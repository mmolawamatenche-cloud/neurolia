import sqlite3
import pyttsx3
import speech_recognition as sr

engine = pyttsx3.init()
DB     = "users.db"

import os

# Demo owner profile: set LIA_OWNER_* env vars to enable owner login. Nothing personal is stored in code.
MASTER_PROFILE = {
    "email":        os.environ.get("LIA_OWNER_EMAIL", "owner@example.com"),
    "name":         os.environ.get("LIA_OWNER_NAME", "Owner"),
    "full_name":    os.environ.get("LIA_OWNER_FULL_NAME", "Demo Owner"),
    "id_number":    os.environ.get("LIA_OWNER_ID", ""),
    "disabilities": ["none"],
    "input_mode":   "voice+gesture+gpt+camera",
    "role":         "owner",
}

DISABILITY_OPTIONS = {
    "1": ("deaf",     "Deaf or hard of hearing"),
    "2": ("mute",     "Non-verbal or mute"),
    "3": ("blind",    "Blind or low vision"),
    "4": ("handless", "No arms or limited hand use"),
    "5": ("motor",    "Motor impairment"),
    "6": ("none",     "No disabilities"),
}

INPUT_MODES = {
    "deaf":     "gesture+text",
    "mute":     "gesture+text",
    "blind":    "voice_only",
    "handless": "voice_only",
    "motor":    "voice+large_buttons",
    "none":     "voice+gesture+gpt+camera",
}


def speak(text):
    print(f"Lia: {text}")
    engine.say(text)
    engine.runAndWait()


def listen_for_answer(timeout=8):
    recognizer = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)
            print("Lia is listening...")
            audio = recognizer.listen(source, timeout=timeout)
        result = recognizer.recognize_google(audio)
        print(f"User said: {result}")
        return result.lower().strip()
    except sr.WaitTimeoutError:
        speak("I did not hear anything. Please try again.")
        return None
    except sr.UnknownValueError:
        speak("Sorry, I did not catch that. Please try again.")
        return None
    except sr.RequestError:
        speak("Network issue. Please check your connection.")
        return None


def init_db():
    conn = sqlite3.connect(DB)
    c    = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        email        TEXT PRIMARY KEY,
        name         TEXT,
        disabilities TEXT,
        input_mode   TEXT,
        role         TEXT DEFAULT 'user'
    )''')
    conn.commit()
    conn.close()


def save_user(email, name, disabilities, input_mode, role="user"):
    conn = sqlite3.connect(DB)
    c    = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO users VALUES (?,?,?,?,?)",
        (email, name, ",".join(disabilities), input_mode, role)
    )
    conn.commit()
    conn.close()


def load_user(email):
    conn = sqlite3.connect(DB)
    c    = conn.cursor()
    c.execute("SELECT * FROM users WHERE email=?", (email,))
    row  = c.fetchone()
    conn.close()
    if row:
        return {
            "email":        row[0],
            "name":         row[1],
            "disabilities": row[2].split(","),
            "input_mode":   row[3],
            "role":         row[4] if len(row) > 4 else "user",
        }
    return None


def is_master_user(identifier):
    """
    Checks if the identifier matches the master owner.
    Accepts: name, full name, id number, or email — any one match grants access.
    Case insensitive, strips spaces.
    """
    identifier = identifier.lower().strip().replace(" ", "")

    checks = [
        MASTER_PROFILE["name"].lower().replace(" ", ""),
        MASTER_PROFILE["full_name"].lower().replace(" ", ""),
        MASTER_PROFILE["id_number"].replace(" ", ""),
        MASTER_PROFILE["email"].lower().replace(" ", ""),
    ]

    checks = [c for c in checks if c]
    return bool(identifier) and identifier in checks


def master_login():
    """
    Grants instant access to owner — no password, no signup.
    Lia greets by name and activates all features.
    """
    speak(
        f"Welcome back, {MASTER_PROFILE['name']}. "
        f"Owner access granted. "
        f"All features are active. "
        f"How can Lia help you today?"
    )
    print("\n" + "="*40)
    print(f"  OWNER LOGIN — {MASTER_PROFILE['full_name']}")
    print(f"  All features unlocked.")
    print("="*40 + "\n")
    return MASTER_PROFILE


def is_voice_only_session():
    speak(
        "Hello. I am Lia. "
        "Before we begin, do you need me to guide you "
        "through login using only your voice? "
        "Say yes or no."
    )
    answer = listen_for_answer()
    if answer and "yes" in answer:
        return True
    return False


def voice_login_flow():
    speak("I will guide you through everything using my voice.")
    speak("Please say your name or your ID number to identify yourself.")

    identifier = None
    while not identifier:
        raw = listen_for_answer()
        if raw:
            cleaned = raw.strip().replace(" ", "")

            if is_master_user(cleaned):
                return master_login()

            identifier = raw.strip()
            speak(f"I heard {identifier}. Is that correct? Say yes or no.")
            confirm = listen_for_answer()
            if confirm and "yes" in confirm:
                break
            else:
                speak("Let us try again. Please say your name or ID number.")
                identifier = None

    speak("Checking your profile.")
    existing = load_user(identifier)
    if existing:
        speak(
            f"Welcome back {existing['name']}. "
            f"How can Lia help you today?"
        )
        return existing

    speak("I do not have a profile for you yet. Let us create one.")
    speak("What is your first name?")

    name = None
    while not name:
        raw = listen_for_answer()
        if raw:
            name = raw.strip().capitalize()
            speak(f"I heard {name}. Is that correct? Say yes or no.")
            confirm = listen_for_answer()
            if confirm and "yes" in confirm:
                break
            else:
                speak("Let us try again. What is your first name?")
                name = None

    speak("Please say your email address.")
    email = None
    while not email:
        raw = listen_for_answer()
        if raw:
            email = raw.replace(" at ", "@").replace(" dot ", ".").replace(" ", "")
            speak(f"I heard {email}. Is that correct? Say yes or no.")
            confirm = listen_for_answer()
            if confirm and "yes" in confirm:
                break
            else:
                speak("Let us try again. Please say your email address.")
                email = None

    disabilities = voice_disability_selection()
    input_mode   = determine_input_mode(disabilities)

    save_user(email, name, disabilities, input_mode)

    speak(
        f"Profile saved. Hello {name}, "
        f"how can Lia help you today?"
    )

    return {
        "email":        email,
        "name":         name,
        "disabilities": disabilities,
        "input_mode":   input_mode,
        "role":         "user",
    }


def voice_disability_selection():
    speak(
        "I will read out some options. "
        "Say yes to select, or no to skip."
    )
    selected = []
    for key, (dis_key, label) in DISABILITY_OPTIONS.items():
        if dis_key == "none":
            continue
        speak(f"Do you have: {label}?")
        answer = listen_for_answer()
        if answer and "yes" in answer:
            selected.append(dis_key)
            speak(f"Noted.")

    if not selected:
        speak("No disabilities selected. All features will be active.")
        selected = ["none"]
    else:
        speak("Thank you. I have noted your profile.")

    return selected


def typed_login_flow():
    print("\n" + "="*40)
    print("  NeuroLia — Login")
    print("="*40)

    identifier = input(
        "\nEnter your name, ID number, or email: "
    ).strip()

    if is_master_user(identifier):
        return master_login()

    existing = load_user(identifier)
    if existing:
        speak(
            f"Welcome back {existing['name']}. "
            f"How can Lia help you today?"
        )
        return existing

    print("\nNo profile found. Creating new account.")
    name  = input("Enter your first name: ").strip()
    email = input("Enter your email address: ").strip()

    print("\nSelect disabilities (comma separated numbers, Enter to skip):")
    for k, (_, label) in DISABILITY_OPTIONS.items():
        print(f"  {k}. {label}")

    choices  = input("\nYour choice(s): ").strip()
    selected = []

    if choices:
        for c in choices.split(","):
            c = c.strip()
            if c in DISABILITY_OPTIONS:
                key = DISABILITY_OPTIONS[c][0]
                if key != "none":
                    selected.append(key)

    if not selected:
        selected = ["none"]

    input_mode = determine_input_mode(selected)
    save_user(email, name, selected, input_mode)

    speak(f"Hello {name}, how can Lia help you today?")
    return {
        "email":        email,
        "name":         name,
        "disabilities": selected,
        "input_mode":   input_mode,
        "role":         "user",
    }


def determine_input_mode(disabilities):
    if "none"     in disabilities: return "voice+gesture+gpt+camera"
    if "handless" in disabilities: return "voice_only"
    if "blind"    in disabilities: return "voice_only"
    if "deaf"     in disabilities: return "gesture+text"
    if "mute"     in disabilities: return "gesture+text"
    if "motor"    in disabilities: return "voice+large_buttons"
    return "voice+gesture"


def run_onboarding():
    init_db()
    speak("Hello. I am Lia. Welcome to NeuroLia.")
    voice_mode = is_voice_only_session()

    if voice_mode:
        return voice_login_flow()
    else:
        return typed_login_flow()