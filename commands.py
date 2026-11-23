import os
import json
import time
import webbrowser
import pyautogui
import pytesseract
from voice import speak
from screen_reader import describe_after_open, summarise_screen_for_blind
from lia_core import find_tesseract

_tesseract_path = find_tesseract()
if _tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = _tesseract_path

FULL_COMMANDS = {
    "open_chrome":     ("Google Chrome",   lambda: os.system("start chrome")),
    "open_notepad":    ("Notepad",         lambda: os.system("start notepad")),
    "open_calculator": ("Calculator",      lambda: os.system("start calc")),
    "open_explorer":   ("File Explorer",   lambda: os.system("start explorer")),
    "open_word":       ("Microsoft Word",  lambda: os.system("start winword")),
    "open_excel":      ("Microsoft Excel", lambda: os.system("start excel")),
    "copy":            ("Copied",          lambda: pyautogui.hotkey("ctrl", "c")),
    "paste":           ("Pasted",          lambda: pyautogui.hotkey("ctrl", "v")),
    "undo":            ("Undone",          lambda: pyautogui.hotkey("ctrl", "z")),
    "redo":            ("Redone",          lambda: pyautogui.hotkey("ctrl", "y")),
    "select_all":      ("Selected all",    lambda: pyautogui.hotkey("ctrl", "a")),
    "volume_up":       ("Volume up",       lambda: pyautogui.press("volumeup")),
    "volume_down":     ("Volume down",     lambda: pyautogui.press("volumedown")),
    "mute":            ("Muted",           lambda: pyautogui.press("volumemute")),
    "screenshot":      ("Screenshot saved",lambda: pyautogui.screenshot().save("screenshot.png")),
    "scroll_up":       ("Scrolling up",    lambda: pyautogui.scroll(5)),
    "scroll_down":     ("Scrolling down",  lambda: pyautogui.scroll(-5)),
    "close_window":    ("Window closed",   lambda: pyautogui.hotkey("alt", "f4")),
    "minimise":        ("Minimised",       lambda: pyautogui.hotkey("win", "down")),
    "maximise":        ("Maximised",       lambda: pyautogui.hotkey("win", "up")),
    "new_tab":         ("New tab opened",  lambda: pyautogui.hotkey("ctrl", "t")),
    "close_tab":       ("Tab closed",      lambda: pyautogui.hotkey("ctrl", "w")),
    "lock_screen":     ("Screen locked",   lambda: pyautogui.hotkey("win", "l")),
}

APP_OPEN_ACTIONS = {
    "open_chrome", "open_notepad", "open_calculator",
    "open_explorer", "open_word", "open_excel"
}

FULL_GESTURE_COMMANDS = {
    "hand_swipe_right": "new_tab",
    "hand_swipe_left":  "close_tab",
    "head_nod_up":      "scroll_up",
    "head_swipe_left":  "scroll_down",
}


def execute_from_gpt(reply, mode="voice+gesture+gpt+camera", disabilities=None):
    if disabilities is None:
        disabilities = []

    is_blind = "blind" in disabilities

    try:
        data   = json.loads(reply)
        action = data.get("action", "")

        if action == "search":
            query = data.get("query", "")
            speak(f"Searching Google for {query}.", mode)
            webbrowser.open(f"https://www.google.com/search?q={query}")

            if is_blind:
                time.sleep(2.5)
                description = describe_after_open("Google Chrome search results")
                speak(description, mode)
            return

        if action == "exit":
            speak("Goodbye. Closing NeuroLia now.", mode)
            exit()

        if action == "read_screen":
            if is_blind:
                speak("Reading everything on your screen now.", mode)
                description = summarise_screen_for_blind()
                speak(description, mode)
            else:
                speak("Screen reading is available in blind mode.", mode)
            return

        if action in FULL_COMMANDS:
            label, fn = FULL_COMMANDS[action]
            fn()

            if action in APP_OPEN_ACTIONS and is_blind:
                app_name = FULL_COMMANDS[action][0]
                description = describe_after_open(app_name)
                speak(description, mode)
            else:
                speak(label, mode)

        else:
            speak(reply, mode)

    except json.JSONDecodeError:
        speak(reply, mode)


def handle_gesture(gesture, mode="voice+gesture+gpt+camera", disabilities=None):
    if disabilities is None:
        disabilities = []

    action_key = FULL_GESTURE_COMMANDS.get(gesture)
    if action_key and action_key in FULL_COMMANDS:
        label, fn = FULL_COMMANDS[action_key]
        fn()
        speak(label, mode)