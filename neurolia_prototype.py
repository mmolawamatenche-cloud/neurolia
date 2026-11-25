"""
NeuroLia Prototype — aligned with lia4.py
Adds: multilingual commands, head gestures, eye-gaze dwell
Reuses: speak(), execute(), ask_gpt(), stop_speaking() from lia4 modules
"""

import customtkinter as ctk
import tkinter as tk
import threading, time, queue, os, re, math
from collections import deque

# ── reuse lia4 core ────────────────────────────────────────────────────────────
from lia4 import (
    speak, stop_speaking, execute, ask_gpt,
    _local_parse, _normalize_action, _safe_print,
    C, CAM_OK, SR_OK, TTS_OK, GPT_OK,
    is_failure_message,
)
from lia_core import is_allowed, needs_confirmation, confirmation_prompt
from engine import is_failure

try:
    import cv2, mediapipe as mp
    from PIL import Image
    _CAM = True
except ImportError:
    _CAM = False

try:
    import speech_recognition as sr
    _SR = True
except ImportError:
    _SR = False

try:
    import pyautogui
    pyautogui.FAILSAFE = False
    _GUI = True
except ImportError:
    _GUI = False

# ── multilingual command tables ────────────────────────────────────────────────
LANGUAGES = {
    "English": "en-US",
    "Afrikaans": "af-ZA",
    "isiZulu": "zu-ZA",
    "isiXhosa": "xh-ZA",
    "Sesotho": "st-ZA",
    "Setswana": "tn-ZA",
    "Sepedi": "nso-ZA",
}

LANG_CMDS = {
    "English": {
        "volume_up":   ["volume up", "increase volume", "louder"],
        "volume_down": ["volume down", "decrease volume", "quieter"],
        "mute":        ["mute", "silence"],
        "scroll_up":   ["scroll up", "go up"],
        "scroll_down": ["scroll down", "go down"],
        "new_tab":     ["new tab"],
        "close_tab":   ["close tab"],
        "go_back":     ["go back", "back"],
        "refresh":     ["refresh"],
        "select_all":  ["select all"],
        "copy":        ["copy", "copy this"],
        "paste":       ["paste", "paste that"],
        "search":      ["search", "search for"],
        "open":        ["open", "launch", "start"],
    },
    "Afrikaans": {
        "volume_up":   ["verhoog die volume", "draai die volume op"],
        "volume_down": ["verlaag die volume", "draai die volume af"],
        "mute":        ["demp"],
        "scroll_up":   ["blaai op", "gaan op"],
        "scroll_down": ["blaai af", "gaan af"],
        "new_tab":     ["nuwe oortjie"],
        "close_tab":   ["sluit oortjie"],
        "go_back":     ["gaan terug"],
        "refresh":     ["verfris"],
        "select_all":  ["kies alles"],
        "copy":        ["kopieer"],
        "paste":       ["plak"],
        "search":      ["soek", "soek vir"],
        "open":        ["open", "maak oop"],
    },
    "isiZulu": {
        "volume_up":   ["nyusa ivolumu", "phakamisa ivolumu"],
        "volume_down": ["yehlisa ivolumu"],
        "mute":        ["thulisa"],
        "scroll_up":   ["skrolela phezulu"],
        "scroll_down": ["skrolela phansi"],
        "new_tab":     ["vula ithebhu entsha"],
        "close_tab":   ["vala ithebhu"],
        "go_back":     ["buyela emuva"],
        "refresh":     ["vuselela"],
        "select_all":  ["khetha konke"],
        "copy":        ["kopisha"],
        "paste":       ["namathisela"],
        "search":      ["sesha", "funa"],
        "open":        ["vula"],
    },
    "isiXhosa": {
        "volume_up":   ["nyusa isandi", "nyusa ivolyum"],
        "volume_down": ["hlisa isandi"],
        "mute":        ["cima isandi"],
        "scroll_up":   ["skrolela phezulu"],
        "scroll_down": ["skrolela ezantsi"],
        "new_tab":     ["vula ithebhu entsha"],
        "close_tab":   ["vala ithebhu"],
        "go_back":     ["buyela emva"],
        "refresh":     ["vuselela"],
        "select_all":  ["khetha konke"],
        "copy":        ["khuphela"],
        "paste":       ["ncamathelisa"],
        "search":      ["khangela"],
        "open":        ["vula"],
    },
    "Sesotho": {
        "volume_up":   ["phahamisa modumo", "eketsa modumo"],
        "volume_down": ["fokotsa modumo"],
        "mute":        ["homotsa"],
        "scroll_up":   ["ya hodimo"],
        "scroll_down": ["ya tlase"],
        "new_tab":     ["bula tab e ntjha"],
        "close_tab":   ["kwala tab"],
        "go_back":     ["kgutlela morao"],
        "refresh":     ["ntjhafatsa"],
        "select_all":  ["kgetha tsohle"],
        "copy":        ["kopitsa"],
        "paste":       ["manamisa"],
        "search":      ["batla"],
        "open":        ["bula", "qala"],
    },
    "Setswana": {
        "volume_up":   ["oketsa modumo", "godisa modumo"],
        "volume_down": ["fokotsa modumo"],
        "mute":        ["didimatsa"],
        "scroll_up":   ["tsamaya kwa godimo"],
        "scroll_down": ["tsamaya kwa tlase"],
        "new_tab":     ["bula tab e ntsha"],
        "close_tab":   ["tswala tab"],
        "go_back":     ["boela morago"],
        "refresh":     ["ntlafatsa"],
        "select_all":  ["tlhopha tsotlhe"],
        "copy":        ["kopisa"],
        "paste":       ["kgomaretsa"],
        "search":      ["batla"],
        "open":        ["bula", "simolola"],
    },
    "Sepedi": {
        "volume_up":   ["oketsa modumo", "godisa modumo"],
        "volume_down": ["fokotsa modumo"],
        "mute":        ["homotsa modumo"],
        "scroll_up":   ["ya godimo"],
        "scroll_down": ["ya fase"],
        "new_tab":     ["bula tab ye mpsha"],
        "close_tab":   ["tswala tab"],
        "go_back":     ["boela morago"],
        "refresh":     ["ntlafatsa"],
        "select_all":  ["kgetha tsohle"],
        "copy":        ["kopolla"],
        "paste":       ["manamisa"],
        "search":      ["nyaka"],
        "open":        ["bula", "thoma"],
    },
}

GESTURE_COOLDOWN  = 0.8
GAZE_DWELL_SECS   = 1.8
GAZE_CONFIRM_TOUT = 8.0
WAKE_WORDS        = ("neurolia", "lia", "leah", "liya")


def _parse_multilang(text: str, lang: str) -> dict | None:
    """Map a multilingual phrase to a lia4-compatible action dict."""
    c = (text or "").lower().strip()
    c = re.sub(r"[?!.,]", "", c)
    table = LANG_CMDS.get(lang, LANG_CMDS["English"])

    # action → lia4 action dict
    simple_map = {
        "volume_up":   {"action": "volume_up"},
        "volume_down": {"action": "volume_down"},
        "mute":        {"action": "mute"},
        "scroll_up":   {"action": "scroll_up"},
        "scroll_down": {"action": "scroll_down"},
        "new_tab":     {"action": "new_tab"},
        "close_tab":   {"action": "close_tab"},
        "go_back":     {"action": "go_back"},
        "refresh":     {"action": "refresh"},
        "select_all":  {"action": "select_all"},
        "copy":        {"action": "hotkey", "keys": ["ctrl", "c"], "label": "Copied."},
        "paste":       {"action": "paste"},
    }

    for action, phrases in table.items():
        for phrase in sorted(phrases, key=len, reverse=True):
            if c == phrase or c.startswith(phrase + " "):
                remainder = c[len(phrase):].strip()
                if action in simple_map:
                    return simple_map[action]
                if action == "search":
                    return {"action": "search", "query": remainder, "target": "chrome"}
                if action == "open":
                    return {"action": "open_app", "target": remainder or c}
    return None


# ── UI theme (mirrors lia4.py) ─────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class NeuroLiaProto(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("NeuroLia Prototype")
        self.geometry("1100x720")
        self.minsize(900, 620)
        self.configure(fg_color=C["bg"])

        self._running      = True
        self._cam_active   = False
        self._voice_active = False
        self._lang         = tk.StringVar(value="English")

        # gaze / gesture state
        self._last_gesture: dict[str, float] = {}
        self._hand_x_hist  = deque(maxlen=12)
        self._hand_y_hist  = deque(maxlen=12)
        self._head_hist    = deque(maxlen=15)
        self._gaze_hist    = deque(maxlen=8)
        self._gaze_start   = None
        self._gaze_pt      = None
        self._confirm_evt  = None
        self._confirm_ans  = None

        self.tk.call("proc", "bgerror", "msg", "")
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._quit)

        self.after(400,  self._greet)
        self.after(1000, self._start_camera)
        self.after(1300, self._start_voice)

    # ── helpers ────────────────────────────────────────────────────────────────
    def _f(self, sz=12, w="normal"):
        return ctk.CTkFont(family="Helvetica", size=sz, weight=w)

    def _log(self, who: str, text: str, color=None):
        color = color or C["text"]
        ts = time.strftime("%H:%M:%S")
        self.after(0, lambda: self._append_log(f"[{ts}] {who}: {text}\n", color))

    def _append_log(self, line: str, color: str):
        self._logbox.configure(state="normal")
        self._logbox.insert("end", line)
        self._logbox.see("end")
        self._logbox.configure(state="disabled")

    # ── BUILD ──────────────────────────────────────────────────────────────────
    def _build(self):
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        # ── left panel ────────────────────────────────────────────────────────
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(14, 6), pady=14)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        # header
        hdr = ctk.CTkFrame(left, fg_color=C["panel"], corner_radius=14,
                           border_width=1, border_color=C["border"])
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        hi = ctk.CTkFrame(hdr, fg_color="transparent")
        hi.pack(fill="x", padx=16, pady=12)
        ctk.CTkLabel(hi, text="NeuroLia Prototype", font=self._f(20, "bold"),
                     text_color=C["text"]).pack(side="left")
        ctk.CTkLabel(hi, text="Multilingual · Gaze · Head gestures",
                     font=self._f(10), text_color=C["dim"]).pack(side="left", padx=12)

        # language selector
        lang_row = ctk.CTkFrame(hdr, fg_color="transparent")
        lang_row.pack(fill="x", padx=16, pady=(0, 10))
        ctk.CTkLabel(lang_row, text="Language:", font=self._f(11),
                     text_color=C["dim"]).pack(side="left")
        ctk.CTkOptionMenu(lang_row, variable=self._lang,
                          values=list(LANGUAGES.keys()),
                          fg_color=C["card"], button_color=C["purple"],
                          button_hover_color=C["pur_dim"],
                          font=self._f(11)).pack(side="left", padx=8)

        # log
        log_wrap = ctk.CTkFrame(left, fg_color=C["panel"], corner_radius=14,
                                border_width=1, border_color=C["border"])
        log_wrap.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        log_wrap.grid_rowconfigure(0, weight=1)
        log_wrap.grid_columnconfigure(0, weight=1)

        self._logbox = tk.Text(log_wrap, bg=C["panel"], fg=C["text"],
                               insertbackground=C["text"], font=("Consolas", 11),
                               wrap="word", state="disabled", relief="flat",
                               padx=12, pady=12)
        self._logbox.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        # input bar
        bar = ctk.CTkFrame(left, fg_color=C["panel"], corner_radius=14,
                           border_width=1, border_color=C["border"])
        bar.grid(row=2, column=0, sticky="ew")
        bi = ctk.CTkFrame(bar, fg_color="transparent")
        bi.pack(fill="x", padx=10, pady=10)
        self._entry = ctk.CTkEntry(bi, height=42,
                                   placeholder_text="Type a command...",
                                   fg_color=C["card"], border_color=C["border"],
                                   text_color=C["text"], font=self._f(12))
        self._entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._entry.bind("<Return>", lambda e: self._send_text())
        ctk.CTkButton(bi, text="Send", width=68, height=42, corner_radius=10,
                      fg_color=C["purple"], hover_color=C["pur_dim"],
                      font=self._f(12, "bold"),
                      command=self._send_text).pack(side="left", padx=(0, 6))
        ctk.CTkButton(bi, text="Stop", width=60, height=42, corner_radius=10,
                      fg_color=C["coral"], hover_color="#8b2020",
                      font=self._f(11, "bold"),
                      command=stop_speaking).pack(side="left")

        # ── right panel ───────────────────────────────────────────────────────
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(0, 14), pady=14)
        right.grid_rowconfigure(1, weight=1)
        right.grid_columnconfigure(0, weight=1)

        cam_hdr = ctk.CTkFrame(right, fg_color="transparent")
        cam_hdr.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ctk.CTkLabel(cam_hdr, text="Camera — gesture + gaze",
                     font=self._f(12, "bold"), text_color=C["text"]).pack(side="left")
        self._cam_status = ctk.CTkLabel(cam_hdr, text="● Starting",
                                        font=self._f(10), text_color=C["amber"])
        self._cam_status.pack(side="right")

        cam_wrap = ctk.CTkFrame(right, fg_color=C["card"], corner_radius=12,
                                border_width=1, border_color=C["border"])
        cam_wrap.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        cam_wrap.grid_rowconfigure(0, weight=1)
        cam_wrap.grid_columnconfigure(0, weight=1)
        self._cam_lbl = ctk.CTkLabel(cam_wrap,
                                     text="📷  Camera loading...",
                                     font=self._f(11), text_color=C["dim"])
        self._cam_lbl.grid(row=0, column=0, sticky="nsew")

        # gaze / gesture status
        info = ctk.CTkFrame(right, fg_color=C["card"], corner_radius=10,
                            border_width=1, border_color=C["border"])
        info.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ii = ctk.CTkFrame(info, fg_color="transparent")
        ii.pack(fill="x", padx=12, pady=8)
        self._gesture_lbl = ctk.CTkLabel(ii, text="Gesture: —",
                                         font=self._f(10), text_color=C["dim"])
        self._gesture_lbl.pack(anchor="w")
        self._gaze_lbl = ctk.CTkLabel(ii, text="Gaze: —",
                                      font=self._f(10), text_color=C["dim"])
        self._gaze_lbl.pack(anchor="w")
        self._conf_lbl = ctk.CTkLabel(ii, text="Confidence: —",
                                      font=self._f(10), text_color=C["dim"])
        self._conf_lbl.pack(anchor="w")

        # confirmation banner
        self._confirm_banner = ctk.CTkLabel(right, text="",
                                            font=self._f(12, "bold"),
                                            text_color=C["text"],
                                            fg_color=C["pur_dim"],
                                            corner_radius=8, wraplength=340)
        self._confirm_banner.grid(row=3, column=0, sticky="ew", pady=(0, 8))

        # gesture legend
        leg = ctk.CTkFrame(right, fg_color=C["card"], corner_radius=10,
                           border_width=1, border_color=C["border"])
        leg.grid(row=4, column=0, sticky="ew")
        li = ctk.CTkFrame(leg, fg_color="transparent")
        li.pack(fill="x", padx=12, pady=8)
        ctk.CTkLabel(li, text="GESTURES", font=self._f(9, "bold"),
                     text_color=C["dim"]).pack(anchor="w", pady=(0, 4))
        for g, a in [("Fist", "Volume down"),
                     ("Open palm", "Volume up"),
                     ("Swipe right", "Next tab"),
                     ("Swipe left", "Close tab"),
                     ("Hand wave up/down", "Scroll"),
                     ("Nod / Thumbs up", "Confirm"),
                     ("Thumbs down", "Cancel"),
                     ("Pinch index+thumb", "Click"),
                     ("Gaze dwell", "Ask to click")]:
            r = ctk.CTkFrame(li, fg_color="transparent")
            r.pack(fill="x", pady=1)
            ctk.CTkLabel(r, text=g, font=self._f(9), text_color=C["dim"]).pack(side="left")
            ctk.CTkLabel(r, text=a, font=self._f(9), text_color=C["purple"]).pack(side="right")

    # ── greet ──────────────────────────────────────────────────────────────────
    def _greet(self):
        msg = ("Hello! I'm NeuroLia Prototype. "
               "I support multilingual commands, head gestures, and eye gaze. "
               "Say NeuroLia or type a command.")
        self._log("NeuroLia", msg)
        speak(msg)

    # ── voice ──────────────────────────────────────────────────────────────────
    def _start_voice(self):
        if not _SR:
            self._log("System", "SpeechRecognition unavailable — type instead", C["coral"])
            return
        self._voice_active = True
        threading.Thread(target=self._voice_loop, daemon=True).start()

    def _voice_loop(self):
        rec = sr.Recognizer()
        rec.dynamic_energy_threshold = False
        WAKE = re.compile(r"\b(neurolia|lia|leah|liya)\b", re.IGNORECASE)

        # one-time calibration
        self._log("System", "Calibrating microphone...", C["amber"])
        calibrated = 300
        try:
            with sr.Microphone() as src:
                rec.adjust_for_ambient_noise(src, duration=1.5)
                calibrated = max(rec.energy_threshold * 1.2, 200)
                rec.energy_threshold = calibrated
        except Exception:
            rec.energy_threshold = calibrated
        self._log("System", f"Ready — threshold {int(calibrated)}. Say 'NeuroLia' to wake.", C["teal"])

        while self._running and self._voice_active:
            # re-read language each loop so switching the dropdown takes effect immediately
            lang_code = LANGUAGES.get(self._lang.get(), "en-US")

            # ── PHASE 1: wake-word gate ────────────────────────────────────────
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
                heard = rec.recognize_google(wake_audio, language=lang_code).lower().strip()
            except sr.UnknownValueError:
                continue
            except sr.RequestError:
                self._log("System", "No internet — check connection", C["coral"])
                time.sleep(3)
                continue

            if not WAKE.search(heard):
                continue

            # strip wake word — if a command followed inline, use it directly
            inline = WAKE.sub("", heard).strip(" ,.")
            self._log("Voice", f'Wake: "{heard}"', C["purple"])

            if inline and len(inline) >= 2:
                self.after(0, lambda c=inline: self._run(c))
                continue

            # ── PHASE 2: command listen ────────────────────────────────────────
            speak("Yes?")
            time.sleep(0.8)   # wait for TTS to finish before opening mic
            try:
                with sr.Microphone() as src:
                    rec.adjust_for_ambient_noise(src, duration=0.4)
                    rec.energy_threshold = max(rec.energy_threshold * 1.1, calibrated * 0.8)
                    cmd_audio = rec.listen(src, timeout=7, phrase_time_limit=12)
            except sr.WaitTimeoutError:
                self._log("System", "No command heard — say 'NeuroLia' again", C["coral"])
                continue
            except Exception:
                time.sleep(0.5)
                continue

            try:
                command = rec.recognize_google(cmd_audio, language=lang_code).strip()
            except sr.UnknownValueError:
                self._log("System", "Couldn't understand — try again", C["coral"])
                continue
            except sr.RequestError:
                time.sleep(3)
                continue

            if not command or len(command.strip()) < 2:
                continue

            clean = WAKE.sub("", command).strip(" ,.")
            if not clean:
                speak("I'm listening. What would you like me to do?")
                continue

            self._log("Voice", f'Command: "{clean}"', C["teal"])
            self.after(0, lambda c=clean: self._run(c))

    # ── command dispatch ───────────────────────────────────────────────────────
    def _send_text(self):
        t = self._entry.get().strip()
        if t:
            self._entry.delete(0, "end")
            self._run(t)

    def _run(self, text: str):
        self._log("You", text)
        threading.Thread(target=self._process, args=(text,), daemon=True).start()

    def _process(self, text: str):
        lang = self._lang.get()

        # 1. multilingual table (non-English wake phrases)
        data = _parse_multilang(text, lang)

        # 2. engine local parser (fast, no network)
        if data is None:
            from engine import parse_command as _eng_parse
            data = _eng_parse(text)

        # 3. GPT / local fallback
        if data is None:
            data = ask_gpt(text)

        if not isinstance(data, dict):
            data = _local_parse(text)

        data = _normalize_action(data)
        reply = str(data.get("reply") or "Done.")
        action = data.get("action", "converse")

        self._log("NeuroLia", reply, C["teal"])
        speak(reply)

        if action == "converse":
            return
        if action == "exit":
            self.after(1500, self._quit)
            return
        if action in ("cursor_on", "cursor_off", "cursor_toggle"):
            # prototype has no real cursor controller; just log it
            self._log("System", f"Cursor mode: {action}", C["amber"])
            return
        if not is_allowed(data):
            self._log("System", "Action not allowed.", C["coral"])
            return
        if needs_confirmation(data):
            prompt = confirmation_prompt(data)
            self._log("NeuroLia", prompt, C["amber"])
            speak(prompt)
            return

        result = execute(data, confirmed=True)
        color = C["coral"] if is_failure(result) else C["teal"]
        self._log("Action", result, color)

    # ── camera ─────────────────────────────────────────────────────────────────
    def _start_camera(self):
        if not _CAM:
            self.after(0, lambda: self._cam_status.configure(
                text="● Not installed", text_color=C["coral"]))
            return
        self._cam_active = True
        self.after(0, lambda: self._cam_status.configure(
            text="● Live", text_color=C["teal"]))
        threading.Thread(target=self._cam_loop, daemon=True).start()

    def _cam_loop(self):
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            self.after(0, lambda: self._cam_status.configure(
                text="● No camera", text_color=C["coral"]))
            return

        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        _ui_pending = False

        def _clear():
            nonlocal _ui_pending
            _ui_pending = False

        with mp.solutions.hands.Hands(
                max_num_hands=1,
                min_detection_confidence=0.6,
                min_tracking_confidence=0.5) as hands, \
             mp.solutions.face_mesh.FaceMesh(
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.6,
                min_tracking_confidence=0.5) as face_mesh:

            while self._running and self._cam_active:
                ok, frame = cap.read()
                if not ok:
                    break
                frame = cv2.flip(frame, 1)
                rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                hr    = hands.process(rgb)
                fr    = face_mesh.process(rgb)

                gesture = None
                finger_tip_px = None  # index fingertip in frame pixels for cursor dot

                if hr.multi_hand_landmarks:
                    hl = hr.multi_hand_landmarks[0]
                    gesture = self._detect_hand(hl)
                    # compute fingertip pixel position for the on-screen cursor dot
                    tip = hl.landmark[8]
                    h2f, w2f = frame.shape[:2]
                    finger_tip_px = (int(tip.x * w2f), int(tip.y * h2f))

                if fr.multi_face_landmarks:
                    face = fr.multi_face_landmarks[0]
                    hg = self._detect_head(face)
                    if hg:
                        gesture = hg
                    self._process_gaze(face, frame.shape[1], frame.shape[0])

                if gesture:
                    self.after(0, lambda g=gesture: self._trigger_gesture(g))

                # draw finger cursor dot (no mouse/keyboard — purely visual on the feed)
                if finger_tip_px:
                    cv2.circle(frame, finger_tip_px, 10, (139, 100, 255), -1)
                    cv2.circle(frame, finger_tip_px, 13, (200, 170, 255), 2)

                # draw gaze cursor
                if self._gaze_pt:
                    gx, gy = self._gaze_pt
                    h2, w2 = frame.shape[:2]
                    cv2.circle(frame, (int(gx * w2), int(gy * h2)), 12, (32, 201, 122), 2)

                if not _ui_pending:
                    h2, w2 = frame.shape[:2]
                    tw = min(240, w2)
                    th = int(h2 * tw / w2)
                    sm = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), (tw, th))
                    img = ctk.CTkImage(light_image=Image.fromarray(sm), size=(tw, th))
                    _ui_pending = True
                    self.after(0, lambda p=img: (
                        self._cam_lbl.configure(image=p, text="") or _clear()))

        cap.release()

    # ── hand gesture detection ─────────────────────────────────────────────────
    def _detect_hand(self, hand) -> str | None:
        lm = hand.landmark

        # normalised hand size (wrist to middle-MCP) for ratio comparisons
        size = math.hypot(lm[0].x - lm[9].x, lm[0].y - lm[9].y) or 1e-6

        # pinch: thumb tip (4) close to index tip (8) — checked FIRST
        pinch_ratio = math.hypot(lm[4].x - lm[8].x, lm[4].y - lm[8].y) / size
        if pinch_ratio < 0.30:
            return "pinch"

        ext = [lm[t].y < lm[p].y for t, p in [(8, 6), (12, 10), (16, 14), (20, 18)]]
        count = sum(ext)
        palm  = lm[9]

        if count == 0:
            self._hand_x_hist.append(palm.x)
            self._hand_y_hist.append(palm.y)
            return "fist"

        if count >= 4:
            self._hand_x_hist.append(palm.x)
            self._hand_y_hist.append(palm.y)
            if len(self._hand_x_hist) >= 8:
                dx = self._hand_x_hist[-1] - self._hand_x_hist[0]
                if abs(dx) > 0.22:
                    self._hand_x_hist.clear()
                    return "hand_swipe_right" if dx > 0 else "hand_swipe_left"
                dy = self._hand_y_hist[-1] - self._hand_y_hist[0]
                if abs(dy) > 0.18:
                    self._hand_y_hist.clear()
                    return "hand_wave_down" if dy > 0 else "hand_wave_up"
            return "open_palm"

        if lm[4].y < lm[3].y and count <= 1:
            return "thumbs_up"
        if lm[4].y > lm[3].y and count <= 1:
            return "thumbs_down"
        return None

    # ── head gesture detection ─────────────────────────────────────────────────
    def _detect_head(self, face) -> str | None:
        nose = face.landmark[1]
        self._head_hist.append((nose.x, nose.y, time.time()))
        if len(self._head_hist) < 10:
            return None
        x0, y0, _ = self._head_hist[0]
        x1, y1, _ = self._head_hist[-1]
        dx, dy = x1 - x0, y1 - y0
        if abs(dy) > 0.16 and abs(dy) > abs(dx) * 1.2:
            self._head_hist.clear()
            return "head_nod"
        if abs(dx) > 0.18 and abs(dx) > abs(dy) * 1.2:
            self._head_hist.clear()
            return "head_right" if dx > 0 else "head_left"
        return None

    # ── gaze processing ────────────────────────────────────────────────────────
    def _process_gaze(self, face, w, h):
        lm = face.landmark
        if len(lm) < 478:
            return
        def _ratio(v, a, b):
            span = b - a
            return (v - a) / span if abs(span) > 0.0001 else 0.5

        li, ri = lm[468], lm[473]
        gx = max(0.0, min(1.0, (_ratio(li.x, lm[33].x, lm[133].x) +
                                 _ratio(ri.x, lm[362].x, lm[263].x)) / 2))
        gy = max(0.0, min(1.0, (_ratio(li.y, lm[159].y, lm[145].y) +
                                 _ratio(ri.y, lm[386].y, lm[374].y)) / 2))

        self._gaze_hist.append((gx, gy))
        avg_x = sum(p[0] for p in self._gaze_hist) / len(self._gaze_hist)
        avg_y = sum(p[1] for p in self._gaze_hist) / len(self._gaze_hist)
        self._gaze_pt = (avg_x, avg_y)

        xs = [p[0] for p in self._gaze_hist]
        ys = [p[1] for p in self._gaze_hist]
        conf = max(0.2, min(0.98, 1.0 - (max(xs)-min(xs) + max(ys)-min(ys)) * 2.5))

        self.after(0, lambda x=avg_x, y=avg_y, c=conf: (
            self._gaze_lbl.configure(text=f"Gaze: X={x:.2f} Y={y:.2f}"),
            self._conf_lbl.configure(text=f"Confidence: {c:.0%}")))

        now = time.time()
        if self._gaze_start is None:
            self._gaze_start = now
        if now - self._gaze_start >= GAZE_DWELL_SECS:
            self._gaze_start = now + 999
            threading.Thread(target=self._gaze_dwell,
                             args=(avg_x, avg_y, conf), daemon=True).start()

    def _gaze_dwell(self, x, y, conf):
        q = f"Gaze dwell at {x:.2f}, {y:.2f} (confidence {conf:.0%}). Click here?"
        self.after(0, lambda: self._confirm_banner.configure(text=q))
        speak(q)
        self._confirm_evt = threading.Event()
        self._confirm_ans = None
        answered = self._confirm_evt.wait(GAZE_CONFIRM_TOUT)
        self.after(0, lambda: self._confirm_banner.configure(text=""))
        if answered and self._confirm_ans is True and _GUI:
            sw, sh = pyautogui.size()
            pyautogui.click(int(x * sw), int(y * sh))
            self._log("Gaze", "Clicked gaze location.", C["teal"])
        self._gaze_start = None

    # ── gesture actions ────────────────────────────────────────────────────────
    def _trigger_gesture(self, gesture: str):
        now = time.time()
        if now - self._last_gesture.get(gesture, 0) < GESTURE_COOLDOWN:
            return
        self._last_gesture[gesture] = now
        self.after(0, lambda: self._gesture_lbl.configure(text=f"Gesture: {gesture}"))

        action_map = {
            "fist":             {"action": "volume_down"},
            "open_palm":        {"action": "volume_up"},
            "hand_swipe_right": {"action": "new_tab"},
            "hand_swipe_left":  {"action": "close_tab"},
            "hand_wave_up":     {"action": "scroll_up"},
            "hand_wave_down":   {"action": "scroll_down"},
            "head_left":        {"action": "go_back"},
            "head_right":       {"action": "switch_tab"},
            "pinch":            {"action": "mouse_click"},
            "head_nod":         {"action": "scroll_up"},
        }

        if gesture in ("thumbs_up", "head_nod"):
            self._log("Gesture", f"{gesture} -> Confirm", C["purple"])
            if self._confirm_evt:
                self._confirm_ans = True
                self._confirm_evt.set()
            return

        if gesture == "thumbs_down":
            self._log("Gesture", "thumbs_down -> Cancel", C["purple"])
            if self._confirm_evt:
                self._confirm_ans = False
                self._confirm_evt.set()
            return

        data = action_map.get(gesture)
        if not data:
            return
        data = _normalize_action(data)
        result = execute(data, confirmed=True)
        self._log("Gesture", f"{gesture} -> {result}", C["purple"])

    # ── quit ───────────────────────────────────────────────────────────────────
    def _quit(self):
        self._running     = False
        self._cam_active  = False
        self._voice_active = False
        if self._confirm_evt:
            self._confirm_ans = False
            self._confirm_evt.set()
        self.destroy()


def main():
    app = NeuroLiaProto()
    app.mainloop()


if __name__ == "__main__":
    main()
