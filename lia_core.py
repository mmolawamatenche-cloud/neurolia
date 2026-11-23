"""Safety and reliability helpers for the NeuroLia desktop app.

This module uses only the Python standard library so its behavior can be
tested independently from the GUI, microphone, camera, and Windows APIs.
"""

import os
import re
import shutil
import time
from collections import deque
from dataclasses import dataclass
from difflib import get_close_matches


def normalise(text: str) -> str:
    """Lower-case, strip punctuation at the edges, and collapse spaces."""
    value = (text or "").lower().strip()
    value = re.sub(r"[^\w\s:.\-]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


@dataclass
class AppMatch:
    name: str | None
    target: str | None
    score: float


def match_app(text: str, apps: dict, fuzzy_cutoff: float = 0.75,
              min_len: int = 3) -> AppMatch:
    """Match exact app names, clear whole-word names, or strict fuzzy matches."""
    value = normalise(text)
    if not value:
        return AppMatch(None, None, 0.0)
    if value in apps:
        return AppMatch(value, apps[value], 1.0)
    if len(value) < min_len:
        return AppMatch(None, None, 0.0)

    words = set(value.split())
    inside = [key for key in apps if set(key.split()) <= words]
    if inside:
        key = max(inside, key=len)
        return AppMatch(key, apps[key], 0.95)

    partial = [key for key in apps if words <= set(key.split())]
    if len(partial) == 1:
        key = partial[0]
        return AppMatch(key, apps[key], 0.9)

    close = get_close_matches(value, list(apps), n=1, cutoff=fuzzy_cutoff)
    if close:
        key = close[0]
        return AppMatch(key, apps[key], fuzzy_cutoff)
    return AppMatch(None, None, 0.0)


_SIMPLE_RULES = [
    (r"\bscreenshot\b", {"action": "screenshot", "reply": "Screenshot saved."}),
    (r"\bvolume up\b|\blouder\b", {"action": "volume_up", "reply": "Volume up."}),
    (r"\bvolume down\b|\bquieter\b", {"action": "volume_down", "reply": "Volume down."}),
    (r"\bmute\b", {"action": "mute", "reply": "Muted."}),
    (r"\bscroll up\b", {"action": "scroll_up", "reply": "Scrolling up."}),
    (r"\bscroll down\b", {"action": "scroll_down", "reply": "Scrolling down."}),
    (r"\bnew tab\b", {"action": "new_tab", "reply": "New tab."}),
    (r"\bclose (?:the |this )?tab\b",
     {"action": "close_tab", "reply": "Closing the tab."}),
    (r"\bclose (?:the |this )?window\b",
     {"action": "close_window", "reply": "Closing the window."}),
    (r"\bgo back\b", {"action": "go_back", "reply": "Going back."}),
    (r"\bgo forward\b", {"action": "go_forward", "reply": "Going forward."}),
    (r"\brefresh\b|\breload\b", {"action": "refresh", "reply": "Refreshed."}),
    (r"\bsave\b", {"action": "save", "reply": "Saved."}),
    (r"\bselect all\b", {"action": "select_all", "reply": "Selected all."}),
    (r"\bundo\b", {"action": "undo", "reply": "Undone."}),
    (r"\bredo\b", {"action": "redo", "reply": "Redone."}),
    (r"\bnext track\b|\bnext song\b", {"action": "next_track", "reply": "Next track."}),
    (r"\bprevious track\b|\bprevious song\b",
     {"action": "prev_track", "reply": "Previous track."}),
    (r"\bpause\b", {"action": "play_pause", "reply": "Paused."}),
    (r"\bplay\b|\bresume\b", {"action": "play_pause", "reply": "Play."}),
    (r"\bexit\b|\bgoodbye\b|\bclose lia\b",
     {"action": "exit", "reply": "Goodbye!"}),
]


def match_simple_command(text: str) -> dict | None:
    """Return a short command action, using whole-word matches only."""
    command = normalise(text)
    if not command:
        return None
    for pattern, result in _SIMPLE_RULES:
        if re.search(pattern, command):
            return dict(result)
    return None


ALLOWED_ACTIONS = {
    "legacy_open", "open_app", "search", "open_website", "copy_text", "paste",
    "copy_and_paste", "type_text", "type_and_search", "hotkey", "scroll_up",
    "scroll_down", "close_window", "minimise", "maximise", "new_tab",
    "close_tab", "switch_tab", "go_back", "go_forward", "refresh",
    "focus_address_bar", "select_all", "undo", "redo", "save", "find",
    "volume_up", "volume_down", "mute", "play_pause", "next_track",
    "prev_track", "screenshot", "exit", "converse", "open_chrome",
    "open_notepad", "open_calculator", "open_explorer", "open_word",
    "open_excel", "copy", "lock_screen",
    "agent",
}

_SAFE_KEYS = (
    set("abcdefghijklmnopqrstuvwxyz0123456789")
    | {f"f{index}" for index in range(1, 13)}
    | {
        "ctrl", "alt", "shift", "win", "tab", "enter", "esc", "space",
        "left", "right", "up", "down", "home", "end", "pageup",
        "pagedown", "backspace",
    }
)

CONFIRM_ACTIONS = {"close_window", "close_tab", "lock_screen"}
CONFIRM_KEYSETS = {
    frozenset({"alt", "f4"}),
    frozenset({"win", "l"}),
    frozenset({"ctrl", "w"}),
}
_CONFIRM_LABELS = {
    "close_window": "Close this window?",
    "close_tab": "Close this tab?",
    "lock_screen": "Lock the screen?",
}


def _keys(data: dict) -> list[str]:
    keys = data.get("keys") or []
    if not isinstance(keys, (list, tuple)):
        return []
    return [str(key).lower().strip() for key in keys]


def is_allowed(data: object) -> bool:
    """Return whether Lia recognizes the action and any supplied hotkey."""
    if not isinstance(data, dict):
        return False
    action = str(data.get("action") or "converse").strip()
    if action not in ALLOWED_ACTIONS:
        return False
    if action == "hotkey":
        keys = _keys(data)
        return 1 <= len(keys) <= 4 and all(key in _SAFE_KEYS for key in keys)
    return True


def needs_confirmation(data: object) -> bool:
    if not isinstance(data, dict):
        return False
    action = str(data.get("action") or "").strip()
    if action in CONFIRM_ACTIONS:
        return True
    return action == "hotkey" and frozenset(_keys(data)) in CONFIRM_KEYSETS


def confirmation_prompt(data: dict) -> str:
    action = str(data.get("action") or "").strip()
    label = _CONFIRM_LABELS.get(action)
    if label is None and action == "hotkey":
        label = {
            frozenset({"alt", "f4"}): "Close this window?",
            frozenset({"win", "l"}): "Lock the screen?",
            frozenset({"ctrl", "w"}): "Close this tab?",
        }.get(frozenset(_keys(data)))
    return f"{label or 'Do this?'} Say yes to confirm, or no to cancel."


_YES = r"\b(yes|yeah|yep|yup|confirm|confirmed|ok|okay|sure|go ahead|do it)\b"
_NO = r"\b(no|nope|cancel|stop|never mind|nevermind|don't|dont)\b"


class ConfirmationGate:
    """Hold one risky action until the user confirms or cancels it."""

    def __init__(self, timeout: float = 12.0, clock=time.monotonic):
        self.timeout = timeout
        self._clock = clock
        self._pending: dict | None = None
        self._asked_at = 0.0

    def ask(self, data: dict) -> str:
        self._pending = dict(data)
        self._asked_at = self._clock()
        return confirmation_prompt(data)

    def has_pending(self) -> bool:
        if self._pending is None:
            return False
        if self._clock() - self._asked_at > self.timeout:
            self._pending = None
            return False
        return True

    def resolve(self, text: str) -> tuple[str | None, dict | None]:
        """Return (status, action) where status is confirmed/cancelled/other."""
        if not self.has_pending():
            return None, None
        command = normalise(text)
        said_no = re.search(_NO, command) is not None
        said_yes = re.search(_YES, command) is not None
        data, self._pending = self._pending, None
        if said_no:
            return "cancelled", None
        if said_yes:
            return "confirmed", data
        return "other", None


class GestureStabilizer:
    """Convert calibrated camera movement into held, cooldown-limited gestures."""

    def __init__(self, hold_frames: int = 5, cooldown: float = 1.2,
                 head_delta: float = 0.10, swipe_dx: float = 0.25,
                 swipe_window: int = 8, calibrate_frames: int = 30,
                 clock=time.monotonic):
        self.hold_frames = hold_frames
        self.cooldown = cooldown
        self.head_delta = head_delta
        self.swipe_dx = swipe_dx
        self.calibrate_frames = calibrate_frames
        self._clock = clock
        self._hand = deque(maxlen=swipe_window)
        self._cal: list[tuple[float, float]] = []
        self._neutral: tuple[float, float] | None = None
        self._cand: str | None = None
        self._cand_n = 0
        self._armed = True
        self._last = float("-inf")

    @property
    def calibrated(self) -> bool:
        return self._neutral is not None

    def recalibrate(self) -> None:
        self._cal, self._neutral = [], None
        self._cand, self._cand_n, self._armed = None, 0, True
        self._hand.clear()

    def _cooling(self, now: float) -> bool:
        return now - self._last < self.cooldown

    def update(self, hand_x: float | None = None,
               head_xy: tuple[float, float] | None = None) -> str | None:
        """Feed one camera frame and return a gesture name, if detected."""
        now = self._clock()
        if hand_x is None:
            self._hand.clear()
        else:
            self._hand.append(hand_x)
            if len(self._hand) == self._hand.maxlen and not self._cooling(now):
                distance = self._hand[-1] - self._hand[0]
                if abs(distance) >= self.swipe_dx:
                    self._hand.clear()
                    self._last = now
                    return "hand_swipe_right" if distance > 0 else "hand_swipe_left"

        if head_xy is None:
            self._cand, self._cand_n = None, 0
            return None

        if self._neutral is None:
            self._cal.append(head_xy)
            if len(self._cal) >= self.calibrate_frames:
                xs, ys = zip(*self._cal)
                self._neutral = (sum(xs) / len(xs), sum(ys) / len(ys))
            return None

        dx = head_xy[0] - self._neutral[0]
        dy = head_xy[1] - self._neutral[1]
        candidate = None
        if abs(dx) >= abs(dy):
            if dx <= -self.head_delta:
                candidate = "head_swipe_left"
            elif dx >= self.head_delta:
                candidate = "head_swipe_right"
        elif dy <= -self.head_delta:
            candidate = "head_nod_up"

        if candidate is None:
            self._cand, self._cand_n, self._armed = None, 0, True
            return None

        if candidate == self._cand:
            self._cand_n += 1
        else:
            self._cand, self._cand_n = candidate, 1

        if self._armed and self._cand_n >= self.hold_frames and not self._cooling(now):
            self._armed = False
            self._last = now
            return candidate
        return None


def find_tesseract() -> str | None:
    """Find tesseract.exe via configuration, PATH, or common Windows folders."""
    configured = os.environ.get("TESSERACT_CMD")
    if configured and os.path.exists(configured):
        return configured
    found = shutil.which("tesseract")
    if found:
        return found
    for path in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ):
        if os.path.exists(path):
            return path
    return None


DEMO_STEPS = [
    ("Hi, I'm Lia. Watch me control this computer by voice.", None),
    ("Opening Notepad.", "open notepad"),
    ("Typing a note for you.", "type Hello from Lia. I can open apps and type for you by voice."),
    ("Searching the web.", "search for free accessibility tools for windows"),
    ("That's Lia: a computer you can control with just your voice or a hand.", None),
]
