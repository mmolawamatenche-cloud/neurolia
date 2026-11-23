"""
Static hand-pose recognition for Lia, powered by the GestureAI model.

GestureAI (c) Abhishek Kumar Singh / Consolecoded, GPL-3.0
The trained model (gesture_model.pkl) and the landmark normalisation this
file reproduces come from that project.
"""
import json
import os
import time
from collections import deque

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_FILE = os.environ.get("LIA_POSE_MODEL", os.path.join(HERE, "gesture_model.pkl"))
MAP_FILE = os.path.join(HERE, "pose_map.json")
DEBUG = os.environ.get("LIA_POSE_DEBUG", "") == "1"

POSE_ACTIONS = {
    "thumbsup": ({"action": "volume_up"}, "Volume up"),
    "Thumbs_UP": ({"action": "volume_up"}, "Volume up"),
    "thumbsdown": ({"action": "volume_down"}, "Volume down"),
    "thumbs_down": ({"action": "volume_down"}, "Volume down"),
    "Peace": ({"action": "play_pause"}, "Play or pause"),
    "open_hand": ({"action": "cancel"}, "Stopped"),
    "Open": ({"action": "cancel"}, "Stopped"),
    "close": ({"action": "mute"}, "Mute toggled"),
    "1": ({"action": "scroll_up"}, "Scroll up"),
    "2": ({"action": "scroll_down"}, "Scroll down"),
    "3": (
        {"action": "hotkey", "keys": ["ctrl", "shift", "tab"]},
        "Previous tab",
    ),
    "three": (
        {"action": "hotkey", "keys": ["ctrl", "shift", "tab"]},
        "Previous tab",
    ),
    "4": ({"action": "switch_tab"}, "Next tab"),
    "four": ({"action": "switch_tab"}, "Next tab"),
    "rotate_clockwise": ({"action": "next_track"}, "Next track"),
    "rotate_anticlockwise": ({"action": "prev_track"}, "Previous track"),
}

REPEAT_ACTIONS = {"volume_up", "volume_down", "scroll_up", "scroll_down"}
QUIET_ACTIONS = {"volume_up", "volume_down", "scroll_up", "scroll_down", "cancel"}


def load_user_map(path=MAP_FILE):
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            for pose, action in json.load(f).items():
                if action in (None, "", "none"):
                    POSE_ACTIONS.pop(pose, None)
                else:
                    POSE_ACTIONS[pose] = (
                        {"action": action},
                        action.replace("_", " ").capitalize(),
                    )
    except Exception as ex:
        print("pose_map.json ignored:", ex)


def normalize_landmarks(flat):
    """Wrist at the origin, scaled to [-1, 1]: exactly what the model was trained on."""
    a = np.array(flat, dtype=float).copy()
    if a.size == 42:
        a = np.hstack([a.reshape(21, 2), np.zeros((21, 1))]).flatten()
    if a.size != 63:
        raise ValueError(f"expected 42 or 63 values, got {a.size}")
    x, y, z = a[::3], a[1::3], a[2::3]
    x -= x[0]
    y -= y[0]
    z -= z[0]
    m = max(abs(x).max(), abs(y).max(), abs(z).max())
    if m > 0:
        x /= m
        y /= m
        z /= m
    a[::3], a[1::3], a[2::3] = x, y, z
    return a


def _flat_xyz(landmarks):
    out = []
    for point in landmarks:
        if hasattr(point, "x"):
            out += [point.x, point.y, point.z]
        else:
            out += list(point)[:3]
    return out


class PoseRecognizer:
    def __init__(
        self, model_path=MODEL_FILE, conf=0.75, hold=0.5, cooldown=1.0,
        repeat_every=0.8, min_interval=0.08, votes=5,
    ):
        self.model_path = model_path
        self.conf, self.hold, self.cooldown = conf, hold, cooldown
        self.repeat_every, self.min_interval = repeat_every, min_interval
        self.clf = None
        self.inv = {}
        self.n_features = 63
        self._votes = deque(maxlen=votes)
        self._t_infer = 0.0
        self._cur = None
        self._since = 0.0
        self._fired = False
        self._last_fire = -1e9
        self.last = (None, 0.0, "")

    @property
    def ready(self):
        return self.clf is not None

    def load(self):
        """Return (ok, message). Never raises. Call from a background thread."""
        if not os.path.exists(self.model_path):
            return False, (
                "Hand-pose model not found. Extract gesture_model.pkl from "
                "GestureAI's gesture_model.zip into the Lia folder to enable "
                "poses like Peace and thumbs-up."
            )
        try:
            import joblib

            data = joblib.load(self.model_path)
            clf = data["model"]
            clf.n_jobs = 1
            self.clf = clf
            self.n_features = int(clf.n_features_in_)
            self.inv = {v: k for k, v in data["label_map"].items()}
            load_user_map()
            return True, (
                f"Hand-poses ready ({len(self.inv)} poses, GestureAI model by "
                "Abhishek Kumar Singh)."
            )
        except Exception as ex:
            self.clf = None
            return False, f"Could not load the hand-pose model: {ex}"

    def classify(self, landmarks):
        """Return the most confident label using xyz and xy-only input."""
        flat = _flat_xyz(landmarks)
        if self.n_features == 42:
            batch = [
                normalize_landmarks(
                    [value for index, value in enumerate(flat) if index % 3 != 2]
                )
            ]
            names = ["xy"]
        else:
            flat0 = list(flat)
            flat0[2::3] = [0.0] * 21
            batch = [normalize_landmarks(flat), normalize_landmarks(flat0)]
            names = ["xyz", "xy0"]
        probs = self.clf.predict_proba(np.array(batch))
        best = (None, 0.0, "")
        for row, name in zip(probs, names):
            index = int(np.argmax(row))
            if row[index] > best[1]:
                best = (self.inv.get(int(self.clf.classes_[index])), float(row[index]), name)
        self.last = best
        return best[0], best[1]

    def lost(self):
        """Call when no hand is visible."""
        self._votes.clear()
        self._cur, self._fired = None, False

    def update(self, landmarks, now=None):
        """Return a pose name once it has been held; otherwise return None."""
        if not self.ready:
            return None
        now = time.time() if now is None else now
        if now - self._t_infer >= self.min_interval:
            self._t_infer = now
            label, conf = self.classify(landmarks)
            self._votes.append(label if conf >= self.conf else None)
            top = max(set(self._votes), key=list(self._votes).count)
            cur = top if list(self._votes).count(top) >= 3 else None
            if cur != self._cur:
                self._cur, self._since, self._fired = cur, now, False
                if DEBUG:
                    print(
                        f"[pose] {cur}  (last: {self.last[0]} "
                        f"{self.last[1]:.2f} via {self.last[2]})"
                    )
        label = self._cur
        if label is None or now - self._since < self.hold:
            return None
        item = POSE_ACTIONS.get(label)
        if item is None:
            return None
        repeat = item[0]["action"] in REPEAT_ACTIONS
        if not self._fired:
            if now - self._last_fire >= self.cooldown:
                self._fired, self._last_fire = True, now
                return label
        elif repeat and now - self._last_fire >= self.repeat_every:
            self._last_fire = now
            return label
        return None
