import speech_recognition as sr, sys, pyttsx3

sys.stdout.reconfigure(encoding='utf-8')

# --- mic scan ---
print("=== Microphone scan ===")
for idx in [8, 1, 3, 4, 0]:
    try:
        with sr.Microphone(device_index=idx) as src:
            r = sr.Recognizer()
            r.dynamic_energy_threshold = False
            r.adjust_for_ambient_noise(src, duration=0.5)
            print(f"Mic {idx} OK  threshold={r.energy_threshold:.0f}")
    except Exception as e:
        print(f"Mic {idx} FAIL: {type(e).__name__}: {e}")

# --- TTS test ---
print("\n=== TTS test ===")
try:
    e = pyttsx3.init()
    voices = e.getProperty('voices')
    print(f"Voices available: {len(voices)}")
    for v in voices[:3]:
        print(" ", v.id)
    e.say("Lia voice test")
    e.runAndWait()
    print("TTS OK")
except Exception as e:
    print(f"TTS FAIL: {e}")

# --- quick listen test ---
print("\n=== Listen test (3s) ===")
try:
    r = sr.Recognizer()
    r.dynamic_energy_threshold = False
    r.energy_threshold = 300
    with sr.Microphone(device_index=8) as src:
        print("Listening for 3s on mic 8...")
        audio = r.listen(src, timeout=3, phrase_time_limit=3)
    text = r.recognize_google(audio)
    print(f"Heard: {text}")
except sr.WaitTimeoutError:
    print("Timeout - no speech detected (mic may be working but silent)")
except sr.UnknownValueError:
    print("Could not understand audio")
except Exception as e:
    print(f"Listen FAIL: {type(e).__name__}: {e}")
