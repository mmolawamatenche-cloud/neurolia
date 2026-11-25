"""
Cursor controller for Lia: move the mouse with your index finger, pinch to click,
two fingers to scroll.

No GUI code and no hard dependency on a screen, so it can be unit-tested anywhere.
Lia's camera loop feeds it MediaPipe hand landmarks and applies the events it returns.

    point (index finger up)        move the cursor
    quick pinch (thumb + index)    left click (at the spot you were pointing at, before the pinch)
    hold the pinch                 drag; let go to drop
    pinch thumb + middle finger    right click
    index + middle together        scroll (move the hand up or down)
    open palm for one second       leave cursor mode
"""
import math
import time
from collections import deque

WRIST, THUMB_TIP, INDEX_MCP = 0, 4, 5
INDEX_PIP, INDEX_TIP = 6, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_TIP = 9, 10, 12
RING_PIP, RING_TIP = 14, 16
PINKY_PIP, PINKY_TIP = 18, 20


def _xy(p):
    return (p.x, p.y) if hasattr(p, "x") else (p[0], p[1])


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


class CursorController:
    def __init__(self, screen=(1920, 1080), box=(0.22, 0.15, 0.78, 0.72), dwell=0.0,
                 pinch_on=0.30, pinch_off=0.45, tap_max=0.40, edge=6,
                 palm_hold=1.0, scroll_step=0.035, scroll_amount=5, dwell_radius=25):
        self.screen = (int(screen[0]), int(screen[1]))
        self.box = box
        self.dwell = float(dwell)
        self.pinch_on, self.pinch_off, self.tap_max = pinch_on, pinch_off, tap_max
        self.edge, self.palm_hold = edge, palm_hold
        self.scroll_step, self.scroll_amount, self.dwell_radius = scroll_step, scroll_amount, dwell_radius
        self.enabled = False
        self.paused = False
        self.state = "off"
        self._reset()

    @property
    def active(self):
        return self.enabled and not self.paused

    def enable(self):
        self._reset()
        self.enabled = True
        self.state = "idle"

    def pause(self):
        """The agent is about to drive the mouse. Returns events to apply (let go of any drag)."""
        ev = self._release()
        self.paused = True
        self.state = "paused"
        return ev

    def resume(self):
        self.paused = False
        self.state = "idle" if self.enabled else "off"

    def disable(self):
        """Returns events to apply (e.g. let go of a drag)."""
        ev = self._release()
        self.enabled = False
        self.state = "off"
        self._reset()
        return ev

    def _reset(self):
        self.pos = None
        self._last_target = None
        self._last_t = None
        self._emitted = None
        self._hist = deque(maxlen=40)
        self._pinch = None
        self._scroll_ref = None
        self._scroll_acc = 0.0
        self._palm_since = None
        self._dw_anchor = None
        self._dw_since = 0.0
        self._dw_fired = False

    def _release(self):
        ev = []
        if self._pinch and self._pinch.get("dragging"):
            x, y = self.pos or (0, 0)
            ev.append(("up", int(x), int(y)))
        self._pinch = None
        self._scroll_ref = None
        self._palm_since = None
        return ev

    def lost(self, now=None):
        """The hand left the picture: never leave a button held down."""
        return self._release() if self.enabled else []

    def _target(self, x, y):
        bx0, by0, bx1, by1 = self.box
        sx = _clamp((x - bx0) / (bx1 - bx0), 0.0, 1.0)
        sy = _clamp((y - by0) / (by1 - by0), 0.0, 1.0)
        w, h = self.screen
        return self.edge + sx * (w - 1 - 2 * self.edge), self.edge + sy * (h - 1 - 2 * self.edge)

    def _smooth(self, tx, ty, now):
        if self.pos is None:
            self.pos, self._last_target, self._last_t = (tx, ty), (tx, ty), now
            return self.pos
        dt = max(now - (self._last_t or now), 1e-3)
        speed = math.hypot(tx - self._last_target[0], ty - self._last_target[1]) / dt
        a = min(0.85, 0.12 + speed / 2500.0)
        self.pos = (self.pos[0] + a * (tx - self.pos[0]), self.pos[1] + a * (ty - self.pos[1]))
        self._last_target, self._last_t = (tx, ty), now
        return self.pos

    def _anchor(self, now, back=0.12):
        """Where the cursor was just BEFORE the pinch started."""
        for t, x, y in reversed(self._hist):
            if t <= now - back:
                return x, y
        return self._hist[0][1:] if self._hist else (self.pos or (0, 0))

    def update(self, lm, now=None, aspect=4 / 3):
        now = time.time() if now is None else now
        if not self.enabled:
            return []
        if self.paused:
            self.state = "paused"
            return self._release()

        pts = [_xy(p) for p in lm]
        P = lambda i: (pts[i][0] * aspect, pts[i][1])
        d = lambda a, b: math.hypot(P(a)[0] - P(b)[0], P(a)[1] - P(b)[1])
        size = d(WRIST, MIDDLE_MCP) or 1e-6
        ext = lambda tip, pip: d(WRIST, tip) > 1.15 * d(WRIST, pip)
        idx  = ext(INDEX_TIP,  INDEX_PIP)
        mid  = ext(MIDDLE_TIP, MIDDLE_PIP)
        ring = ext(RING_TIP,   RING_PIP)
        pinky = ext(PINKY_TIP, PINKY_PIP)
        pr_idx = d(THUMB_TIP, INDEX_TIP)  / size
        pr_mid = d(THUMB_TIP, MIDDLE_TIP) / size
        events = []

        # 1) open palm held = leave cursor mode
        if idx and mid and ring and pinky and pr_idx > 0.7 and self._pinch is None:
            self._palm_since = self._palm_since or now
            self.state = "palm"
            if now - self._palm_since >= self.palm_hold:
                events += self._release()
                self.enabled, self.state = False, "off"
                events.append(("exit",))
            return events
        self._palm_since = None

        # 2) pinch state machine (click / drag / right click)
        if self._pinch is None:
            if pr_idx < self.pinch_on:
                self._pinch = {"kind": "left",  "t0": now, "anchor": self._anchor(now), "dragging": False}
            elif pr_mid < self.pinch_on and pr_idx > self.pinch_off:
                self._pinch = {"kind": "right", "t0": now, "anchor": self._anchor(now), "dragging": False}
            if self._pinch:
                self._scroll_ref = None
        else:
            p = self._pinch
            ratio = pr_idx if p["kind"] == "left" else pr_mid
            if ratio > self.pinch_off:
                ax, ay = int(p["anchor"][0]), int(p["anchor"][1])
                if p["dragging"]:
                    x, y = self.pos or p["anchor"]
                    events.append(("up", int(x), int(y)))
                else:
                    events.append(("click", ax, ay, p["kind"]))
                self._pinch = None
                self._dw_fired, self._dw_since, self._dw_anchor = True, now, None
            elif p["kind"] == "left" and not p["dragging"] and now - p["t0"] >= self.tap_max:
                p["dragging"] = True
                events.append(("down", int(p["anchor"][0]), int(p["anchor"][1])))

        pinching = self._pinch is not None

        # 3) two fingers together = scroll
        together = d(INDEX_TIP, MIDDLE_TIP) / size < 0.45
        if not pinching and idx and mid and together and not ring and not pinky:
            y = (pts[INDEX_TIP][1] + pts[MIDDLE_TIP][1]) / 2
            if self._scroll_ref is not None:
                self._scroll_acc += y - self._scroll_ref
                n = int(self._scroll_acc / self.scroll_step)
                if n:
                    events.append(("scroll", -n * self.scroll_amount))
                    self._scroll_acc -= n * self.scroll_step
            self._scroll_ref = y
            self.state = "scrolling"
            return events
        self._scroll_ref, self._scroll_acc = None, 0.0

        # 4) pointing moves the cursor
        if idx or pinching:
            tx, ty = self._target(*pts[INDEX_TIP])
            x, y = self._smooth(tx, ty, now)
            self._hist.append((now, x, y))
            if not pinching or self._pinch["dragging"]:
                if self._emitted is None or math.hypot(x - self._emitted[0], y - self._emitted[1]) >= 2:
                    self._emitted = (x, y)
                    events.append(("move", int(x), int(y)))
            self.state = ("dragging" if pinching and self._pinch["dragging"]
                          else ("pinching" if pinching else "pointing"))
            # 5) optional dwell click
            if self.dwell > 0 and not pinching:
                if (self._dw_anchor is None or
                        math.hypot(x - self._dw_anchor[0], y - self._dw_anchor[1]) > self.dwell_radius):
                    self._dw_anchor, self._dw_since, self._dw_fired = (x, y), now, False
                elif not self._dw_fired and now - self._dw_since >= self.dwell:
                    self._dw_fired = True
                    events.append(("click", int(x), int(y), "left"))
        else:
            self.state = "idle"
        return events


class PyAutoGuiMouse:
    """Real mouse. _pause=False so Lia's global pyautogui.PAUSE doesn't make the cursor laggy."""
    def __init__(self):
        import pyautogui
        self.pg = pyautogui

    def move(self, x, y):
        self.pg.moveTo(x, y, _pause=False)

    def click(self, x, y, button="left"):
        self.pg.click(x, y, button=button, _pause=False)

    def down(self, x, y):
        self.pg.moveTo(x, y, _pause=False)
        self.pg.mouseDown(_pause=False)

    def up(self, x, y):
        self.pg.moveTo(x, y, _pause=False)
        self.pg.mouseUp(_pause=False)

    def scroll(self, n):
        self.pg.scroll(n, _pause=False)


def apply_events(events, mouse):
    """Apply mouse events; returns non-mouse events (e.g. ('exit',))."""
    rest = []
    for ev in events:
        k = ev[0]
        if k == "move":
            mouse.move(ev[1], ev[2])
        elif k == "click":
            mouse.click(ev[1], ev[2], ev[3])
        elif k == "down":
            mouse.down(ev[1], ev[2])
        elif k == "up":
            mouse.up(ev[1], ev[2])
        elif k == "scroll":
            mouse.scroll(ev[1])
        else:
            rest.append(ev)
    return rest
