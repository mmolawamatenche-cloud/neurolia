import pyautogui
import pytesseract
import subprocess
import psutil
from PIL import Image
from lia_core import find_tesseract

_tesseract_path = find_tesseract()
if _tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = _tesseract_path

def get_open_windows():
    """Returns list of all currently open window titles."""
    import ctypes
    import ctypes.wintypes

    titles = []

    def enum_windows_callback(hwnd, lParam):
        if ctypes.windll.user32.IsWindowVisible(hwnd):
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.strip()
                if title and title not in ["Program Manager", "Windows Input Experience"]:
                    titles.append(title)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    ctypes.windll.user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)
    return titles


def get_active_window_title():
    """Returns the title of the currently focused window."""
    import ctypes
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    buff = ctypes.create_unicode_buffer(length + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, buff, length + 1)
    return buff.value.strip()


def get_running_apps():
    """Returns names of running processes (apps)."""
    apps = set()
    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info["name"]
            if name and not name.endswith("svchost.exe"):
                apps.add(name.replace(".exe", "").capitalize())
        except Exception:
            pass
    return sorted(apps)


def read_screen_text():
    """
    Takes a screenshot and uses OCR to extract visible text.
    Returns a cleaned string of what is on screen.
    """
    screenshot = pyautogui.screenshot()
    text = pytesseract.image_to_string(screenshot)
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 3]
    return " ".join(lines[:30])


def summarise_screen_for_blind():
    """
    Builds a full verbal description of the current screen state.
    Returns a string Lia will speak aloud.
    """
    active = get_active_window_title()
    windows = get_open_windows()

    summary = []

    if active:
        summary.append(f"The active window is: {active}.")

    if windows:
        if len(windows) == 1:
            summary.append(f"You have one window open: {windows[0]}.")
        else:
            listed = ", ".join(windows[:6])
            summary.append(
                f"You have {len(windows)} windows open. "
                f"They are: {listed}."
            )

    screen_text = read_screen_text()
    if screen_text:
        summary.append(
            f"I can see the following text on screen: "
            f"{screen_text[:300]}."
        )

    if not summary:
        summary.append("I cannot detect what is on screen right now.")

    return " ".join(summary)


def describe_after_open(app_name):
    """
    Called right after Lia opens an app.
    Waits briefly then reads what appeared on screen.
    """
    import time
    time.sleep(2.5)

    active = get_active_window_title()
    windows = get_open_windows()
    screen_text = read_screen_text()

    parts = []

    parts.append(f"I have opened {app_name} for you.")

    if active:
        parts.append(f"The window now showing is: {active}.")

    chrome_keywords = ["chrome", "browser", "google", "tab"]
    if any(k in app_name.lower() for k in chrome_keywords):
        tabs = [w for w in windows if "chrome" in w.lower() or "google" in w.lower()]
        if tabs:
            parts.append(
                f"Chrome has {len(tabs)} tab open. "
                f"Current tab is: {tabs[0]}."
            )

    if screen_text:
        parts.append(
            f"On the screen I can read: "
            f"{screen_text[:250]}."
        )

    other_windows = [w for w in windows if app_name.lower() not in w.lower()]
    if other_windows:
        listed = ", ".join(other_windows[:4])
        parts.append(
            f"You also still have these open in the background: "
            f"{listed}."
        )

    return " ".join(parts)