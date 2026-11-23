from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
import argparse
import tempfile
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime


class NeuroLia(tk.Tk):
    def __init__(self, out_path: Path, verbose: bool = False):
        super().__init__()
        self.out_path = out_path
        self.verbose = verbose
        # Default save file (rolling single file)
        self.save_file_path = self.out_path.parent / "saved_text.txt"
        self.title("NeuroLia Prototype")
        self.geometry("600x320")
        label = tk.Label(self, text="NeuroLia Prototype", font=("Segoe UI", 16))
        label.pack(pady=10)

        # Small text area for user input
        self.text = tk.Text(self, height=10, width=70)
        self.text.pack(padx=10, pady=5)

        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=8)

        save_btn = tk.Button(btn_frame, text="Save Text", command=self.save_text)
        save_btn.pack(side=tk.LEFT, padx=6)

        quit_btn = tk.Button(btn_frame, text="Quit", command=self.destroy)
        quit_btn.pack(side=tk.LEFT, padx=6)

        # Menu to choose save filename
        menubar = tk.Menu(self)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Choose Save File...", command=self.choose_save_file)
        filemenu.add_command(label="Show Current Save File", command=self.show_save_file)
        menubar.add_cascade(label="File", menu=filemenu)
        self.config(menu=menubar)

    def save_text(self):
        content = self.text.get("1.0", tk.END).rstrip()
        # Ensure save directory exists
        self.save_file_path.parent.mkdir(parents=True, exist_ok=True)
        # Append content to the single rolling save file
        with self.save_file_path.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}]\n")
            f.write(content)
            f.write("\n---\n")

        logging.info(f"Saved GUI text to: {self.save_file_path}")
        if self.verbose:
            print(f"Saved GUI text to: {self.save_file_path}")

    def choose_save_file(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=self.save_file_path.name)
        if path:
            self.save_file_path = Path(path)
            logging.info(f"User selected save file: {self.save_file_path}")

    def show_save_file(self):
        messagebox.showinfo("Current Save File", str(self.save_file_path))


def main():
    parser = argparse.ArgumentParser(description="NeuroLia prototype")
    parser.add_argument("--no-gui", action="store_true", help="Skip launching the Tk GUI")
    parser.add_argument("--out", help="Output path for the prototype file")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    # Read this file's source
    src = Path(__file__).read_text(encoding="utf-8")

    # Determine a Windows-friendly default output path if none provided
    if args.out:
        out_path = Path(args.out)
    else:
        tmp = tempfile.gettempdir()
        out_path = Path(tmp) / "neurolia_prototype.py"

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Configure rotating file logging
    log_file = out_path.parent / "neurolia.log"
    rhandler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    rhandler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    handlers = [rhandler]
    if args.verbose:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(level=logging.INFO, handlers=handlers)
    logging.info("Starting NeuroLia prototype run")

    out_path.write_text(src, encoding="utf-8")
    out_path.write_text(src, encoding="utf-8")
    print(f"Prototype lines: {len(src.splitlines())}")
    logging.info(f"Wrote prototype to: {out_path}")

    if args.no_gui:
        print("--no-gui specified: skipping GUI launch")
        logging.info("--no-gui specified: skipping GUI launch")
        out_path.write_text(src, encoding="utf-8")
        logging.info("Final write complete (no-gui)")
        return

    try:
        app = NeuroLia(out_path, verbose=args.verbose)
    except tk.TclError as e:
        print("Tkinter GUI unavailable:", e)
        logging.error(f"Tkinter GUI unavailable: {e}")
        out_path.write_text(src, encoding="utf-8")
        logging.info("Final write complete (no display)")
        return

    app.mainloop()

    # Final write after the GUI closes (matches the original snippet intent).
    out_path.write_text(src, encoding="utf-8")
    logging.info("Final write complete (after GUI exit)")


if __name__ == "__main__":
    main()
"""
NeuroLia Accessibility Prototype
--------------------------------
A Windows-first multimodal accessibility assistant.

Features:
- Voice commands with wake word "NeuroLia"
- Voice copy/paste/type/open/search controls
- Hand gestures:
    Fist -> volume down
    Open palm -> volume up
    Swipe right -> next tab
    Swipe left -> close tab
    Hand wave up -> scroll up
    Hand wave down -> scroll down
    Thumbs up -> confirm
    Thumbs down -> cancel
- Head gestures:
    Nod -> confirm / click
    Head shake -> cancel
    Head left/right -> previous/next
- Eye gaze:
    Uses MediaPipe Face Mesh iris landmarks
    Shows a gaze cursor
    Long dwell asks for confirmation before clicking
- Text + voice confirmation
- Basic South African language profiles for speech recognition
- Accessible UI: large controls, high contrast, no mouse required for core actions

IMPORTANT:
This is a prototype, not a medical device. Camera-based gaze/gesture recognition
can make mistakes. Always require confirmation before important actions.

Install:
    pip install opencv-python mediapipe pillow pyautogui pyperclip
    pip install SpeechRecognition PyAudio pyttsx3

Run:
    python neurolia_prototype.py
"""

import json
import math
import os
import queue
import re
import subprocess
import threading
import time
import webbrowser
from collections import deque
from difflib import get_close_matches
import tkinter as tk
from tkinter import ttk, messagebox

# Optional imports
try:
    import cv2
    import mediapipe as mp
    from PIL import Image, ImageTk
    CAMERA_OK = True
except Exception:
    CAMERA_OK = False

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.08
    GUI_CONTROL_OK = True
except Exception:
    GUI_CONTROL_OK = False

try:
    import pyperclip
    CLIPBOARD_OK = True
except Exception:
    CLIPBOARD_OK = False

try:
    import speech_recognition as sr
    SPEECH_OK = True
except Exception:
    SPEECH_OK = False

try:
    import pyttsx3
    TTS_OK = True
except Exception:
    TTS_OK = False


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

APP_NAME = "NeuroLia"
WAKE_WORDS = ("neurolia", "lia", "leah", "liya")

LANGUAGES = {
    "English (South Africa)": "en-ZA",
    "isiZulu": "zu-ZA",
    "isiXhosa": "xh-ZA",
    "Sesotho": "st-ZA",
    "Setswana": "tn-ZA",
    "Sepedi": "nso-ZA",
    "Afrikaans": "af-ZA",
}

LANGUAGE_COMMANDS = {
    "English (South Africa)": {
        "open": ["open", "launch", "start"],
        "close": ["close", "exit", "shut"],
        "copy": ["copy", "copy this", "copy that"],
        "paste": ["paste", "paste this", "paste that"],
        "select_all": ["select all", "select everything"],
        "volume_up": ["volume up", "increase volume", "turn volume up", "make it louder"],
        "volume_down": ["volume down", "decrease volume", "turn volume down", "make it quieter"],
        "mute": ["mute", "mute volume"],
        "scroll_up": ["scroll up", "go up"],
        "scroll_down": ["scroll down", "go down"],
        "back": ["go back", "back"],
        "new_tab": ["new tab", "open new tab"],
        "close_tab": ["close tab"],
        "search": ["search", "search for", "look for"],
    },
    "Setswana": {
        "open": ["bula", "simolola"],
        "close": ["tswala", "tswalela"],
        "copy": ["kopisa", "kopitsa"],
        "paste": ["kgomaretsa", "manamisa"],
        "select_all": ["tlhopha tsotlhe"],
        "volume_up": ["oketsa modumo", "godisa modumo"],
        "volume_down": ["fokotsa modumo", "fokotsa segalo"],
        "mute": ["didimatsa", "didimatsa modumo"],
        "scroll_up": ["tsamaya kwa godimo", "ya kwa godimo"],
        "scroll_down": ["tsamaya kwa tlase", "ya kwa tlase"],
        "back": ["boela morago", "morago"],
        "new_tab": ["bula tab e ntsha", "tab e ntsha"],
        "close_tab": ["tswala tab"],
        "search": ["batla", "batla sengwe"],
    },
    "Sepedi": {
        "open": ["bula", "thoma"],
        "close": ["tswala", "tswalela"],
        "copy": ["kopolla", "kopisa"],
        "paste": ["manamisa", "kgomaretša"],
        "select_all": ["kgetha tšohle"],
        "volume_up": ["oketša modumo", "godisa modumo"],
        "volume_down": ["fokotša modumo"],
        "mute": ["homotša modumo"],
        "scroll_up": ["ya godimo", "sepela godimo"],
        "scroll_down": ["ya fase", "sepela fase"],
        "back": ["boela morago"],
        "new_tab": ["bula tab ye mpsha"],
        "close_tab": ["tswala tab"],
        "search": ["nyaka", "nyaka se"],
    },
    "isiZulu": {
        "open": ["vula", "vula i", "vula le"],
        "close": ["vala", "vala i", "vala le"],
        "copy": ["kopisha", "kopisha lokhu"],
        "paste": ["namathisela", "namathisela lokhu"],
        "select_all": ["khetha konke"],
        "volume_up": ["phakamisa ivolumu", "nyusa ivolumu", "yenza umsindo ube phezulu"],
        "volume_down": ["yehlisa ivolumu", "yehlisa umsindo"],
        "mute": ["thulisa", "thulisa umsindo"],
        "scroll_up": ["skrolela phezulu", "hamba phezulu"],
        "scroll_down": ["skrolela phansi", "hamba phansi"],
        "back": ["buyela emuva"],
        "new_tab": ["vula ithebhu entsha"],
        "close_tab": ["vala ithebhu"],
        "search": ["sesha", "sesha lokhu", "funa"],
    },
    "isiXhosa": {
        "open": ["vula", "vula i"],
        "close": ["vala", "vala i"],
        "copy": ["khuphela", "khuphela oku"],
        "paste": ["ncamathelisa", "ncamathelisa oku"],
        "select_all": ["khetha konke"],
        "volume_up": ["nyusa ivolyum", "nyusa isandi"],
        "volume_down": ["hlisa ivolyum", "hlisa isandi"],
        "mute": ["cima isandi"],
        "scroll_up": ["skrolela phezulu", "yiya phezulu"],
        "scroll_down": ["skrolela ezantsi", "yiya ezantsi"],
        "back": ["buyela emva"],
        "new_tab": ["vula ithebhu entsha"],
        "close_tab": ["vala ithebhu"],
        "search": ["khangela", "khangela oku"],
    },
    "Sesotho": {
        "open": ["bula", "qala"],
        "close": ["kwala", "koala"],
        "copy": ["kopitsa", "kopitsa sena"],
        "paste": ["manamisa", "manamisa sena"],
        "select_all": ["kgetha tsohle"],
        "volume_up": ["phahamisa modumo", "eketsa modumo"],
        "volume_down": ["fokotsa modumo"],
        "mute": ["homotsa"],
        "scroll_up": ["ya hodimo", "tsamaya hodimo"],
        "scroll_down": ["ya tlase", "tsamaya tlase"],
        "back": ["kgutlela morao"],
        "new_tab": ["bula tab e ntjha"],
        "close_tab": ["kwala tab"],
        "search": ["batla", "batla sena"],
    },
    "Afrikaans": {
        "open": ["open", "maak oop", "begin"],
        "close": ["sluit", "maak toe"],
        "copy": ["kopieer", "kopieer dit"],
        "paste": ["plak", "plak dit"],
        "select_all": ["kies alles"],
        "volume_up": ["verhoog die volume", "draai die volume op"],
        "volume_down": ["verlaag die volume", "draai die volume af"],
        "mute": ["demp", "demp die volume"],
        "scroll_up": ["blaai op", "gaan op"],
        "scroll_down": ["blaai af", "gaan af"],
        "back": ["gaan terug"],
        "new_tab": ["maak 'n nuwe oortjie oop", "nuwe oortjie"],
        "close_tab": ["sluit oortjie"],
        "search": ["soek", "soek vir"],
    },
}

APP_NAMES = {
    "chrome": ["chrome", "google chrome", "chroom"],
    "word": ["word", "microsoft word"],
    "vs code": ["vs code", "visual studio code", "vscode", "code"],
    "notepad": ["notepad", "teksblok"],
    "edge": ["edge", "microsoft edge"],
    "whatsapp": ["whatsapp"],
    "spotify": ["spotify"],
    "calculator": ["calculator", "calc", "sakrekenaar"],
    "file explorer": ["file explorer", "explorer", "lêerverkenner"],
}


def find_app_name(text):
    text = (text or "").lower().strip()
    if not text:
        return None

    for app, aliases in APP_NAMES.items():
        for alias in aliases:
            if text == alias:
                return app

    for app, aliases in APP_NAMES.items():
        for alias in aliases:
            if alias in text:
                return app

    return text


def find_command(user_text, selected_language):
    raw_text = (user_text or "").strip()
    normalized_text = raw_text.lower().strip()
    normalized_text = re.sub(r"[?!.,]", "", normalized_text)

    commands = LANGUAGE_COMMANDS.get(selected_language, LANGUAGE_COMMANDS["English (South Africa)"])

    for action, phrases in commands.items():
        for phrase in sorted(phrases, key=len, reverse=True):
            phrase_lower = phrase.lower().strip()
            if normalized_text == phrase_lower or normalized_text.startswith(phrase_lower + " "):
                remaining = raw_text[len(phrase):].strip()
                remaining = re.sub(r"[?!.,]", "", remaining)

                if action == "open":
                    target = find_app_name(remaining)
                    return {"action": "open_app", "target": target or remaining, "language": selected_language}
                if action == "search":
                    return {"action": "search", "query": remaining, "language": selected_language}
                if action == "copy":
                    return {"action": "copy_text", "text": remaining, "language": selected_language}
                if action == "paste":
                    return {"action": "paste", "text": remaining, "language": selected_language}
                return {"action": action, "language": selected_language}

    return {"action": "unknown", "text": normalized_text, "language": selected_language}


APPS = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "firefox": "firefox",
    "notepad": "notepad",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "outlook": "outlook",
    "calculator": "calc",
    "file explorer": "explorer",
    "explorer": "explorer",
    "task manager": "taskmgr",
    "settings": "ms-settings:",
    "paint": "mspaint",
    "vs code": "code",
    "visual studio code": "code",
    "code": "code",
    "spotify": "spotify",
    "vlc": "vlc",
    "whatsapp": "whatsapp:",
    "teams": "msteams:",
}

SEARCH_TARGETS = {
    "chrome": lambda q: webbrowser.open(
        "https://www.google.com/search?q=" + quote(q)
    ),
    "google": lambda q: webbrowser.open(
        "https://www.google.com/search?q=" + quote(q)
    ),
    "youtube": lambda q: webbrowser.open(
        "https://www.youtube.com/results?search_query=" + quote(q)
    ),
    "maps": lambda q: webbrowser.open(
        "https://maps.google.com/?q=" + quote(q)
    ),
}

# Hand/head gesture cooldowns prevent repeated actions every frame.
GESTURE_COOLDOWN = 0.8
GAZE_DWELL_SECONDS = 1.8
GAZE_CONFIRM_TIMEOUT = 8.0


def quote(text: str) -> str:
    from urllib.parse import quote_plus
    return quote_plus(text)


# ---------------------------------------------------------------------------
# Text-to-speech
# ---------------------------------------------------------------------------

class SpeechOutput:
    def __init__(self):
        self.q = queue.Queue()
        self.engine = None
        self.running = True
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def _worker(self):
        while self.running:
            try:
                text = self.q.get(timeout=0.2)
            except queue.Empty:
                continue

            if text is None:
                break

            if TTS_OK:
                try:
                    if self.engine is None:
                        self.engine = pyttsx3.init()
                        self.engine.setProperty("rate", 165)
                    self.engine.say(text)
                    self.engine.runAndWait()
                except Exception:
                    pass

            self.q.task_done()

    def say(self, text: str):
        if text:
            self.q.put(str(text))

    def stop(self):
        self.running = False
        self.q.put(None)


TTS = SpeechOutput()


# ---------------------------------------------------------------------------
# Desktop control
# ---------------------------------------------------------------------------

def press(*keys):
    if not GUI_CONTROL_OK:
        return False
    try:
        if len(keys) == 1:
            pyautogui.press(keys[0])
        else:
            pyautogui.hotkey(*keys)
        return True
    except Exception:
        return False


def open_target(target: str) -> bool:
    target = target.lower().strip()
    executable = APPS.get(target)

    try:
        if executable and executable.endswith(":"):
            os.startfile(executable)
            return True

        if executable:
            os.startfile(executable)
            return True
    except Exception:
        pass

    try:
        if executable:
            subprocess.Popen(executable, shell=True)
            return True
    except Exception:
        pass

    # If it looks like a website
    if "." in target and " " not in target:
        try:
            webbrowser.open(
                target if target.startswith("http") else "https://" + target
            )
            return True
        except Exception:
            pass

    return False


def copy_active():
    if not GUI_CONTROL_OK or not CLIPBOARD_OK:
        return False, ""
    try:
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.2)
        return True, pyperclip.paste()
    except Exception:
        return False, ""


def paste_active(text=None):
    if not GUI_CONTROL_OK or not CLIPBOARD_OK:
        return False
    try:
        if text is not None:
            pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        return True
    except Exception:
        return False


def type_text(text):
    if not GUI_CONTROL_OK:
        return False
    try:
        pyautogui.write(text, interval=0.015)
        return True
    except Exception:
        if CLIPBOARD_OK:
            return paste_active(text)
        return False


# ---------------------------------------------------------------------------
# Command parser
# ---------------------------------------------------------------------------

def local_command(text: str, selected_language: str = "English (South Africa)"):
    """
    Offline fallback parser.
    Returns a dictionary:
        action, text/query/target/destination, reply
    """
    command = find_command(text, selected_language)
    if command.get("action") != "unknown":
        payload = dict(command)
        reply = {
            "open_app": f"Opening {payload.get('target', '').title()}.",
            "search": f"Searching for {payload.get('query', '')}.",
            "copy_text": f"Copying: {payload.get('text', '')}.",
            "paste": "Pasting.",
        }.get(payload.get("action"), "Command recognized.")
        payload["reply"] = reply
        return payload

    c = (text or "").lower().strip()

    if any(x in c for x in ("goodbye", "exit neurolia", "close neurolia")):
        return {"action": "exit", "reply": "Goodbye."}

    if "volume up" in c or "increase volume" in c or "turn it up" in c:
        return {"action": "volume_up", "reply": "Volume up."}

    if "volume down" in c or "decrease volume" in c or "turn it down" in c:
        return {"action": "volume_down", "reply": "Volume down."}

    if "mute" in c:
        return {"action": "mute", "reply": "Muted."}

    if "scroll up" in c:
        return {"action": "scroll_up", "reply": "Scrolling up."}

    if "scroll down" in c:
        return {"action": "scroll_down", "reply": "Scrolling down."}

    if "new tab" in c:
        return {"action": "new_tab", "reply": "Opening a new tab."}

    if "close tab" in c:
        return {"action": "close_tab", "reply": "Closing the tab."}

    if "go back" in c:
        return {"action": "back", "reply": "Going back."}

    if "refresh" in c:
        return {"action": "refresh", "reply": "Refreshing."}

    if "select all" in c:
        return {"action": "select_all", "reply": "Selecting everything."}

    if c in ("copy", "copy this", "copy that", "copy selected text"):
        return {"action": "copy", "reply": "Copying the selected text."}

    if c in ("paste", "paste that", "paste it"):
        return {"action": "paste", "reply": "Pasting."}

    m = re.search(
        r"copy (?:everything )?(?:from )?(.+?) "
        r"(?:and )?(?:paste|put) (?:it )?(?:in|into|to) (.+)",
        c,
    )
    if m:
        return {
            "action": "copy_and_paste",
            "source": m.group(1).strip(),
            "destination": m.group(2).strip(),
            "reply": "Copying and pasting that for you.",
        }

    m = re.search(
        r"(?:type|write) (.+?) (?:in|into|on) (.+)",
        c,
    )
    if m:
        return {
            "action": "type",
            "text": m.group(1).strip(),
            "destination": m.group(2).strip(),
            "reply": "Typing that for you.",
        }

    m = re.search(r"(?:type|write) (.+)", c)
    if m:
        return {
            "action": "type",
            "text": m.group(1).strip(),
            "reply": "Typing that for you.",
        }

    m = re.search(
        r"search (?:for )?(.+?) (?:on|in|using) (.+)",
        c,
    )
    if m:
        return {
            "action": "search",
            "query": m.group(1).strip(),
            "target": m.group(2).strip(),
            "reply": "Searching for that.",
        }

    m = re.search(r"search (?:for )?(.+)", c)
    if m:
        return {
            "action": "search",
            "query": m.group(1).strip(),
            "target": "chrome",
            "reply": "Searching for that.",
        }

    m = re.search(r"(?:open|launch|start) (.+)", c)
    if m:
        return {
            "action": "open",
            "target": m.group(1).strip(),
            "reply": f"Opening {m.group(1).strip()}.",
        }

    return {
        "action": "unknown",
        "reply": f"I heard: {text}. I am not sure what action you want.",
    }


# ---------------------------------------------------------------------------
# NeuroLia application
# ---------------------------------------------------------------------------

class NeuroLia(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("NeuroLia — Accessibility AI")
        self.geometry("1180x760")
        self.minsize(950, 650)
        self.configure(bg="#09090e")

        # State
        self.running = True
        self.camera_running = False
        self.voice_running = False

        self.selected_language = tk.StringVar(
            value="English (South Africa)"
        )

        self.status_var = tk.StringVar(value="Starting NeuroLia...")
        self.gesture_var = tk.StringVar(value="No gesture detected")
        self.gaze_var = tk.StringVar(value="Gaze: waiting for camera")
        self.confidence_var = tk.StringVar(value="Confidence: --")
        self.confirm_var = tk.StringVar(value="")

        self.log_lines = deque(maxlen=200)

        self.last_gesture_time = {}
        self.hand_x_history = deque(maxlen=12)
        self.hand_y_history = deque(maxlen=12)
        self.head_history = deque(maxlen=15)

        self.gaze_history = deque(maxlen=8)
        self.gaze_start = None
        self.gaze_point = None
        self.confirmation_event = None
        self.confirmation_answer = None

        self.calibration = {
            "left": 0.0,
            "right": 1.0,
            "top": 0.0,
            "bottom": 1.0,
        }

        self.build_ui()

        self.protocol("WM_DELETE_WINDOW", self.shutdown)

        self.after(500, self.greet)
        self.after(1000, self.start_camera)
        self.after(1300, self.start_voice)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def build_ui(self):
        top = tk.Frame(self, bg="#111118")
        top.pack(fill="x", padx=14, pady=(14, 8))

        tk.Label(
            top,
            text="NEUROLIA",
            bg="#111118",
            fg="#f0eeff",
            font=("Segoe UI", 24, "bold"),
        ).pack(side="left", padx=14, pady=12)

        tk.Label(
            top,
            text="Adaptive AI accessibility interface",
            bg="#111118",
            fg="#6b6890",
            font=("Segoe UI", 11),
        ).pack(side="left")

        lang = ttk.Combobox(
            top,
            textvariable=self.selected_language,
            values=list(LANGUAGES.keys()),
            state="readonly",
            width=24,
        )
        lang.pack(side="right", padx=14)

        tk.Label(
            top,
            text="Language",
            bg="#111118",
            fg="#6b6890",
        ).pack(side="right")

        main = tk.Frame(self, bg="#09090e")
        main.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        left = tk.Frame(main, bg="#111118")
        left.pack(side="left", fill="both", expand=True, padx=(0, 7))

        right = tk.Frame(main, bg="#111118", width=410)
        right.pack(side="right", fill="both", padx=(7, 0))
        right.pack_propagate(False)

        # Status
        tk.Label(
            left,
            textvariable=self.status_var,
            bg="#111118",
            fg="#20c97a",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).pack(fill="x", padx=16, pady=(16, 3))

        tk.Label(
            left,
            text="Say “NeuroLia” followed by a command.",
            bg="#111118",
            fg="#6b6890",
            font=("Segoe UI", 10),
            anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 10))

        # Conversation log
        log_frame = tk.Frame(left, bg="#18181f")
        log_frame.pack(fill="both", expand=True, padx=12, pady=8)

        self.log = tk.Text(
            log_frame,
            bg="#18181f",
            fg="#f0eeff",
            insertbackground="#f0eeff",
            font=("Consolas", 11),
            wrap="word",
            state="disabled",
            relief="flat",
            padx=12,
            pady=12,
        )
        self.log.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.log.yview
        )
        scroll.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scroll.set)

        # Text command
        command_frame = tk.Frame(left, bg="#111118")
        command_frame.pack(fill="x", padx=12, pady=10)

        self.command_entry = tk.Entry(
            command_frame,
            bg="#18181f",
            fg="#f0eeff",
            insertbackground="#f0eeff",
            font=("Segoe UI", 12),
            relief="flat",
        )
        self.command_entry.pack(
            side="left", fill="x", expand=True, ipady=10
        )
        self.command_entry.bind("<Return>", lambda e: self.send_text())

        tk.Button(
            command_frame,
            text="SEND",
            command=self.send_text,
            bg="#8b7cf8",
            fg="white",
            activebackground="#2d2860",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
            width=10,
        ).pack(side="right", padx=(8, 0), ipady=7)

        # Camera
        tk.Label(
            right,
            text="CAMERA / MULTIMODAL CONTROL",
            bg="#111118",
            fg="#f0eeff",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", padx=14, pady=(14, 6))

        self.camera_label = tk.Label(
            right,
            text="Camera loading...",
            bg="#18181f",
            fg="#6b6890",
            font=("Segoe UI", 11),
        )
        self.camera_label.pack(
            fill="both", expand=True, padx=14, pady=4
        )

        # Detection status
        status = tk.Frame(right, bg="#18181f")
        status.pack(fill="x", padx=14, pady=8)

        for variable in (
            self.gesture_var,
            self.gaze_var,
            self.confidence_var,
        ):
            tk.Label(
                status,
                textvariable=variable,
                bg="#18181f",
                fg="#6b6890",
                anchor="w",
                font=("Segoe UI", 10),
            ).pack(fill="x", padx=10, pady=3)

        # Confirmation
        self.confirm_label = tk.Label(
            right,
            textvariable=self.confirm_var,
            bg="#2d2860",
            fg="#f0eeff",
            font=("Segoe UI", 13, "bold"),
            wraplength=360,
            padx=10,
            pady=10,
        )
        self.confirm_label.pack(fill="x", padx=14, pady=6)

        # Gesture legend
        legend = tk.Frame(right, bg="#111118")
        legend.pack(fill="x", padx=14, pady=8)

        tk.Label(
            legend,
            text="GESTURE CONTROLS",
            bg="#111118",
            fg="#6b6890",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")

        gestures = [
            ("✊ Fist", "Volume down"),
            ("✋ Open palm", "Volume up"),
            ("👉 Swipe right", "Next tab"),
            ("👈 Swipe left", "Close tab"),
            ("↕ Hand wave", "Scroll"),
            ("👍 Thumbs up / Nod", "Confirm"),
            ("👎 Thumbs down / Shake", "Cancel"),
            ("👁 Gaze dwell", "Ask before click"),
        ]

        for g, a in gestures:
            row = tk.Frame(legend, bg="#111118")
            row.pack(fill="x")
            tk.Label(
                row, text=g, bg="#111118", fg="#f0eeff",
                font=("Segoe UI", 9), anchor="w"
            ).pack(side="left")
            tk.Label(
                row, text=a, bg="#111118", fg="#8b7cf8",
                font=("Segoe UI", 9), anchor="e"
            ).pack(side="right")

        # Emergency stop
        tk.Button(
            right,
            text="STOP CURRENT ACTION",
            command=self.cancel_action,
            bg="#3d1010",
            fg="#e85545",
            activebackground="#5a1717",
            relief="flat",
            font=("Segoe UI", 10, "bold"),
        ).pack(fill="x", padx=14, pady=(4, 14), ipady=8)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log_message(self, who, text):
        timestamp = time.strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert(
            "end",
            f"[{timestamp}] {who}: {text}\n"
        )
        self.log.see("end")
        self.log.configure(state="disabled")

    def set_status(self, text, color="#20c97a"):
        self.status_var.set(text)

    # ------------------------------------------------------------------
    # Greeting
    # ------------------------------------------------------------------

    def greet(self):
        message = (
            "Hello. I'm NeuroLia. I can control your computer with voice, "
            "hand gestures, head movements and eye gaze."
        )
        self.log_message("NeuroLia", message)
        TTS.say(message)

    # ------------------------------------------------------------------
    # Voice
    # ------------------------------------------------------------------

    def start_voice(self):
        if not SPEECH_OK:
            self.log_message(
                "System",
                "SpeechRecognition is unavailable. Text commands still work."
            )
            return

        self.voice_running = True
        threading.Thread(
            target=self.voice_loop,
            daemon=True,
        ).start()

    def voice_loop(self):
        recognizer = sr.Recognizer()
        recognizer.dynamic_energy_threshold = True

        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=1)
        except Exception as exc:
            self.after(
                0,
                lambda: self.log_message(
                    "System",
                    f"Microphone unavailable: {exc}"
                ),
            )
            return

        while self.running and self.voice_running:
            try:
                self.after(
                    0,
                    lambda: self.set_status(
                        "Listening for NeuroLia..."
                    ),
                )

                with sr.Microphone() as source:
                    audio = recognizer.listen(
                        source,
                        timeout=5,
                        phrase_time_limit=4,
                    )

                language = LANGUAGES.get(
                    self.selected_language.get(), "en-ZA"
                )

                try:
                    heard = recognizer.recognize_google(
                        audio,
                        language=language,
                    ).strip()
                except Exception:
                    # English fallback can be useful when a regional
                    # language model is unavailable.
                    heard = recognizer.recognize_google(
                        audio,
                        language="en-US",
                    ).strip()

                if not heard:
                    continue

                if not self.contains_wake_word(heard):
                    continue

                command = self.remove_wake_word(heard)

                self.after(
                    0,
                    lambda h=heard: self.log_message(
                        "Voice", h
                    ),
                )

                if not command:
                    TTS.say("Yes? What would you like me to do?")
                    continue

                self.after(
                    0,
                    lambda c=command: self.run_command(c),
                )

            except sr.WaitTimeoutError:
                continue
            except Exception:
                time.sleep(0.5)

    def contains_wake_word(self, text):
        lower = text.lower()
        return any(
            re.search(r"\b" + re.escape(w) + r"\b", lower)
            for w in WAKE_WORDS
        )

    def remove_wake_word(self, text):
        result = text
        for word in WAKE_WORDS:
            result = re.sub(
                r"\b" + re.escape(word) + r"\b",
                "",
                result,
                flags=re.IGNORECASE,
            )
        return re.sub(r"\s+", " ", result).strip(" ,.!?")

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def send_text(self):
        text = self.command_entry.get().strip()
        if not text:
            return
        self.command_entry.delete(0, "end")
        self.run_command(text)

    def run_command(self, text):
        self.log_message("You", text)
        self.set_status("Thinking...")
        threading.Thread(
            target=self._process_command,
            args=(text,),
            daemon=True,
        ).start()

    def _process_command(self, text):
        data = local_command(text)
        reply = data.get("reply", "Done.")

        self.after(
            0,
            lambda: self.log_message("NeuroLia", reply)
        )
        TTS.say(reply)

        action = data.get("action")

        try:
            if action == "open":
                ok = open_target(data.get("target", ""))
                result = "Opened." if ok else "I couldn't open that."

            elif action == "search":
                result = self.execute_search(
                    data.get("target", "chrome"),
                    data.get("query", ""),
                )

            elif action == "copy":
                ok, copied = copy_active()
                result = (
                    "Copied the selected text."
                    if ok else
                    "I couldn't copy the selected text."
                )

            elif action == "paste":
                result = (
                    "Pasted."
                    if paste_active()
                    else "I couldn't paste."
                )

            elif action == "copy_and_paste":
                result = self.copy_between_apps(
                    data.get("source", ""),
                    data.get("destination", ""),
                )

            elif action == "type":
                if data.get("destination"):
                    open_target(data["destination"])
                    time.sleep(1)
                ok = type_text(data.get("text", ""))
                result = "Typed." if ok else "I couldn't type that."

            elif action == "volume_up":
                press("volumeup")
                result = "Volume up."

            elif action == "volume_down":
                press("volumedown")
                result = "Volume down."

            elif action == "mute":
                press("volumemute")
                result = "Muted."

            elif action == "scroll_up":
                if GUI_CONTROL_OK:
                    pyautogui.scroll(5)
                result = "Scrolling up."

            elif action == "scroll_down":
                if GUI_CONTROL_OK:
                    pyautogui.scroll(-5)
                result = "Scrolling down."

            elif action == "new_tab":
                press("ctrl", "t")
                result = "New tab."

            elif action == "close_tab":
                press("ctrl", "w")
                result = "Closed the tab."

            elif action == "back":
                press("alt", "left")
                result = "Going back."

            elif action == "refresh":
                press("ctrl", "r")
                result = "Refreshed."

            elif action == "select_all":
                press("ctrl", "a")
                result = "Selected all."

            elif action == "exit":
                self.after(0, self.shutdown)
                return

            else:
                result = reply

            self.after(
                0,
                lambda r=result: self.log_message(
                    "Action", r
                )
            )

        except Exception as exc:
            self.after(
                0,
                lambda: self.log_message(
                    "Error", str(exc)
                )
            )

        self.after(
            0,
            lambda: self.set_status(
                "Ready — say NeuroLia or use a gesture"
            )
        )

    def execute_search(self, target, query):
        target = target.lower().strip()

        if target in SEARCH_TARGETS:
            SEARCH_TARGETS[target](query)
            return f"Searching {target}."

        webbrowser.open(
            "https://www.google.com/search?q=" + quote(query)
        )
        return "Searching Google."

    def copy_between_apps(self, source, destination):
        if source:
            open_target(source)
            time.sleep(1)

        ok, copied = copy_active()

        if not ok:
            return "I couldn't copy the source."

        if destination:
            open_target(destination)
            time.sleep(1)

        if paste_active(copied):
            return "Copied and pasted successfully."

        return "I copied the text, but couldn't paste it."

    # ------------------------------------------------------------------
    # Confirmation system
    # ------------------------------------------------------------------

    def ask_confirmation(self, question):
        """
        Ask using text + voice.
        Returns True, False or None.
        """
        self.confirmation_answer = None
        self.confirmation_event = threading.Event()

        self.after(
            0,
            lambda: self.confirm_var.set(question)
        )

        TTS.say(question)

        # Give the user a chance to answer with voice or gesture.
        finished = self.confirmation_event.wait(
            GAZE_CONFIRM_TIMEOUT
        )

        answer = self.confirmation_answer

        self.after(
            0,
            lambda: self.confirm_var.set("")
        )

        return answer if finished else None

    def confirm_yes(self):
        self.confirmation_answer = True
        if self.confirmation_event:
            self.confirmation_event.set()

    def confirm_no(self):
        self.confirmation_answer = False
        if self.confirmation_event:
            self.confirmation_event.set()

    def cancel_action(self):
        self.confirmation_answer = False
        if self.confirmation_event:
            self.confirmation_event.set()

        self.confirm_var.set("")
        self.log_message("NeuroLia", "Current action cancelled.")
        TTS.say("Current action cancelled.")

    # ------------------------------------------------------------------
    # Camera
    # ------------------------------------------------------------------

    def start_camera(self):
        if not CAMERA_OK:
            self.camera_label.configure(
                text="Camera libraries unavailable.\n"
                     "Install OpenCV, MediaPipe and Pillow."
            )
            return

        self.camera_running = True

        threading.Thread(
            target=self.camera_loop,
            daemon=True,
        ).start()

    def camera_loop(self):
        cap = cv2.VideoCapture(0)

        if not cap.isOpened():
            self.after(
                0,
                lambda: self.camera_label.configure(
                    text="Could not open camera."
                ),
            )
            return

        hands = None
        face_mesh = None

        try:
            hands = mp.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=1,
                min_detection_confidence=0.55,
                min_tracking_confidence=0.55,
            )

            face_mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )

            while self.running and self.camera_running:
                ok, frame = cap.read()
                if not ok:
                    continue

                frame = cv2.flip(frame, 1)

                rgb = cv2.cvtColor(
                    frame,
                    cv2.COLOR_BGR2RGB,
                )

                hand_result = hands.process(rgb)
                face_result = face_mesh.process(rgb)

                gesture = None

                if hand_result.multi_hand_landmarks:
                    gesture = self.detect_hand_gesture(
                        hand_result.multi_hand_landmarks[0]
                    )

                if face_result.multi_face_landmarks:
                    face = face_result.multi_face_landmarks[0]
                    head_gesture = self.detect_head_gesture(face)

                    if head_gesture:
                        gesture = head_gesture

                    self.process_gaze(
                        face,
                        frame.shape[1],
                        frame.shape[0],
                    )

                if gesture:
                    self.trigger_gesture(gesture)

                # Draw a simple center reticle.
                h, w = frame.shape[:2]
                cv2.circle(
                    frame,
                    (w // 2, h // 2),
                    5,
                    (139, 124, 248),
                    -1,
                )

                # Gaze cursor
                if self.gaze_point:
                    gx, gy = self.gaze_point
                    cv2.circle(
                        frame,
                        (int(gx * w), int(gy * h)),
                        12,
                        (32, 201, 122),
                        2,
                    )

                small_w = 390
                small_h = int(
                    frame.shape[0] * small_w / frame.shape[1]
                )

                display = cv2.resize(
                    frame,
                    (small_w, small_h),
                )

                display = cv2.cvtColor(
                    display,
                    cv2.COLOR_BGR2RGB,
                )

                image = Image.fromarray(display)
                photo = ImageTk.PhotoImage(image=image)

                self.after(
                    0,
                    lambda p=photo: self.update_camera_image(p)
                )

                time.sleep(0.02)

        except Exception as exc:
            self.after(
                0,
                lambda: self.log_message(
                    "Camera",
                    f"Camera engine error: {exc}"
                )
            )
        finally:
            if hands:
                hands.close()
            if face_mesh:
                face_mesh.close()
            cap.release()

    def update_camera_image(self, photo):
        if not self.running:
            return
        self.camera_label.configure(image=photo, text="")
        self.camera_label.image = photo

    # ------------------------------------------------------------------
    # Hand recognition
    # ------------------------------------------------------------------

    @staticmethod
    def distance(a, b):
        return math.sqrt(
            (a.x - b.x) ** 2 +
            (a.y - b.y) ** 2 +
            (a.z - b.z) ** 2
        )

    def finger_extended(self, lm, tip, pip):
        return lm[tip].y < lm[pip].y

    def detect_hand_gesture(self, hand):
        lm = hand.landmark

        # Finger states
        index = self.finger_extended(lm, 8, 6)
        middle = self.finger_extended(lm, 12, 10)
        ring = self.finger_extended(lm, 16, 14)
        pinky = self.finger_extended(lm, 20, 18)

        palm = lm[9]

        # Fist
        extended_count = sum(
            [index, middle, ring, pinky]
        )

        if extended_count == 0:
            self.hand_x_history.append(palm.x)
            self.hand_y_history.append(palm.y)
            return "fist"

        # Open palm
        if extended_count >= 4:
            self.hand_x_history.append(palm.x)
            self.hand_y_history.append(palm.y)

            if len(self.hand_x_history) >= 8:
                dx = (
                    self.hand_x_history[-1]
                    - self.hand_x_history[0]
                )
                if abs(dx) > 0.22:
                    self.hand_x_history.clear()
                    return (
                        "hand_swipe_right"
                        if dx > 0
                        else "hand_swipe_left"
                    )

                dy = (
                    self.hand_y_history[-1]
                    - self.hand_y_history[0]
                )
                if abs(dy) > 0.18:
                    self.hand_y_history.clear()
                    return (
                        "hand_wave_down"
                        if dy > 0
                        else "hand_wave_up"
                    )

            return "open_palm"

        # Thumbs-up / thumbs-down
        thumb_up = lm[4].y < lm[3].y
        thumb_down = lm[4].y > lm[3].y

        if index and not middle and not ring and not pinky:
            return "point"

        if thumb_up and extended_count <= 1:
            return "thumbs_up"

        if thumb_down and extended_count <= 1:
            return "thumbs_down"

        return None

    # ------------------------------------------------------------------
    # Head recognition
    # ------------------------------------------------------------------

    def detect_head_gesture(self, face):
        """
        Prototype head gesture detection.
        Uses the nose landmark as a coarse head-position signal.
        """
        nose = face.landmark[1]

        self.head_history.append(
            (nose.x, nose.y, time.time())
        )

        if len(self.head_history) < 10:
            return None

        x0, y0, _ = self.head_history[0]
        x1, y1, _ = self.head_history[-1]

        dx = x1 - x0
        dy = y1 - y0

        # Strong vertical movement = nod
        if abs(dy) > 0.16 and abs(dy) > abs(dx) * 1.2:
            self.head_history.clear()
            return "head_nod"

        # Strong horizontal movement = head swipe
        if abs(dx) > 0.18 and abs(dx) > abs(dy) * 1.2:
            self.head_history.clear()

            if dx > 0:
                return "head_right"
            return "head_left"

        return None

    # ------------------------------------------------------------------
    # Eye gaze
    # ------------------------------------------------------------------

    def process_gaze(self, face, width, height):
        """
        Estimate gaze from iris position relative to the eye corners.
        This is deliberately conservative and intended as a prototype.
        """
        lm = face.landmark

        # MediaPipe Face Mesh iris landmarks:
        # left iris approx 468-472, right iris approx 473-477.
        if len(lm) < 478:
            return

        left_iris = lm[468]
        right_iris = lm[473]

        # Approximate eye corners.
        left_inner = lm[133]
        left_outer = lm[33]
        right_inner = lm[362]
        right_outer = lm[263]

        left_ratio = self.normalized_position(
            left_iris.x,
            left_outer.x,
            left_inner.x,
        )

        right_ratio = self.normalized_position(
            right_iris.x,
            right_inner.x,
            right_outer.x,
        )

        gaze_x = max(
            0.0,
            min(
                1.0,
                (left_ratio + right_ratio) / 2,
            ),
        )

        # Vertical estimate using upper/lower eyelid points.
        left_top = lm[159]
        left_bottom = lm[145]
        right_top = lm[386]
        right_bottom = lm[374]

        left_y = self.normalized_position(
            left_iris.y,
            left_top.y,
            left_bottom.y,
        )

        right_y = self.normalized_position(
            right_iris.y,
            right_top.y,
            right_bottom.y,
        )

        gaze_y = max(
            0.0,
            min(
                1.0,
                (left_y + right_y) / 2,
            ),
        )

        # Low-pass smoothing.
        self.gaze_history.append(
            (gaze_x, gaze_y)
        )

        avg_x = sum(p[0] for p in self.gaze_history) / len(
            self.gaze_history
        )
        avg_y = sum(p[1] for p in self.gaze_history) / len(
            self.gaze_history
        )

        self.gaze_point = (avg_x, avg_y)

        confidence = self.calculate_gaze_confidence(
            self.gaze_history
        )

        self.after(
            0,
            lambda c=confidence: self.confidence_var.set(
                f"Confidence: {c:.0%}"
            ),
        )

        self.after(
            0,
            lambda x=avg_x, y=avg_y: self.gaze_var.set(
                f"Gaze: X={x:.2f}, Y={y:.2f}"
            ),
        )

        # Dwell detection
        now = time.time()

        if self.gaze_start is None:
            self.gaze_start = now

        if now - self.gaze_start >= GAZE_DWELL_SECONDS:
            # Reset immediately so we don't repeatedly ask.
            self.gaze_start = now + 999

            threading.Thread(
                target=self.handle_gaze_dwell,
                args=(avg_x, avg_y, confidence),
                daemon=True,
            ).start()

    @staticmethod
    def normalized_position(value, start, end):
        span = end - start

        if abs(span) < 0.0001:
            return 0.5

        return (value - start) / span

    @staticmethod
    def calculate_gaze_confidence(history):
        if len(history) < 3:
            return 0.4

        xs = [p[0] for p in history]
        ys = [p[1] for p in history]

        variance = (
            max(xs) - min(xs)
            + max(ys) - min(ys)
        )

        confidence = max(
            0.2,
            min(
                0.98,
                1.0 - variance * 2.5,
            ),
        )

        return confidence

    def handle_gaze_dwell(self, x, y, confidence):
        """
        Never click automatically after gaze dwell.
        Ask the user first.
        """
        question = (
            f"Is this what you were looking at? "
            f"Gaze position {x:.2f}, {y:.2f}."
        )

        answer = self.ask_confirmation(question)

        if answer is True:
            if GUI_CONTROL_OK:
                screen_w, screen_h = pyautogui.size()

                screen_x = int(x * screen_w)
                screen_y = int(y * screen_h)

                pyautogui.click(
                    screen_x,
                    screen_y,
                )

            self.log_message(
                "Gaze",
                "Confirmed. Clicked the gaze location.",
            )
            TTS.say("Confirmed.")

        elif answer is False:
            self.log_message(
                "Gaze",
                "Gaze selection cancelled.",
            )
            TTS.say("Okay. I won't click.")

        else:
            self.log_message(
                "Gaze",
                "No confirmation received.",
            )

        self.gaze_start = None

    # ------------------------------------------------------------------
    # Gesture actions
    # ------------------------------------------------------------------

    def trigger_gesture(self, gesture):
        now = time.time()
        previous = self.last_gesture_time.get(
            gesture,
            0,
        )

        if now - previous < GESTURE_COOLDOWN:
            return

        self.last_gesture_time[gesture] = now

        self.gesture_var.set(
            f"Gesture: {gesture}"
        )

        if gesture == "fist":
            press("volumedown")
            self.log_message(
                "Gesture",
                "✊ Fist → Volume down",
            )
            TTS.say("Volume down.")

        elif gesture == "open_palm":
            press("volumeup")
            self.log_message(
                "Gesture",
                "✋ Open palm → Volume up",
            )
            TTS.say("Volume up.")

        elif gesture == "hand_swipe_right":
            press("ctrl", "tab")
            self.log_message(
                "Gesture",
                "Swipe right → Next tab",
            )

        elif gesture == "hand_swipe_left":
            press("ctrl", "w")
            self.log_message(
                "Gesture",
                "Swipe left → Close tab",
            )

        elif gesture == "hand_wave_up":
            if GUI_CONTROL_OK:
                pyautogui.scroll(5)
            self.log_message(
                "Gesture",
                "Hand wave up → Scroll up",
            )

        elif gesture == "hand_wave_down":
            if GUI_CONTROL_OK:
                pyautogui.scroll(-5)
            self.log_message(
                "Gesture",
                "Hand wave down → Scroll down",
            )

        elif gesture in ("thumbs_up", "head_nod"):
            self.log_message(
                "Gesture",
                f"{gesture} → Confirm",
            )
            self.confirm_yes()
            TTS.say("Confirmed.")

        elif gesture in ("thumbs_down",):
            self.log_message(
                "Gesture",
                "Thumbs down → Cancel",
            )
            self.confirm_no()
            TTS.say("Cancelled.")

        elif gesture == "head_left":
            press("alt", "left")
            self.log_message(
                "Gesture",
                "Head left → Back",
            )

        elif gesture == "head_right":
            press("ctrl", "tab")
            self.log_message(
                "Gesture",
                "Head right → Next",
            )

        elif gesture == "head_shake":
            self.confirm_no()

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def shutdown(self):
        if not self.running:
            return

        self.running = False
        self.camera_running = False
        self.voice_running = False

        try:
            TTS.stop()
        except Exception:
            pass

        self.destroy()


if __name__ == "__main__":
    app = NeuroLia()
    app.mainloop()