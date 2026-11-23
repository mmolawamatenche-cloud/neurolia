"""
NeuroLia — Live Assistant  (full rebuild)
- Always-on voice listener (no button needed)
- 30+ app launcher with fuzzy match
- In-app search via voice (Chrome, Edge, Spotify, etc.)
- Copy text to clipboard then paste to active window
- Full blind / handless support (zero mouse/keyboard needed)
- Camera gesture panel
- GPT-4o brain with local fallback

pip install customtkinter openai speechrecognition pyttsx3 pyaudio
pip install opencv-python mediapipe pillow pyautogui pyperclip
"""

import customtkinter as ctk
import tkinter as tk
import threading, time, queue, os, sys, json, webbrowser, re, ctypes
import subprocess, pyautogui, pyperclip
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
from urllib.parse import quote_plus
from engine import (
    GestureTracker,
    hotkey_allowed,
    is_failure,
    parse_command,
    split_wake,
    trim_history,
    validate_action,
)
from agent import LiaAgent, AgentUnavailable, first_sentence, is_yes
from lia_core import (
    ConfirmationGate,
    GestureStabilizer,
    confirmation_prompt,
    find_tesseract,
    is_allowed,
    match_app,
    match_simple_command,
    needs_confirmation,
)
try:
    from static_gestures import PoseRecognizer, POSE_ACTIONS, QUIET_ACTIONS
    POSE_OK = True
except Exception:
    POSE_OK = False
    PoseRecognizer = None
    POSE_ACTIONS = {}
    QUIET_ACTIONS = set()

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.12

# ── optional imports ───────────────────────────────────────────────────────────
try:
    import cv2, mediapipe as mp
    from PIL import Image, ImageTk
    CAM_OK = True
except ImportError:
    CAM_OK = False

try:
    import speech_recognition as sr
    SR_OK = True
except ImportError:
    SR_OK = False

try:
    import pyttsx3
    TTS_OK = True
except Exception:
    TTS_OK = False

try:
    from openai import OpenAI
    GPT_OK = True
except ImportError:
    GPT_OK = False

# ── identity ───────────────────────────────────────────────────────────────────
# Owner identity and API key come from environment variables (never hard-code them).
#   LIA_OWNER_IDS="name,email,idnumber"   LIA_OWNER_NAME="Alex"   OPENAI_API_KEY="..."
MASTER_IDS = [x.strip().lower() for x in os.environ.get("LIA_OWNER_IDS", "").split(",") if x.strip()]
OWNER_NAME = os.environ.get("LIA_OWNER_NAME", "Owner")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY_HERE")

# ── colour palette ─────────────────────────────────────────────────────────────
C = dict(
    bg="#09090e", panel="#111118", card="#18181f", border="#252530",
    purple="#8b7cf8", pur_dim="#2d2860", teal="#20c97a", teal_dim="#0a3d22",
    amber="#f0a030", coral="#e85545", blue="#4a9eff", blue_dim="#1a3a6b",
    text="#f0eeff", dim="#6b6890", muted="#35334a",
)

# ── app registry ───────────────────────────────────────────────────────────────
WIN_APPS = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "firefox": "firefox",
    "notepad": "notepad",
    "word": "winword",
    "word 2016": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "access": "msaccess",
    "access 2016": "msaccess",
    "outlook": "outlook",
    "microsoft store": "ms-windows-store:",
    "store": "ms-windows-store:",
    "office": "winword",
    "calculator": "calc",
    "calendar": "outlookcal:",
    "file explorer": "explorer",
    "explorer": "explorer",
    "task manager": "taskmgr",
    "settings": "ms-settings:",
    "paint": "mspaint",
    "snipping tool": "snippingtool",
    "vs code": "code",
    "visual studio code": "code",
    "code": "code",
    "spotify": "spotify",
    "vlc": "vlc",
    "whatsapp": "whatsapp:",
    "teams": "msteams:",
    "microsoft teams": "msteams:",
    "skype": "skype:",
    "discord": "discord",
    "instagram": "instagram:",
    "tiktok": "tiktok:",
    "espn": "espn:",
    "copilot": "microsoft.copilot:",
    "copilot ai": "microsoft.copilot:",
}


def _run_windows_target(target: str) -> bool:
    try:
        if target.endswith(":"):
            os.startfile(target)
            return True
        try:
            os.startfile(target)
            return True
        except OSError:
            pass
        subprocess.Popen(target, shell=True)
        return True
    except Exception:
        return False


def _open_url(url: str) -> bool:
    try:
        webbrowser.open(url)
        return True
    except Exception:
        return False


def _foreground_title() -> str:
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value.lower().strip()
    except Exception:
        return ""


SEARCHABLE_APPS = {
    "chrome": lambda q: _open_url(f"https://www.google.com/search?q={quote_plus(q)}"),
    "edge": lambda q: _run_windows_target(f'msedge "https://www.google.com/search?q={quote_plus(q)}"'),
    "firefox": lambda q: _run_windows_target(f'firefox "https://www.google.com/search?q={quote_plus(q)}"'),
    "spotify": lambda q: _run_windows_target(f"spotify:search:{quote_plus(q)}"),
    "youtube": lambda q: _open_url(f"https://www.youtube.com/results?search_query={quote_plus(q)}"),
    "google": lambda q: _open_url(f"https://www.google.com/search?q={quote_plus(q)}"),
    "maps": lambda q: _open_url(f"https://maps.google.com/?q={quote_plus(q)}"),
    "wikipedia": lambda q: _open_url(f"https://en.wikipedia.org/wiki/{quote_plus(q.replace(' ', '_'))}"),
    "amazon": lambda q: _open_url(f"https://www.amazon.com/s?k={quote_plus(q)}"),
    "news": lambda q: _open_url(f"https://news.google.com/search?q={quote_plus(q)}"),
}

# ── TTS engine ─────────────────────────────────────────────────────────────────
_tts_q: queue.Queue = queue.Queue()
_tts_stop = threading.Event()
_speaking = threading.Event()

def _tts_worker():
    engine = None
    if TTS_OK:
        try:
            engine = pyttsx3.init()
        except Exception:
            engine = None
    while True:
        txt = _tts_q.get()
        if txt is None:
            _tts_q.task_done()
            break
        _tts_stop.clear()
        _speaking.set()
        if engine:
            try:
                engine.say(txt)
                engine.runAndWait()
            except Exception:
                try:
                    engine = pyttsx3.init()
                    engine.say(txt)
                    engine.runAndWait()
                except Exception:
                    pass
        _speaking.clear()
        _tts_q.task_done()

threading.Thread(target=_tts_worker, daemon=True).start()

def _safe_print(txt: str) -> str:
    """Replace common Unicode punctuation with ASCII equivalents for cp1252 consoles."""
    replacements = {
        "\u2014": "--",  # em dash
        "\u2013": "-",   # en dash
        "\u2018": "'",   # left single quote
        "\u2019": "'",   # right single quote
        "\u201c": '"',   # left double quote
        "\u201d": '"',   # right double quote
        "\u2026": "...", # ellipsis
    }
    for char, replacement in replacements.items():
        txt = txt.replace(char, replacement)
    return txt.encode(sys.stdout.encoding, errors="replace").decode(sys.stdout.encoding)

def speak(txt: str):
    print(f"Lia >> {_safe_print(txt)}")
    # drain any queued speech so new reply plays immediately
    while not _tts_q.empty():
        try:
            _tts_q.get_nowait()
            _tts_q.task_done()
        except queue.Empty:
            break
    _tts_q.put(txt)

def stop_speaking():
    while not _tts_q.empty():
        try:
            _tts_q.get_nowait()
            _tts_q.task_done()
        except queue.Empty:
            break
    _tts_stop.set()

# ── fuzzy app match ────────────────────────────────────────────────────────────
def find_app(text: str):
    match = match_app(text, WIN_APPS)
    return match.name, match.target

def find_search_engine(text: str):
    match = match_app(text, SEARCHABLE_APPS)
    return match.name, match.target


def parse_command_text(text: str):
    return parse_command(text)


def split_wake_text(text: str):
    return split_wake(text)


def is_failure_message(text: str) -> bool:
    return is_failure(text)


def hotkey_allowed_keys(keys):
    return hotkey_allowed(keys)


def validate_action_data(payload):
    return validate_action(payload)


# ── command executor ───────────────────────────────────────────────────────────
def _wait_for_app(app_name: str, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    tokens = [w for w in app_name.lower().split() if w]
    while time.time() < deadline:
        title = _foreground_title()
        if title and any(tok in title for tok in tokens):
            return True
        time.sleep(0.25)
    return False


def _launch_and_wait(app_key: str, wait_sec: float = 1.5) -> tuple:
    name, target = find_app(app_key)
    if not target:
        return app_key, False
    ok = _run_windows_target(target)
    if not ok:
        return name or app_key, False
    time.sleep(wait_sec)
    if name:
        _wait_for_app(name, timeout=6.0)
    return name or app_key, True


def _type_text_in_active_field(text: str) -> str:
    if not text:
        return "No text to type."
    try:
        pyautogui.write(text, interval=0.02)
        return f'Typed: "{text[:60]}"'
    except Exception:
        try:
            pyperclip.copy(text)
            time.sleep(0.15)
            pyautogui.hotkey("ctrl", "v")
            return f'Typed via paste: "{text[:60]}"'
        except Exception as ex:
            return f"Typing failed: {ex}"


def _focus_destination_field(app_key: str, field_hint: str = ""):
    app_key = (app_key or "").lower().strip()
    field = (field_hint or "").lower().strip()
    browser_apps = {"chrome", "edge", "firefox", "microsoft edge", "google chrome"}
    office_apps = {"word", "word 2016", "notepad", "powerpoint", "excel", "access", "access 2016", "outlook"}
    search_apps = {"spotify", "microsoft store", "store"}
    if app_key in browser_apps or field in {"address bar", "url bar"}:
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.2)
        return
    if app_key in search_apps or field in {"search", "search box"}:
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.2)
        pyautogui.hotkey("ctrl", "a")
        time.sleep(0.1)
        return
    if app_key in {"vs code", "code", "visual studio code"}:
        pyautogui.hotkey("ctrl", "n")
        time.sleep(0.35)
        return
    if app_key in office_apps:
        pyautogui.press("esc")
        time.sleep(0.1)


def _paste_into_app(text: str, app_key: str, field_hint: str = "") -> str:
    if not text:
        return "No text to paste."
    try:
        pyperclip.copy(text)
    except Exception as ex:
        return f"Clipboard failed: {ex}"
    display_name, ok = _launch_and_wait(app_key, wait_sec=1.8)
    if not ok:
        time.sleep(0.3)
        try:
            pyautogui.hotkey("ctrl", "v")
            return f'Pasted into active window: "{text[:50]}"'
        except Exception as ex:
            return f"Paste failed: {ex}"
    time.sleep(0.4)
    _focus_destination_field(app_key, field_hint)
    time.sleep(0.2)
    try:
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.15)
        return f'Opened {display_name.title()} and pasted: "{text[:50]}"'
    except Exception as ex:
        return f"Paste failed in {display_name.title()}: {ex}"


def _normalize_action(data: dict) -> dict:
    """Accept both current JSON actions and legacy command-style aliases."""
    normalized = dict(data)
    action = str(data.get("action") or "").strip()

    legacy_aliases = {
        "open_chrome": {"action": "legacy_open", "target": "chrome"},
        "open_notepad": {"action": "legacy_open", "target": "notepad"},
        "open_calculator": {"action": "legacy_open", "target": "calculator"},
        "open_explorer": {"action": "legacy_open", "target": "file explorer"},
        "open_word": {"action": "legacy_open", "target": "word"},
        "open_excel": {"action": "legacy_open", "target": "excel"},
        "copy": {"action": "hotkey", "keys": ["ctrl", "c"], "label": "Copied."},
        "volume_up": {"action": "volume_up"},
        "volume_down": {"action": "volume_down"},
        "mute": {"action": "mute"},
        "lock_screen": {"action": "hotkey", "keys": ["win", "l"], "label": "Screen locked."},
    }

    mapping = legacy_aliases.get(action)
    if mapping:
        normalized["action"] = mapping["action"]
        if "target" in mapping and not normalized.get("target"):
            normalized["target"] = mapping["target"]
        if "keys" in mapping:
            normalized["keys"] = mapping["keys"]
        if "label" in mapping:
            normalized["label"] = mapping["label"]

    return normalized


def execute(data: dict, *, confirmed: bool = False) -> str:
    try:
        data = _normalize_action(data)
        if not is_allowed(data):
            return "I can't safely run that action."
        if needs_confirmation(data) and not confirmed:
            return confirmation_prompt(data)
        action = (data.get("action") or "").strip()
        target = (data.get("target") or "").lower().strip()
        query = (data.get("query") or "").strip()
        text = (data.get("text") or "").strip()
        dest = (data.get("destination") or "").lower().strip()
        field = (data.get("field") or "").lower().strip()

        if action == "legacy_open":
            shell_targets = {
                "chrome": "start chrome",
                "notepad": "start notepad",
                "calculator": "start calc",
                "file explorer": "start explorer",
                "word": "start winword",
                "excel": "start excel",
            }
            cmd = shell_targets.get(target)
            if not cmd:
                return f"I don't know how to open '{target}'."
            os.system(cmd)
            friendly_name = {
                "chrome": "Chrome",
                "notepad": "Notepad",
                "calculator": "Calculator",
                "file explorer": "File Explorer",
                "word": "Word",
                "excel": "Excel",
            }.get(target, target.title())
            return f"Opening {friendly_name}."

        elif action == "open_app":
            name, launch_target = find_app(target)
            if launch_target and _run_windows_target(launch_target):
                return f"Opening {(name or target).title()}."
            if "." in target:
                url = target if target.startswith("http") else f"https://{target}"
                if _open_url(url):
                    return f"Opening {target}."
            return f"I don't know how to open '{target}'."

        elif action == "search":
            q = query or text
            if not q:
                return "No search query provided."
            engine, fn = find_search_engine(target)
            if fn:
                fn(q)
                return f"Searching {engine.title()} for: {q}"
            name, launch_target = find_app(target)
            if launch_target:
                _launch_and_wait(target, 1.8)
                time.sleep(0.3)
                _focus_destination_field(target, field or "search box")
                _type_text_in_active_field(q)
                time.sleep(0.1)
                pyautogui.press("enter")
                return f"Opened {name.title()} and searched for: {q}"
            _open_url(f"https://www.google.com/search?q={quote_plus(q)}")
            return f"Searching Google for: {q}"

        elif action == "open_website":
            url = query or target
            if not url:
                return "No URL provided."
            full = url if url.startswith("http") else f"https://{url}"
            if _open_url(full):
                return f"Opening {url}."
            return f"Could not open {url}."

        elif action == "copy_text":
            if text:
                pyperclip.copy(text)
                if dest:
                    return _paste_into_app(text, dest, field)
                return f'Copied: "{text[:60]}"'
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.2)
            pyautogui.hotkey("ctrl", "c")
            time.sleep(0.2)
            copied = pyperclip.paste()
            if dest:
                return _paste_into_app(copied, dest, field)
            return "Selected all and copied."

        elif action == "paste":
            payload = text or pyperclip.paste()
            if dest:
                return _paste_into_app(payload, dest, field)
            pyautogui.hotkey("ctrl", "v")
            return "Pasted into active window."

        elif action == "copy_and_paste":
            src = (data.get("source") or "").lower().strip()
            copied = text
            if src:
                _launch_and_wait(src, 1.8)
                time.sleep(0.3)
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.2)
                pyautogui.hotkey("ctrl", "c")
                time.sleep(0.2)
                copied = pyperclip.paste()
            if not copied:
                copied = pyperclip.paste()
            if dest:
                return _paste_into_app(copied, dest, field)
            pyperclip.copy(copied)
            pyautogui.hotkey("ctrl", "v")
            return "Copied and pasted."

        elif action == "type_text":
            t = text or query
            if dest:
                _launch_and_wait(dest, 1.8)
                time.sleep(0.2)
                _focus_destination_field(dest, field)
            return _type_text_in_active_field(t)

        elif action == "type_and_search":
            q = query or text
            if not q:
                return "No text to search."
            if dest:
                _launch_and_wait(dest, 1.8)
                time.sleep(0.2)
                _focus_destination_field(dest, field or "search box")
            _type_text_in_active_field(q)
            time.sleep(0.1)
            pyautogui.press("enter")
            return f'Typed and searched: "{q[:50]}"'

        elif action == "hotkey":
            keys = data.get("keys", [])
            if keys:
                pyautogui.hotkey(*keys)
                return data.get("label", "Shortcut executed.")
            return "No keys specified."

        elif action == "scroll_up":
            pyautogui.scroll(500)
            return "Scrolling up."
        elif action == "scroll_down":
            pyautogui.scroll(-500)
            return "Scrolling down."

        elif action == "close_window":
            pyautogui.hotkey("alt", "f4")
            return "Window closed."
        elif action == "minimise":
            pyautogui.hotkey("win", "down")
            return "Minimised."
        elif action == "maximise":
            pyautogui.hotkey("win", "up")
            return "Maximised."
        elif action == "new_tab":
            pyautogui.hotkey("ctrl", "t")
            return "New tab opened."
        elif action == "close_tab":
            pyautogui.hotkey("ctrl", "w")
            return "Tab closed."
        elif action == "switch_tab":
            pyautogui.hotkey("ctrl", "tab")
            return "Switched tab."
        elif action == "go_back":
            pyautogui.hotkey("alt", "left")
            return "Went back."
        elif action == "go_forward":
            pyautogui.hotkey("alt", "right")
            return "Went forward."
        elif action == "refresh":
            pyautogui.hotkey("ctrl", "r")
            return "Refreshed."
        elif action == "focus_address_bar":
            pyautogui.hotkey("ctrl", "l")
            return "Address bar focused."
        elif action == "select_all":
            pyautogui.hotkey("ctrl", "a")
            return "Selected all."
        elif action == "undo":
            pyautogui.hotkey("ctrl", "z")
            return "Undone."
        elif action == "redo":
            pyautogui.hotkey("ctrl", "y")
            return "Redone."
        elif action == "save":
            pyautogui.hotkey("ctrl", "s")
            return "Saved."
        elif action == "find":
            pyautogui.hotkey("ctrl", "f")
            if query:
                time.sleep(0.2)
                _type_text_in_active_field(query)
            return f"Find: {query}" if query else "Find box opened."

        elif action == "volume_up":
            pyautogui.press("volumeup")
            return "Volume up."
        elif action == "volume_down":
            pyautogui.press("volumedown")
            return "Volume down."
        elif action == "mute":
            pyautogui.press("volumemute")
            return "Muted."
        elif action == "play_pause":
            pyautogui.press("playpause")
            return "Play / pause."
        elif action == "next_track":
            pyautogui.press("nexttrack")
            return "Next track."
        elif action == "prev_track":
            pyautogui.press("prevtrack")
            return "Previous track."

        elif action == "screenshot":
            pyautogui.screenshot().save("screenshot.png")
            return "Screenshot saved as screenshot.png."

        elif action == "cancel":
            stop_speaking()
            return "Stopped."

        elif action == "read_screen":
            try:
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                return f"Active window: {buf.value.strip() or 'unknown'}."
            except Exception as ex:
                return f"Could not read screen: {ex}"

        elif action == "exit":
            return "__EXIT__"

        elif action == "converse":
            return "Conversation only."

        return f"I don't know that action yet: {action}"

    except Exception as ex:
        return f"Command failed: {ex}"

# ── GPT brain ──────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are Lia, a smart hands-free AI desktop assistant built for accessibility.
Users may have NO ARMS or be BLIND — they rely entirely on your voice output and you executing tasks for them.
NEVER ask the user to touch the mouse or keyboard. You do everything for them.
ALWAYS respond with a single valid JSON object. Never plain text outside JSON.

FULL JSON SCHEMA:
{
  "action":      "...",         // required — see actions below
  "target":      "...",         // app name (for open_app, search)
  "query":       "...",         // search query or URL
  "text":        "...",         // exact text to copy / type / paste
  "destination": "...",         // app name where text should land
  "source":      "...",         // app name to copy FROM
  "field":       "...",         // hint: "address bar" / "search box" / "body"
  "keys":        ["ctrl","c"],  // for hotkey action
  "label":       "...",         // human label for hotkey result
  "task":        "...",         // full instruction for agent mode
  "reply":       "..."          // ALWAYS include — what Lia speaks aloud
}

ACTIONS AVAILABLE:
  open_app          — open any installed app by name
  search            — search inside an app or browser (no mouse needed)
  open_website      — open a URL in default browser
  copy_text         — copy given text to clipboard, optionally paste to destination
  paste             — paste clipboard into destination app
  copy_and_paste    — copy from source app and paste into destination app
  type_text         — type text into currently focused field (or destination app)
  type_and_search   — type text and press Enter (for search boxes)
  hotkey            — any keyboard shortcut
  scroll_up/down    — scroll the active window
  volume_up/down/mute/play_pause/next_track/prev_track
  screenshot        — save screenshot
  close_window/minimise/maximise/new_tab/close_tab/switch_tab
  go_back/go_forward/refresh/focus_address_bar/select_all/undo/redo/save/find
  agent             — a multi-step job needing eyes and mouse/keyboard
  converse          — no system task, just answer the question
  exit              — close NeuroLia

EXAMPLES:

"open chrome"
→ {"action":"open_app","target":"chrome","reply":"Opening Chrome for you."}

"open vs code"
→ {"action":"open_app","target":"vs code","reply":"Opening Visual Studio Code."}

"search python tutorials on chrome"
→ {"action":"search","target":"chrome","query":"python tutorials","reply":"Searching Chrome for python tutorials — no mouse needed."}

"search lofi music on spotify"
→ {"action":"search","target":"spotify","query":"lofi music","reply":"Searching Spotify for lofi music."}

"open youtube and search drake"
→ {"action":"search","target":"youtube","query":"drake","reply":"Opening YouTube and searching for Drake."}

"go to facebook"
→ {"action":"open_website","query":"facebook.com","reply":"Opening Facebook."}

"open netflix"
→ {"action":"open_website","query":"netflix.com","reply":"Opening Netflix in your browser."}

"copy the text hello world and paste it in notepad"
→ {"action":"copy_text","text":"hello world","destination":"notepad","reply":"Copying that text, opening Notepad, and pasting it in for you."}

"copy my email address alex@example.com into word"
→ {"action":"copy_text","text":"alex@example.com","destination":"word","reply":"Copied your email and pasting it into Word."}

"type my name is Alex in the search box"
→ {"action":"type_and_search","query":"my name is Alex","reply":"Typing and searching for that now."}

"copy everything in notepad and paste it in word"
→ {"action":"copy_and_paste","source":"notepad","destination":"word","reply":"Copying everything from Notepad and pasting into Word."}

"paste what I copied into outlook"
→ {"action":"paste","destination":"outlook","reply":"Opening Outlook and pasting your clipboard content."}

"what is machine learning"
→ {"action":"converse","reply":"Machine learning is a branch of AI where computers learn from data without being explicitly programmed for each task."}

"goodbye"
→ {"action":"exit","reply":"Goodbye! Have a great day."}
"""

_history = []

def ask_gpt(user_input: str, name: str = "") -> dict:
    global _history
    if GPT_OK and OPENAI_KEY != "YOUR_OPENAI_API_KEY_HERE":
        client = OpenAI(api_key=OPENAI_KEY)
        if not _history:
            _history.append({"role":"system","content":SYSTEM_PROMPT})
        prompt = f"[User: {name}] {user_input}" if name else user_input
        _history.append({"role":"user","content":prompt})
        try:
            resp = client.chat.completions.create(
                model="gpt-4o", messages=_history,
                max_tokens=300, temperature=0.5)
            raw = (resp.choices[0].message.content or "").strip()
            _history.append({"role":"assistant","content":raw})
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                if m:
                    return json.loads(m.group(0))
                return _local_parse(user_input)
        except Exception:
            return _local_parse(user_input)
    return _local_parse(user_input)

def _local_parse(cmd: str) -> dict:
    """Full keyword parser — no OpenAI needed."""
    c = cmd.lower().strip()

    # try engine parser first (handles sequences, open+search, etc.)
    engine_result = parse_command(cmd)
    if engine_result and engine_result.get("action") != "sequence":
        # add a reply if missing
        if not engine_result.get("reply"):
            action = engine_result.get("action", "")
            target = engine_result.get("target", "")
            query  = engine_result.get("query", "")
            if action == "open_app":
                engine_result["reply"] = f"Opening {target.title()}."
            elif action == "open_website":
                engine_result["reply"] = f"Opening {query or target}."
            elif action == "search":
                engine_result["reply"] = f"Searching {target.title()} for {query}."
            else:
                engine_result["reply"] = "Done."
        return engine_result

    # copy everything from X into Y  (must come before plain copy X+paste)
    m = re.search(r"copy\s+(?:everything\s+)?(?:from\s+)?(.+?)\s+(?:and\s+)?(?:paste|put)\s+(?:it\s+)?(?:in|to|into)\s+(.+)", c)
    if m:
        src, dst = m.group(1).strip(), m.group(2).strip()
        # if src looks like literal text (not an app name), treat as copy_text
        _, app_target = find_app(src)
        if app_target:
            return {"action": "copy_and_paste", "source": src, "destination": dst,
                    "reply": f"Copying from {src.title()} and pasting into {dst.title()}."}
        return {"action": "copy_text", "text": src, "destination": dst,
                "reply": f"Copying '{src}' and pasting into {dst.title()}."}

    # paste into Y
    m = re.search(r"paste\s+(?:it\s+)?(?:in|to|into)\s+(.+)", c)
    if m:
        dst = m.group(1).strip()
        return {"action": "paste", "destination": dst, "reply": f"Pasting into {dst.title()}."}

    if re.search(r"\bpaste\b", c):
        return {"action": "paste", "reply": "Pasted."}

    # copy X
    m = re.search(r"\bcopy\s+(.+)", c)
    if m:
        txt = m.group(1).strip()
        return {"action": "copy_text", "text": txt, "reply": f"Copied: {txt}."}

    # search X on/in Y
    m = re.search(r"search(?:\s+for)?\s+(.+?)\s+(?:on|in|using|with)\s+([\w\s]+)", c)
    if m:
        q, eng = m.group(1).strip(), m.group(2).strip()
        return {"action": "search", "query": q, "target": eng,
                "reply": f"Searching {eng.title()} for {q}."}

    # search X
    m = re.search(r"search(?:\s+for)?\s+(.+)", c)
    if m:
        q = m.group(1).strip()
        return {"action": "search", "query": q, "target": "chrome",
                "reply": f"Searching for {q}."}

    # go to / visit website
    m = re.search(r"(?:go to|visit)\s+([\w\.-]+\.(?:com|org|net|co|io|tv|app)[\w/]*)", c)
    if m:
        url = m.group(1).strip()
        return {"action": "open_website", "query": url, "reply": f"Opening {url}."}

    # volume controls
    if re.search(r"(?:turn|set)\s+(?:the\s+)?volume\s+(?:up|higher|louder)", c):
        return {"action": "volume_up", "reply": "Turning the volume up."}
    if re.search(r"(?:turn|set)\s+(?:the\s+)?volume\s+(?:down|lower|quieter)", c):
        return {"action": "volume_down", "reply": "Turning the volume down."}
    if re.search(r"\b(?:mute|silence)\b", c):
        return {"action": "mute", "reply": "Muting the volume."}

    # type X into Y
    m = re.search(r"\btype\s+(.+?)\s+(?:in|into|on)\s+(.+)", c)
    if m:
        txt, dst = m.group(1).strip(), m.group(2).strip()
        return {"action": "type_text", "text": txt, "destination": dst,
                "reply": f"Typing '{txt}' into {dst.title()}."}

    # type X
    m = re.search(r"\btype\s+(.+)", c)
    if m:
        txt = m.group(1).strip()
        return {"action": "type_text", "text": txt, "reply": f"Typing: {txt}."}

    # simple one-word commands (scroll, save, undo, etc.)
    simple = match_simple_command(c)
    if simple:
        return simple

    # open app — last resort so it doesn't swallow other commands
    m = re.search(r"(?:open|launch|start)\s+(.+?)(?:\s+(?:for me|please|now))?$", c)
    if m:
        app = m.group(1).strip()
        app = re.sub(r"\s+(?:for me|please|now)$", "", app).strip()
        name2, _ = find_app(app)
        return {"action": "open_app", "target": app,
                "reply": f"Opening {(name2 or app).title()} for you."}

    return {"action": "converse", "reply": f"I heard: \"{cmd}\". Could you be more specific?"}

# ─────────────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class LiaApp(ctk.CTk):
    def __init__(self, profile: dict):
        super().__init__()
        self.profile      = profile
        self.uname        = profile.get("name","")
        self.disabilities = profile.get("disabilities",["none"])
        self.is_blind     = "blind"    in self.disabilities
        self.is_handless  = "handless" in self.disabilities or \
                            "mute"     in self.disabilities
        self.is_deaf      = "deaf"     in self.disabilities

        self.title("NeuroLia")
        self.geometry("980x700")
        self.minsize(820,600)
        self.configure(fg_color=C["bg"])

        self._cam_active  = False
        self._always_on   = True   # always-on voice
        self._listening   = False
        self._wake_active = True
        self._confirmation_gate = ConfirmationGate()
        self._confirmation_lock = threading.Lock()
        self._agent = None
        self._agent_busy = False
        self._agent_consent = False
        self._answer_q = None
        self._awaiting_until = 0.0

        self._build()
        self.after(400,  self._greet)
        self.after(1200, self._start_always_on_voice)
        if CAM_OK and not self.is_blind:
            self.after(800, self._start_camera)

        self.protocol("WM_DELETE_WINDOW", self._quit)
        # silence Tcl's "invalid command name" noise on close
        self.tk.call("proc", "bgerror", "msg", "")

    # ── helpers ────────────────────────────────────────────────────────────────
    def _f(self, sz=13, w="normal"):
        return ctk.CTkFont(family="Helvetica", size=sz, weight=w)

    def _card(self, parent, **kw):
        return ctk.CTkFrame(parent, fg_color=C["card"], corner_radius=12,
                            border_width=1, border_color=C["border"], **kw)

    # ── BUILD ──────────────────────────────────────────────────────────────────
    def _build(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)
        self._build_left()
        self._build_right()

    def _build_left(self):
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(14,6), pady=14)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # ── head panel ────────────────────────────────────────────────────────
        head = ctk.CTkFrame(left, fg_color=C["panel"], corner_radius=14,
                            border_width=1, border_color=C["border"])
        head.grid(row=0, column=0, sticky="ew", pady=(0,8))

        hi = ctk.CTkFrame(head, fg_color="transparent")
        hi.pack(fill="x", padx=18, pady=14)

        # Lia face canvas
        self.face_cv = tk.Canvas(hi, width=72, height=72,
                                  bg=C["panel"], highlightthickness=0)
        self.face_cv.pack(side="left", padx=(0,16))
        self._draw_face("idle")

        right_col = ctk.CTkFrame(hi, fg_color="transparent")
        right_col.pack(side="left", fill="x", expand=True)

        self.lbl_status = ctk.CTkLabel(right_col, text="Standing by",
                                        font=self._f(18,"bold"),
                                        text_color=C["text"])
        self.lbl_status.pack(anchor="w")

        self.lbl_sub = ctk.CTkLabel(right_col,
                                     text="Always listening — just speak",
                                     font=self._f(11), text_color=C["dim"])
        self.lbl_sub.pack(anchor="w", pady=(2,6))

        # always-on indicator
        ao_row = ctk.CTkFrame(right_col, fg_color="transparent")
        ao_row.pack(anchor="w")

        self.ao_dot = ctk.CTkLabel(ao_row, text="● Always-on voice",
                                    font=self._f(10,"bold"),
                                    text_color=C["teal"])
        self.ao_dot.pack(side="left")

        if self.is_blind or self.is_handless:
            ctk.CTkLabel(ao_row,
                         text="  |  Hands-free mode",
                         font=self._f(10),
                         text_color=C["amber"]).pack(side="left")

        # ── feed ──────────────────────────────────────────────────────────────
        feed_wrap = ctk.CTkFrame(left, fg_color=C["panel"],
                                  corner_radius=14, border_width=1,
                                  border_color=C["border"])
        feed_wrap.grid(row=1, column=0, sticky="nsew", pady=(0,8))
        feed_wrap.grid_rowconfigure(0, weight=1)
        feed_wrap.grid_columnconfigure(0, weight=1)

        self.feed = ctk.CTkScrollableFrame(feed_wrap, fg_color="transparent",
                                            scrollbar_button_color=C["border"])
        self.feed.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        # ── input bar ─────────────────────────────────────────────────────────
        bar = ctk.CTkFrame(left, fg_color=C["panel"], corner_radius=14,
                           border_width=1, border_color=C["border"])
        bar.grid(row=2, column=0, sticky="ew")

        bi = ctk.CTkFrame(bar, fg_color="transparent")
        bi.pack(fill="x", padx=10, pady=10)

        self.entry = ctk.CTkEntry(bi, height=42,
                                   placeholder_text="Type or speak — Lia is always listening...",
                                   fg_color=C["card"],
                                   border_color=C["border"],
                                   text_color=C["text"],
                                   font=self._f(12))
        self.entry.pack(side="left", fill="x", expand=True, padx=(0,8))
        self.entry.bind("<Return>", lambda e: self._send_text())

        ctk.CTkButton(bi, text="Send", width=68, height=42,
                      corner_radius=10, fg_color=C["purple"],
                      hover_color=C["pur_dim"], font=self._f(12,"bold"),
                      command=self._send_text).pack(side="left", padx=(0,6))

        # mic status badge (shows state, not a button)
        self.mic_badge = ctk.CTkLabel(bi, text="🎤 ON",
                                       font=self._f(10,"bold"),
                                       text_color=C["teal"])
        self.mic_badge.pack(side="left")

    def _build_right(self):
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(0,14), pady=14)
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        # ── camera panel ──────────────────────────────────────────────────────
        cam_hdr = ctk.CTkFrame(right, fg_color="transparent")
        cam_hdr.grid(row=0, column=0, sticky="ew", pady=(0,6))
        ctk.CTkLabel(cam_hdr, text="Camera — gesture control",
                     font=self._f(12,"bold"), text_color=C["text"]).pack(side="left")
        self.cam_status = ctk.CTkLabel(cam_hdr, text="● Starting",
                                        font=self._f(10), text_color=C["amber"])
        self.cam_status.pack(side="right")

        cam_wrap = ctk.CTkFrame(right, fg_color=C["card"],
                                corner_radius=12, border_width=1,
                                border_color=C["border"])
        cam_wrap.grid(row=1, column=0, sticky="nsew", pady=(0,8))
        cam_wrap.grid_rowconfigure(0, weight=1)
        cam_wrap.grid_columnconfigure(0, weight=1)

        self.cam_lbl = ctk.CTkLabel(cam_wrap,
                                     text="📷  Camera loading...\n\nMake sure opencv-python\nand mediapipe are installed",
                                     font=self._f(11), text_color=C["dim"])
        self.cam_lbl.grid(row=0, column=0, sticky="nsew")

        # ── gestures legend ───────────────────────────────────────────────────
        gl = self._card(right)
        gl.grid(row=2, column=0, sticky="ew", pady=(0,8))
        gi = ctk.CTkFrame(gl, fg_color="transparent")
        gi.pack(fill="x", padx=12, pady=10)
        ctk.CTkLabel(gi, text="GESTURES", font=self._f(10,"bold"),
                     text_color=C["dim"]).pack(anchor="w", pady=(0,6))
        for g, a in [("✋ Swipe right","New tab"),("✋ Swipe left","Close tab"),
                     ("↕ Head nod","Scroll up"),("↔ Head left","Scroll down")]:
            r = ctk.CTkFrame(gi, fg_color="transparent")
            r.pack(fill="x", pady=1)
            ctk.CTkLabel(r, text=g, font=self._f(10), text_color=C["dim"]).pack(side="left")
            ctk.CTkLabel(r, text=a, font=self._f(10), text_color=C["purple"]).pack(side="right")

        # ── quick apps ────────────────────────────────────────────────────────
        qa = self._card(right)
        qa.grid(row=3, column=0, sticky="ew", pady=(0,8))
        qai = ctk.CTkFrame(qa, fg_color="transparent")
        qai.pack(fill="x", padx=12, pady=10)
        ctk.CTkLabel(qai, text="QUICK OPEN", font=self._f(10,"bold"),
                     text_color=C["dim"]).pack(anchor="w", pady=(0,6))

        apps_grid = ctk.CTkFrame(qai, fg_color="transparent")
        apps_grid.pack(fill="x")

        quick = [("Chrome","chrome"),("Edge","edge"),("Spotify","spotify"),
                 ("VS Code","vs code"),("WhatsApp","whatsapp"),("Notepad","notepad"),
                 ("Word","word"),("PowerPoint","powerpoint"),("Outlook","outlook"),
                 ("Teams","teams"),("Instagram","instagram"),("TikTok","tiktok"),
                 ("Copilot","copilot"),("Store","microsoft store")]

        for i,(label,cmd) in enumerate(quick):
            ctk.CTkButton(apps_grid, text=label, height=28,
                          corner_radius=6, fg_color=C["panel"],
                          hover_color=C["border"], border_width=1,
                          border_color=C["border"], font=self._f(10),
                          text_color=C["text"],
                          command=lambda c=cmd: self._run(f"open {c}")
                          ).grid(row=i//3, column=i%3,
                                 padx=2, pady=2, sticky="ew")

        apps_grid.grid_columnconfigure(0, weight=1)
        apps_grid.grid_columnconfigure(1, weight=1)
        apps_grid.grid_columnconfigure(2, weight=1)

    # ── FACE DRAWING ───────────────────────────────────────────────────────────
    def _draw_face(self, state="idle"):
        cv = self.face_cv; cv.delete("all")
        cx,cy,r = 36,36,30
        ring = {"idle":C["border"],"listening":C["purple"],
                "thinking":C["amber"],"speaking":C["teal"],
                "error":C["coral"]}.get(state,C["border"])
        cv.create_oval(cx-r,cy-r,cx+r,cy+r, outline=ring, width=2, fill=C["card"])
        if state=="listening":
            for pr in [r+7,r+14]:
                cv.create_oval(cx-pr,cy-pr,cx+pr,cy+pr, outline=ring, width=1)
        eye = C["text"] if state!="error" else C["coral"]
        if state=="thinking":
            cv.create_line(cx-9,cy-5,cx-3,cy-5, fill=eye, width=2, capstyle="round")
            cv.create_line(cx+3,cy-5,cx+9,cy-5, fill=eye, width=2, capstyle="round")
        else:
            cv.create_oval(cx-10,cy-8,cx-4,cy-2, fill=eye, outline="")
            cv.create_oval(cx+4, cy-8,cx+10,cy-2, fill=eye, outline="")
        if state in ("speaking","idle"):
            cv.create_arc(cx-9,cy+3,cx+9,cy+13, start=200,extent=140,
                          outline=eye, width=2, style="arc")
        elif state=="listening":
            cv.create_line(cx-7,cy+8,cx+7,cy+8, fill=eye, width=2, capstyle="round")
        elif state=="error":
            cv.create_arc(cx-9,cy+9,cx+9,cy+17, start=20,extent=140,
                          outline=eye, width=2, style="arc")
        dot = ring if state!="idle" else C["muted"]
        cv.create_oval(cx+18,cy+18,cx+26,cy+26, fill=dot, outline="")

    def _set_state(self, state, title, sub=""):
        self._draw_face(state)
        self.lbl_status.configure(text=title)
        self.lbl_sub.configure(text=sub)

    # ── FEED MESSAGES ──────────────────────────────────────────────────────────
    def _msg(self, who, text):
        is_lia = who=="lia"
        outer = ctk.CTkFrame(self.feed, fg_color="transparent")
        outer.pack(fill="x", pady=3, padx=8)

        row = ctk.CTkFrame(outer, fg_color="transparent")
        row.pack(fill="x", anchor="w" if is_lia else "e")

        if is_lia:
            dot = ctk.CTkFrame(row, width=26,height=26, corner_radius=13,
                               fg_color=C["pur_dim"])
            dot.pack(side="left", padx=(0,6), anchor="n")
            dot.pack_propagate(False)
            ctk.CTkLabel(dot,text="L",font=self._f(10,"bold"),
                         text_color=C["purple"]).place(relx=.5,rely=.5,anchor="center")
            bub = ctk.CTkFrame(row, fg_color=C["card"], corner_radius=10,
                               border_width=1, border_color=C["border"])
            bub.pack(side="left")
        else:
            bub = ctk.CTkFrame(row, fg_color=C["pur_dim"], corner_radius=10)
            bub.pack(side="right")

        ctk.CTkLabel(bub, text=text, font=self._f(12),
                     text_color=C["text"], wraplength=300,
                     justify="left").pack(padx=12, pady=8)

        ctk.CTkLabel(outer, text=time.strftime("%H:%M"),
                     font=self._f(9), text_color=C["muted"]
                     ).pack(anchor="w" if is_lia else "e", padx=4)

        self.feed.after(60, lambda: self.feed._parent_canvas.yview_moveto(1.0))

    def _log(self, text, status="success"):
        clr = {"success":(C["teal_dim"],C["teal"]),
               "error":("#3d1010",C["coral"]),
               "info":(C["blue_dim"],C["blue"]),
               "gesture":("#2a1a50",C["purple"])}.get(status,(C["card"],C["dim"]))
        icon = {"success":"✔","error":"✘","info":"◈","gesture":"👋"}.get(status,"•")
        f = ctk.CTkFrame(self.feed, fg_color=clr[0], corner_radius=8)
        f.pack(fill="x", pady=2, padx=8)
        ctk.CTkLabel(f, text=f" {icon}  {text}", font=self._f(11),
                     text_color=clr[1]).pack(anchor="w", padx=10, pady=5)
        self.feed.after(60, lambda: self.feed._parent_canvas.yview_moveto(1.0))

    # ── GREET ──────────────────────────────────────────────────────────────────
    def _greet(self):
        n = self.uname
        g = (f"Hello {n}! I'm Lia. I'm always listening — just speak or type."
             if n else
             "Hello! I'm Lia. I'm always listening — just speak or type.")
        if self.is_handless:
            g += " Hands-free mode is active — no mouse or keyboard needed."
        if self.is_blind:
            g += " I will read everything on screen for you."
        self._set_state("speaking","Greeting...",g[:50])
        self._msg("lia", g)
        speak(g)
        self.after(4000, lambda: self._set_state(
            "idle","Standing by","Always listening — just speak"))

    # ── ALWAYS-ON VOICE (no button needed) ────────────────────────────────────
    def _start_always_on_voice(self):
        if not SR_OK or self.is_deaf:
            self._log("SpeechRecognition not installed — type instead", "error")
            return

        def engine():
            rec = sr.Recognizer()
            rec.dynamic_energy_threshold = False
            WAKE = re.compile(r"\b(lia|lea|leah|liya)\b", re.IGNORECASE)

            # ── one-time calibration ──────────────────────────────────────────
            self.after(0, lambda: self._log("Calibrating microphone...", "info"))
            self.after(0, lambda: self.mic_badge.configure(
                text="Calibrating", text_color=C["amber"]))
            calibrated = 300
            try:
                with sr.Microphone() as src:
                    rec.adjust_for_ambient_noise(src, duration=1.5)
                    calibrated = max(rec.energy_threshold * 1.2, 200)
                    rec.energy_threshold = calibrated
            except Exception:
                rec.energy_threshold = calibrated

            self.after(0, lambda v=int(calibrated): self._log(
                f"Ready — threshold {v}. Say 'Lia' to wake me.", "info"))
            self.after(0, lambda: self.mic_badge.configure(
                text="Waiting for 'Lia'", text_color=C["teal"]))
            self.after(0, lambda: self._set_state(
                "idle", "Standing by", "Say 'Lia' to wake me up"))

            while self._wake_active:
                # ── PHASE 1: wake-word gate ───────────────────────────────────
                try:
                    with sr.Microphone() as src:
                        rec.energy_threshold = calibrated
                        wake_audio = rec.listen(src, timeout=8, phrase_time_limit=4)
                except sr.WaitTimeoutError:
                    continue
                except Exception:
                    time.sleep(0.5)
                    continue

                try:
                    heard = rec.recognize_google(wake_audio, language="en-US").lower().strip()
                except sr.UnknownValueError:
                    continue
                except sr.RequestError:
                    self.after(0, lambda: self._log("No internet — check connection", "error"))
                    time.sleep(3)
                    continue

                # check if the wake word was in the clip
                if not WAKE.search(heard):
                    continue

                # strip wake word — if a command followed it inline, use it directly
                inline = WAKE.sub("", heard).strip().lstrip(",. ")

                self.after(0, lambda h=heard: self._log(f'Wake: "{h}"', "info"))
                self.after(0, lambda: self.mic_badge.configure(
                    text="Listening...", text_color=C["purple"]))
                self.after(0, lambda: self._set_state(
                    "listening", "Listening...", "Go ahead, I'm ready"))
                speak("Yes?")

                if inline and len(inline) >= 2:
                    # command was spoken in the same breath as the wake word
                    self.after(0, lambda t=inline: self._run(t))
                    self.after(0, lambda: self.mic_badge.configure(
                        text="Waiting for 'Lia'", text_color=C["teal"]))
                    continue

                # ── PHASE 2: command listen ───────────────────────────────────
                # wait for TTS "Yes?" to finish before opening mic
                time.sleep(0.8)
                try:
                    with sr.Microphone() as src:
                        rec.adjust_for_ambient_noise(src, duration=0.4)
                        rec.energy_threshold = max(rec.energy_threshold * 1.1, calibrated * 0.8)
                        self.after(0, lambda: self.mic_badge.configure(
                            text="Recording...", text_color=C["coral"]))
                        cmd_audio = rec.listen(src, timeout=7, phrase_time_limit=12)
                except sr.WaitTimeoutError:
                    self.after(0, lambda: self._log("No command heard — say 'Lia' again", "error"))
                    speak("I didn't hear a command. Say Lia when you're ready.")
                    self.after(0, lambda: self._set_state(
                        "idle", "Standing by", "Say 'Lia' to wake me up"))
                    self.after(0, lambda: self.mic_badge.configure(
                        text="Waiting for 'Lia'", text_color=C["teal"]))
                    continue
                except Exception:
                    time.sleep(0.5)
                    continue

                self.after(0, lambda: self.mic_badge.configure(
                    text="Processing...", text_color=C["amber"]))
                self.after(0, lambda: self._set_state(
                    "thinking", "Processing...", "Just a moment"))

                try:
                    command = rec.recognize_google(cmd_audio, language="en-US").strip()
                except sr.UnknownValueError:
                    self.after(0, lambda: self._log("Couldn't understand — try again", "error"))
                    self.after(0, lambda: self._set_state(
                        "error", "Didn't catch that", "Say 'Lia' to try again"))
                    speak("Sorry, I didn't catch that. Say Lia to try again.")
                    self.after(0, lambda: self._set_state(
                        "idle", "Standing by", "Say 'Lia' to wake me up"))
                    self.after(0, lambda: self.mic_badge.configure(
                        text="Waiting for 'Lia'", text_color=C["teal"]))
                    continue
                except sr.RequestError:
                    self.after(0, lambda: self._log("No internet connection", "error"))
                    time.sleep(3)
                    continue

                if not command or len(command.strip()) < 2:
                    continue

                # strip any leading wake word from the command
                clean = WAKE.sub("", command).strip().lstrip(",. ")
                if not clean:
                    speak("I'm listening. What would you like me to do?")
                    continue

                self.after(0, lambda c=clean: self._log(f'Command: "{c}"', "success"))
                self.after(0, lambda: self.mic_badge.configure(
                    text="Waiting for 'Lia'", text_color=C["teal"]))
                self.after(0, lambda t=clean: self._run(t))

        threading.Thread(target=engine, daemon=True).start()

    def _wake_ack(self):
        # kept for compatibility — no longer called directly
        pass

    # ── PROCESS COMMAND ────────────────────────────────────────────────────────
    def _run(self, user_text: str):
        if not user_text.strip():
            return

        if self._answer_q is not None:
            self._msg("user", user_text)
            local = parse_command(user_text)
            if local and local["action"] == "cancel" and self._agent:
                self._agent.cancel()
            self._answer_q.put(user_text)
            return

        self._msg("user", user_text)
        self._set_state("thinking","Thinking...",user_text[:45])

        def process():
            if self._agent_busy:
                local = parse_command(user_text)
                if not (local and local["action"] in ("cancel", "exit")):
                    msg = "I’m busy with a task. Say stop to cancel it."
                    self.ui(self._msg, "lia", msg)
                    speak(msg)
                    return
                data = local
            else:
                confirmation_status, pending_action = self._confirmation_gate.resolve(user_text)
                if confirmation_status == "cancelled":
                    reply = "Cancelled."
                    self.ui(self._msg, "lia", reply)
                    speak(reply)
                    self.ui(self._set_state, "idle", "Standing by", "Always listening — just speak")
                    return
                if confirmation_status == "confirmed":
                    data = pending_action
                elif confirmation_status == "other":
                    return
                else:
                    data = ask_gpt(user_text, self.uname)
            if not isinstance(data, dict):
                reply = "I couldn't safely understand that command."
                self.ui(self._msg, "lia", reply)
                speak(reply)
                self.ui(self._set_state, "idle", "Standing by", "Always listening — just speak")
                return
            data = _normalize_action(data)
            reply = str(data.get("reply") or "Done.")
            action = data.get("action", "converse")

            if not is_allowed(data):
                reply = "I can't safely run that action."
                self.ui(self._msg, "lia", reply)
                speak(reply)
                self.ui(self._log, reply, "error")
                self.ui(self._set_state, "idle", "Standing by", "Always listening — just speak")
                return

            if action == "cancel":
                stop_speaking()
                if self._agent_busy and self._agent:
                    self._agent.cancel()
                self.ui(self._log, "Cancelled", "info")
                self.ui(self._set_state, "idle", "Standing by", "Say 'Lia' then your command")
                return

            self.ui(self._msg, "lia", reply)
            speak(reply)

            if action == "converse":
                pass
            elif action == "exit":
                self.ui(self.after, 1500, self.destroy)
                return
            elif action == "agent":
                self._run_agent(data.get("task") or user_text, bool(data.get("explicit")))
            else:
                if needs_confirmation(data):
                    confirmation = self._confirmation_gate.ask(data)
                    self.ui(self._msg, "lia", confirmation)
                    speak(confirmation)
                    self.ui(self._set_state, "idle", "Standing by", "Say yes to confirm or no to cancel")
                    return
                result = execute(data)
                if result == "__EXIT__":
                    self.ui(self.after, 1500, self.destroy)
                    return
                status = "error" if is_failure_message(result) else "success"
                self.ui(self._log, result, status)
                if self.is_blind:
                    time.sleep(2.5)
                    self.ui(self._blind_read)
                if status == "error" or action == "read_screen":
                    speak(result)

            self.ui(self._set_state, "idle", "Standing by", "Always listening — just speak")

        threading.Thread(target=process, daemon=True).start()

    def ui(self, function, *args):
        self.after(0, lambda: function(*args))

    AGENT_CONSENT = ("Agent mode lets me see your screen and use your mouse and keyboard. "
                     "Screenshots are sent to Anthropic to work out each step. "
                     "Close anything private first. Say yes to allow it for this session, or no.")

    def _agent_say(self, text):
        self.ui(self._msg, "lia", text)
        if _tts_q.empty() and not _speaking.is_set():
            speak(first_sentence(text))

    def _agent_log(self, text):
        self.ui(self._log, text, "info")

    def _agent_ask(self, question):
        self._answer_q = queue.Queue()
        self.ui(self._msg, "lia", question)
        speak(question)
        t0 = time.time()
        while (_speaking.is_set() or not _tts_q.empty()) and time.time() - t0 < 30:
            time.sleep(0.1)
        self._awaiting_until = time.time() + 25
        try:
            return self._answer_q.get(timeout=45)
        except queue.Empty:
            return ""
        finally:
            self._awaiting_until = 0.0
            self._answer_q = None

    def _run_agent(self, task, explicit):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            msg = "Agent mode needs an Anthropic API key. Set ANTHROPIC_API_KEY and restart me."
            self.ui(self._msg, "lia", msg)
            speak(msg)
            return
        if self._agent is None:
            self._agent = LiaAgent(say=self._agent_say, ask=self._agent_ask, log=self._agent_log)
        self._agent_busy = True
        final = ""
        try:
            if not self._agent_consent:
                if not is_yes(self._agent_ask(self.AGENT_CONSENT)):
                    speak("Okay, I won’t.")
                    return
                self._agent_consent = True
            elif not explicit:
                if not is_yes(self._agent_ask(f"That needs me to use your screen: {task[:80]}. Shall I go ahead?")):
                    speak("Okay.")
                    return
            self.ui(self._set_state, "thinking", "Working on it...", task[:45])
            final = self._agent.run(task)
        except AgentUnavailable as ex:
            final = str(ex)
        except Exception as ex:
            final = f"I had to stop: {ex}"
        finally:
            self._agent_busy = False
            self._answer_q = None
        self.ui(self._msg, "lia", final)
        speak(final)
        self.ui(self._set_state, "idle", "Standing by", "Say 'Lia' then your command")

    def _send_text(self):
        t = self.entry.get().strip()
        if t:
            self.entry.delete(0,"end")
            self._run(t)

    # ── BLIND NARRATION ────────────────────────────────────────────────────────
    def _blind_read(self):
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            l    = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            b    = ctypes.create_unicode_buffer(l+1)
            ctypes.windll.user32.GetWindowTextW(hwnd,b,l+1)
            msg = f"Active window is now: {b.value.strip()}."
        except Exception:
            msg = "Action completed."
        self._msg("lia", msg)
        speak(msg)

    # ── CAMERA ─────────────────────────────────────────────────────────────────
    def _start_camera(self):
        if not CAM_OK:
            self.cam_status.configure(text="● Not installed", text_color=C["coral"])
            return
        self._cam_active = True
        self.cam_status.configure(text="● Live", text_color=C["teal"])
        self._pose = PoseRecognizer() if POSE_OK else None
        if self._pose:
            threading.Thread(target=self._load_pose_model, daemon=True).start()
        threading.Thread(target=self._cam_loop, daemon=True).start()

    def _load_pose_model(self):
        ok, msg = self._pose.load()
        self.after(0, lambda: self._log(msg, "success" if ok else "info"))

    def _cam_loop(self):
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            self.after(0, lambda: self.cam_status.configure(
                text="● No camera", text_color=C["coral"]))
            return

        mp_h  = mp.solutions.hands
        mp_fm = mp.solutions.face_mesh
        mp_d  = mp.solutions.drawing_utils
        stabilizer = GestureStabilizer()

        with mp_h.Hands(max_num_hands=1, min_detection_confidence=0.7) as hands, \
             mp_fm.FaceMesh(max_num_faces=1, min_detection_confidence=0.7) as face:

            while self._cam_active:
                ok, frame = cap.read()
                if not ok: break
                frame = cv2.flip(frame,1)
                rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                hr    = hands.process(rgb)
                fr    = face.process(rgb)
                hand_x = None
                hand_landmarks = None
                head_xy = None

                if hr.multi_hand_landmarks:
                    for hl in hr.multi_hand_landmarks:
                        mp_d.draw_landmarks(frame, hl, mp_h.HAND_CONNECTIONS,
                            mp_d.DrawingSpec(color=(140,100,255),thickness=2),
                            mp_d.DrawingSpec(color=(200,170,255),thickness=1))
                        hand_x = hl.landmark[0].x
                        hand_landmarks = hl.landmark

                if fr.multi_face_landmarks:
                    for fl in fr.multi_face_landmarks:
                        nose = fl.landmark[1]
                        head_xy = (nose.x, nose.y)

                det = stabilizer.update(hand_x=hand_x, head_xy=head_xy)
                if self._pose:
                    if hand_landmarks is None:
                        self._pose.lost()
                    elif det is None and self._pose.ready:
                        pose = self._pose.update(hand_landmarks)
                        if pose:
                            det = "pose:" + pose
                if det:
                    self.after(0, lambda g=det: self._gesture(g))

                h2,w2 = frame.shape[:2]
                tw = min(280, w2)
                th = int(h2*tw/w2)
                sm = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), (tw, th))
                ctk_img = ctk.CTkImage(light_image=Image.fromarray(sm), size=(tw, th))
                self.after(0, lambda p=ctk_img: self._show_cam(p))
                time.sleep(0.033)

        cap.release()

    def _show_cam(self, photo):
        if self.cam_lbl.winfo_exists():
            self.cam_lbl.configure(image=photo, text="")
            self.cam_lbl.image = photo

    def _gesture(self, g):
        if g.startswith("pose:"):
            item, kind = POSE_ACTIONS.get(g[5:], None), "hand pose"
        else:
            gmap = {
                "hand_swipe_right": ({"action": "new_tab"}, "New tab"),
                "hand_swipe_left": ({"action": "close_tab"}, "Close tab"),
                "head_nod_up": ({"action": "scroll_up"}, "Scroll up"),
                "head_swipe_left": ({"action": "scroll_down"}, "Scroll down"),
            }
            item, kind = gmap.get(g), "gesture"
        if not item:
            return
        data, label = item
        data = _normalize_action(data)
        if self._agent_busy and data["action"] != "cancel":
            return
        if data["action"] == "cancel":
            try:
                stop_speaking()
            except Exception as ex:
                self._log(f"Could not stop speech: {ex}", "error")
                return
            self._log(f"{label} — {kind}", "info")
            return
        if not is_allowed(data):
            self._log("Gesture action is not allowed.", "error")
            return
        if needs_confirmation(data):
            with self._confirmation_lock:
                prompt = self._confirmation_gate.ask(data)
            self._log(prompt, "info")
            speak(prompt)
            return
        result = execute(data)
        self._log(
            f"{label} — {kind}",
            "error" if is_failure(result) else "success",
        )
        if data["action"] not in QUIET_ACTIONS:
            speak(label)

    # ── QUIT ───────────────────────────────────────────────────────────────────
    def _quit(self):
        self._cam_active  = False
        self._wake_active = False
        if self._agent:
            self._agent.cancel()
        _tts_q.put(None)
        self.destroy()


# ── LOGIN ──────────────────────────────────────────────────────────────────────
class Login(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("NeuroLia")
        self.geometry("400x540")
        self.resizable(False,False)
        self.configure(fg_color=C["bg"])
        self.profile = None
        self._build()

    def _f(self,sz=13,w="normal"):
        return ctk.CTkFont(family="Helvetica",size=sz,weight=w)

    def _build(self):
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.place(relx=.5,rely=.5,anchor="center")

        # logo
        logo = ctk.CTkFrame(wrap, fg_color="transparent")
        logo.pack(pady=(0,20))
        ring = ctk.CTkFrame(logo, width=72, height=72, corner_radius=36,
                            fg_color=C["panel"], border_width=2,
                            border_color=C["purple"])
        ring.pack(pady=(0,10)); ring.pack_propagate(False)
        cv = tk.Canvas(ring,width=72,height=72,bg=C["panel"],highlightthickness=0)
        cv.place(relx=.5,rely=.5,anchor="center")
        cx,cy,r=36,36,26
        cv.create_oval(cx-r,cy-r,cx+r,cy+r,outline=C["purple"],width=2,fill=C["panel"])
        cv.create_oval(cx-8,cy-7,cx-3,cy-2,fill=C["text"],outline="")
        cv.create_oval(cx+3,cy-7,cx+8,cy-2,fill=C["text"],outline="")
        cv.create_arc(cx-7,cy+2,cx+7,cy+11,start=200,extent=140,
                      outline=C["text"],width=2,style="arc")
        ctk.CTkLabel(logo,text="NeuroLia",font=self._f(22,"bold"),
                     text_color=C["text"]).pack()
        ctk.CTkLabel(logo,text="Your intelligent assistant",
                     font=self._f(11),text_color=C["dim"]).pack()

        # card
        card = ctk.CTkFrame(wrap,fg_color=C["panel"],corner_radius=14,
                            border_width=1,border_color=C["border"],width=340)
        card.pack(pady=(0,10)); card.pack_propagate(False)
        ci = ctk.CTkFrame(card,fg_color="transparent")
        ci.pack(fill="both",expand=True,padx=20,pady=20)

        ctk.CTkLabel(ci,text="Name, ID number, or email",
                     font=self._f(11),text_color=C["dim"]).pack(anchor="w",pady=(0,4))
        self.ent = ctk.CTkEntry(ci,height=42,width=300,
                                fg_color=C["card"],border_color=C["border"],
                                text_color=C["text"],font=self._f(13),
                                placeholder_text="e.g. your name")
        self.ent.pack(pady=(0,6))
        self.ent.bind("<KeyRelease>",self._hint)
        self.ent.bind("<Return>",lambda e:self._login())
        self.hint_lbl = ctk.CTkLabel(ci,text="",font=self._f(11),
                                      text_color=C["teal"],height=14)
        self.hint_lbl.pack(anchor="w",pady=(0,10))
        ctk.CTkButton(ci,text="Sign in →",height=42,width=300,corner_radius=10,
                      fg_color=C["purple"],hover_color=C["pur_dim"],
                      font=self._f(13,"bold"),command=self._login).pack()

        # voice
        sep = ctk.CTkFrame(wrap,height=1,fg_color=C["border"],width=340)
        sep.pack(pady=10)
        vc = ctk.CTkFrame(wrap,fg_color=C["panel"],corner_radius=12,
                          border_width=1,border_color=C["border"],width=340)
        vc.pack(); vc.pack_propagate(False)
        vi = ctk.CTkFrame(vc,fg_color="transparent")
        vi.pack(fill="both",expand=True,padx=16,pady=12)
        ctk.CTkLabel(vi,text="🎤  No arms / blind? Voice login",
                     font=self._f(12,"bold"),text_color=C["text"]).pack(anchor="w")
        ctk.CTkLabel(vi,text="Just say your name — no typing needed",
                     font=self._f(10),text_color=C["dim"]).pack(anchor="w",pady=(2,8))
        ctk.CTkButton(vi,text='Activate voice login',height=36,corner_radius=8,
                      fg_color=C["card"],hover_color=C["border"],
                      border_width=1,border_color=C["border"],
                      font=self._f(11),text_color=C["dim"],
                      command=self._voice_login).pack(fill="x")

    def _hint(self, _=None):
        v = self.ent.get().strip().lower().replace(" ","")
        if any(m.replace(" ","").startswith(v[:5]) for m in MASTER_IDS if len(v)>=3):
            self.hint_lbl.configure(text="⚡ Owner recognised",text_color=C["teal"])
        elif len(v)>2:
            self.hint_lbl.configure(text="Looking up...",text_color=C["dim"])
        else:
            self.hint_lbl.configure(text="")

    def _login(self):
        v = self.ent.get().strip().lower().replace(" ","")
        if not v: return
        owner = any(v==m.replace(" ","") or
                    (len(v)>=5 and m.replace(" ","").startswith(v[:5]))
                    for m in MASTER_IDS)
        self.profile = {"name":OWNER_NAME if owner else v.capitalize(),
                        "disabilities":["none"],
                        "input_mode":"voice+gesture+gpt+camera",
                        "role":"owner" if owner else "user"}
        self.destroy()

    def _voice_login(self):
        if not SR_OK:
            self.hint_lbl.configure(text="speechrecognition not installed",
                                     text_color=C["coral"])
            return
        self.hint_lbl.configure(text="🎤 Listening for your name...",
                                 text_color=C["amber"])
        def listen():
            r = sr.Recognizer()
            try:
                with sr.Microphone() as s:
                    r.adjust_for_ambient_noise(s,duration=0.5)
                    audio = r.listen(s,timeout=6,phrase_time_limit=5)
                name_heard = r.recognize_google(audio).strip()
                v = name_heard.lower().replace(" ","")
                owner = any(m.replace(" ","").startswith(v[:5]) for m in MASTER_IDS)
                self.profile = {
                    "name":OWNER_NAME if owner else name_heard.split()[0].capitalize(),
                    "disabilities":["none"],
                    "input_mode":"voice+gesture+gpt+camera",
                    "role":"owner" if owner else "user"}
                self.after(0, self.destroy)
            except Exception as ex:
                self.after(0, lambda: self.hint_lbl.configure(
                    text=f"Didn't catch that — try again",text_color=C["coral"]))
        threading.Thread(target=listen, daemon=True).start()


def main():
    login = Login()
    login.mainloop()
    if not login.profile:
        return
    app = LiaApp(login.profile)
    app.mainloop()

if __name__ == "__main__":
    main()