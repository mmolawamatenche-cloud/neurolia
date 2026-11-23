import speech_recognition as sr
import pyttsx3

_engine = None

def _get_engine():
    global _engine
    if _engine is None:
        try:
            _engine = pyttsx3.init()
        except Exception:
            _engine = None
    return _engine

def speak(text, mode="voice+gesture+gpt+camera"):
    print("NeuroLia:", text)
    e = _get_engine()
    if e:
        try:
            e.say(text)
            e.runAndWait()
        except Exception:
            pass

def listen(timeout=None, phrase_time_limit=None):
    recognizer = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            print("Listening...")
            recognizer.adjust_for_ambient_noise(source, duration=0.8)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        command = recognizer.recognize_google(audio)
        print("You said:", command)
        return command.lower()
    except sr.WaitTimeoutError:
        print("Listen timeout")
        return ""
    except sr.UnknownValueError:
        print("Could not understand audio")
        return ""
    except sr.RequestError as e:
        print("Speech recognition request failed:", e)
        return ""
    except Exception as e:
        print("Unexpected error in listen():", e)
        return ""


def wait_for_wake_word(timeout=5, phrase_time_limit=4):
    recognizer = sr.Recognizer()
    print("Waiting for wake word 'Lia'...")
    while True:
        try:
            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.8)
                audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            try:
                heard = recognizer.recognize_google(audio).lower()
                print("Heard:", heard)
                if "lia" in heard:
                    speak("Yes, I'm listening.")
                    return True  # wake word detected
            except sr.UnknownValueError:
                # couldn't understand audio, continue listening
                continue
            except sr.RequestError as e:
                print("Speech recognition request failed:", e)
                return False
        except sr.WaitTimeoutError:
            # no audio within timeout, continue listening
            continue
        except Exception as e:
            print("Unexpected error in wait_for_wake_word():", e)
            return False
