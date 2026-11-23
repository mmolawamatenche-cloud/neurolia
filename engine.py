import re
from collections import deque

VALID_ACTIONS = {
    "open_app",
    "search",
    "open_website",
    "copy_text",
    "paste",
    "copy_and_paste",
    "type_text",
    "type_and_search",
    "hotkey",
    "scroll_up",
    "scroll_down",
    "close_window",
    "minimise",
    "maximise",
    "new_tab",
    "close_tab",
    "switch_tab",
    "go_back",
    "go_forward",
    "refresh",
    "focus_address_bar",
    "select_all",
    "undo",
    "redo",
    "save",
    "find",
    "volume_up",
    "volume_down",
    "mute",
    "play_pause",
    "next_track",
    "prev_track",
    "screenshot",
    "read_screen",
    "cancel",
    "exit",
    "converse",
    "agent",
    "sequence",
    "open_chrome",
    "open_notepad",
    "open_calculator",
    "open_explorer",
    "open_word",
    "open_excel",
    "copy",
    "lock_screen",
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


def normalise(text: str) -> str:
    value = (text or "").strip()
    value = re.sub(r"[^\w\s\-.:/]+", " ", value.lower())
    return re.sub(r"\s+", " ", value).strip()


def split_wake(text: str):
    if text is None:
        return False, ""
    raw = str(text).strip()
    if not raw:
        return False, ""
    match = re.search(r"(?:^|\s)(?:hey\s+)?lia\b", raw, re.I)
    if not match:
        return False, raw
    remainder = raw[match.end():].strip()
    remainder = re.sub(r"^[,;:!?\.\s]+", "", remainder)
    return True, remainder


def is_failure(text: str) -> bool:
    if text is None:
        return False
    msg = str(text).lower()
    return any(
        token in msg for token in (
            "i don't know how to",
            "command failed",
            "can't safely",
            "safe list",
            "not allowed",
            "failed:",
            "invalid",
            "error",
        )
    )


def hotkey_allowed(keys):
    if not isinstance(keys, (list, tuple)):
        return False
    clean = [str(k).lower().strip() for k in keys if str(k).strip()]
    if not 1 <= len(clean) <= 4:
        return False
    return all(key in _SAFE_KEYS for key in clean)


def validate_action(value):
    if not isinstance(value, dict):
        return False
    action = str(value.get("action") or "").strip()
    if not action:
        return False
    if action in VALID_ACTIONS:
        if action == "hotkey":
            return hotkey_allowed(value.get("keys") or [])
        return True
    return False


def trim_history(history, max_items: int = 10):
    if not isinstance(history, list):
        return []
    max_items = max(1, int(max_items))
    system = [item for item in history if item.get("role") == "system"]
    rest = [item for item in history if item.get("role") != "system"]
    keep = max_items
    if not system:
        return rest[-keep:]
    if keep <= 0:
        return system[:1]
    trimmed = system[:1] + rest[-keep:]
    return trimmed


def parse_command(text):
    if text is None:
        return None
    raw = str(text).strip()
    if not raw:
        return None
    wake, command = split_wake(raw)
    if wake:
        raw = command
    command = raw.strip()
    if not command:
        return None

    agent_match = re.match(
        r"^\W*(?:(?:hey|ok|okay)\s+)?(?:please\s+)?(?:(?:can|could|would)\s+you\s+)?"
        r"(?:take over|computer use|agent mode|use the computer to|use agent to|agent)\b[\s:,.-]*(.*)$",
        command,
        re.I | re.S,
    )
    if agent_match:
        task = agent_match.group(1).strip()
        if task:
            return {"action": "agent", "task": task, "explicit": True,
                    "reply": "Okay, taking over."}
        return {"action": "converse",
                "reply": "Tell me the job after “take over”, for example: take over, search for flights to Paris."}

    lower = command.lower()
    if re.search(r"^(?:hey\s+)?lia\b", command, re.I):
        command = command.split(None, 1)[-1] if " " in command else ""

    if re.search(r"^(?:open|launch|start)\s+(.+?)\s+and\s+search(?:\s+for)?\s+(.+)$", command, re.I):
        target, query = re.match(r"^(?:open|launch|start)\s+(.+?)\s+and\s+search(?:\s+for)?\s+(.+)$", command, re.I).groups()
        return {"action": "search", "target": target.strip(), "query": query.strip()}

    if re.search(r"^(?:open|launch|start)\s+(.+?)\s+and\s+type\s+(.+)$", command, re.I):
        target, text = re.match(r"^(?:open|launch|start)\s+(.+?)\s+and\s+type\s+(.+)$", command, re.I).groups()
        return {"action": "type_text", "destination": target.strip(), "text": text.strip()}

    if re.search(r"^copy\s+everything\s+in\s+(.+?)\s+and\s+paste(?:\s+it)?(?:\s+in|\s+to|\s+into)\s+(.+)$", command, re.I):
        source, dest = re.match(r"^copy\s+everything\s+in\s+(.+?)\s+and\s+paste(?:\s+it)?(?:\s+in|\s+to|\s+into)\s+(.+)$", command, re.I).groups()
        return {"action": "copy_and_paste", "source": source.strip(), "destination": dest.strip()}

    if re.search(r"^copy\s+(.+?)\s+and\s+paste(?:\s+it)?(?:\s+in|\s+to|\s+into)\s+(.+)$", command, re.I):
        text, dest = re.match(r"^copy\s+(.+?)\s+and\s+paste(?:\s+it)?(?:\s+in|\s+to|\s+into)\s+(.+)$", command, re.I).groups()
        return {"action": "copy_text", "text": text.strip(), "destination": dest.strip()}

    if re.search(r"^copy\s+(.+)$", command, re.I):
        text = re.match(r"^copy\s+(.+)$", command, re.I).group(1).strip()
        return {"action": "copy_text", "text": text}

    # explicit sequence fallback
    if re.search(r"^(.+?)\s+and\s+(.+)$", command, re.I):
        left, right = re.match(r"^(.+?)\s+and\s+(.+)$", command, re.I).groups()
        left_cmd = parse_command(left)
        right_cmd = parse_command(right)
        if left_cmd and right_cmd:
            return {"action": "sequence", "steps": [left_cmd, right_cmd]}

    if re.search(r"^(?:please\s+)?(?:can\s+you\s+)?(?:i\s+want\s+to\s+)?(?:please\s+)?open\s+(.+)$", command, re.I):
        target = re.match(r"^(?:please\s+)?(?:can\s+you\s+)?(?:i\s+want\s+to\s+)?(?:please\s+)?open\s+(.+)$", command, re.I).group(1).strip()
        target = re.sub(r"\s+(?:for\s+me|please|now)$", "", target, flags=re.I).strip()
        target_lower = target.lower()
        if re.search(r"\.|(?:facebook|youtube|google|netflix|twitter|x\.com|instagram|amazon|github|wikipedia|gmail)$", target_lower):
            return {"action": "open_website", "query": target}
        return {"action": "open_app", "target": target}

    if re.search(r"^open\s+(.+)$", command, re.I):
        target = re.match(r"^open\s+(.+)$", command, re.I).group(1).strip()
        target_lower = target.lower()
        if re.search(r"\.|(?:facebook|youtube|google|netflix|twitter|x\.com|instagram|amazon|github|wikipedia|gmail)$", target_lower):
            return {"action": "open_website", "query": target}
        return {"action": "open_app", "target": target}

    if re.search(r"^(?:stop|cancel|abort)\b", lower):
        return {"action": "cancel"}

    if re.search(r"^(?:read\s+(?:the\s+)?screen|what(?:'s|s)?\s+on\s+my\s+screen|whats\s+on\s+my\s+screen)$", lower):
        return {"action": "read_screen"}

    if re.search(r"^(?:turn|set)\s+(?:the\s+)?volume\s+(?:up|higher|louder)\b", lower):
        return {"action": "volume_up"}
    if re.search(r"^(?:turn|set)\s+(?:the\s+)?volume\s+(?:down|lower|quieter)\b", lower):
        return {"action": "volume_down"}
    if re.search(r"^(?:mute|silence)\b", lower):
        return {"action": "mute"}

    if re.search(r"^close\s+(?:the\s+)?window\b", lower):
        return {"action": "close_window"}
    if re.search(r"^minimi[sz]e\b", lower):
        return {"action": "minimise"}
    if re.search(r"^switch\s+tab\b", lower):
        return {"action": "switch_tab"}
    if re.search(r"^lock\s+(?:the\s+)?screen\b", lower):
        return {"action": "lock_screen"}
    if re.search(r"^(?:next|skip)\s+(?:song|track)\b", lower):
        return {"action": "next_track"}
    if re.search(r"^(?:take|capture)\s+(?:a\s+)?screenshot\b", lower):
        return {"action": "screenshot"}

    if re.search(r"^(?:go to|visit)\s+([\w.-]+(?:\.[\w.-]+)+(?:/[\w./?&=%-]*)?)\b", lower):
        url = re.search(r"^(?:go to|visit)\s+([\w.-]+(?:\.[\w.-]+)+(?:/[\w./?&=%-]*)?)\b", lower).group(1)
        return {"action": "open_website", "query": url}

    if re.search(r"^(?:go to|visit|open)\s+([A-Za-z0-9.-]+)\b", lower):
        site = re.search(r"^(?:go to|visit|open)\s+([A-Za-z0-9.-]+)\b", lower).group(1)
        if site.lower() in {"facebook", "youtube", "google", "netflix", "twitter", "instagram", "amazon", "github", "wikipedia", "gmail"}:
            return {"action": "open_website", "query": site}

    if re.search(r"^search\b", lower):
        if re.search(r"^search\s+(.+?)\s+(?:on|in|using|with)\s+([\w\s]+)$", lower):
            query, target = re.match(r"^search\s+(.+?)\s+(?:on|in|using|with)\s+([\w\s]+)$", lower).groups()
            return {"action": "search", "query": query.strip(), "target": target.strip()}
        m = re.search(r"^search(?:\s+for)?\s+(.+)$", lower)
        if m:
            q = m.group(1).strip()
            return {"action": "search", "query": q, "target": "chrome"}

    if re.search(r"^scroll\s+(?:up|down)\b", lower):
        direction = re.search(r"^scroll\s+(up|down)\b", lower).group(1)
        return {"action": f"scroll_{direction}"}
    if re.search(r"^(?:goodbye|exit|close lia)\b", lower):
        return {"action": "exit"}
    if re.search(r"^(?:stop|pause)\b", lower):
        return {"action": "cancel"}

    return None


class GestureTracker:
    """Very small gesture detector used by the command engine tests."""

    def __init__(self):
        self._last_hand = None
        self._last_hand_time = None
        self._last_head = None
        self._last_head_time = None
        self._head_neutral = 0.5
        self._head_active = False

    def hand(self, x, t):
        if self._last_hand is None:
            self._last_hand = x
            self._last_hand_time = t
            self._hand_run = 0.0
            self._hand_run_start = t
            return None

        dx = x - self._last_hand
        self._last_hand = x
        self._last_hand_time = t

        if dx > 0:
            self._hand_run += dx
        else:
            self._hand_run = 0.0
            self._hand_run_start = t

        if t - self._hand_run_start < 0.7 and self._hand_run > 0.22:
            self._hand_run = 0.0
            self._hand_run_start = t
            return "hand_swipe_right"

        if dx < 0 and abs(self._hand_run) > 0.22:
            self._hand_run = 0.0
            self._hand_run_start = t
            return "hand_swipe_left"

        return None

    def head(self, x, y, t):
        if self._last_head is None:
            self._last_head = (x, y)
            self._last_head_time = t
            return None

        prev_x, prev_y = self._last_head
        self._last_head = (x, y)
        self._last_head_time = t

        if abs(x - 0.5) > 0.2:
            self._head_active = False
            return None

        if y < 0.42 and not self._head_active:
            self._head_active = True
            return "head_nod_up"

        if y > 0.48:
            self._head_active = False
        return None
