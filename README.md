# NeuroLia (Lia) — a computer anyone can use, with just a voice or a hand

> **HackOnVibe — "Build a Product That Spreads"**

NeuroLia is a Windows desktop assistant that lets people control a computer **by voice, hand gestures or head movement** — no mouse or keyboard needed. It was built for people who are blind, deaf, non-verbal, have limited hand use or motor impairments, and it works just as well for anyone who wants hands-free control.

## Why it spreads
- **One sentence to explain:** "Say *Lia* and control your computer."
- **Every user is a messenger:** the people who need it (and the families, carers, teachers and schools around them) are the ones who recommend it.
- **Free tier works offline:** voice commands run locally; the optional AI brain only adds natural-language understanding.
- **Multilingual:** command engine includes South African languages (e.g. Setswana), so it reaches people other assistants ignore.

## What it does
| Need | Feature |
|---|---|
| Blind / low vision | Reads the screen aloud (window titles + OCR), describes what opened |
| Limited hand use | Always-on voice listener with the "Lia" wake word, 30+ app launcher, dictation into any field |
| Deaf / non-verbal | Gesture + text input mode, camera gesture panel (swipe left/right to change tabs) |
| Everyone | Open apps, search the web, copy/paste, scroll, volume, screenshots by voice |

## Run it (Windows 10/11, Python 3.10+)
```bash
pip install -r requirements.txt
# Optional: install Tesseract OCR for screen reading (https://github.com/UB-Mannheim/tesseract/wiki)
set OPENAI_API_KEY=your-key        # optional – without it Lia uses the built-in local parser
set LIA_OWNER_NAME=Alex            # optional – enables owner profile
python lia4.py
```
Sign in with any name, or use **voice login** (say your name).

## Project layout
- `lia4.py` – main app (GUI, voice listener, camera panel, command execution)
- `lia_core.py` – shared app matching, command safety/confirmation, gesture stabilization, and OCR lookup
- `neurolia_prototype.py` – multilingual command engine prototype
- `voice.py`, `screen_reader.py`, `commands.py`, `onboarding.py` – supporting modules
- `tests/` – unit tests for the command engine and aliases

## Honest limits (v1)
- Windows only; needs a webcam and microphone for gestures and voice.
- Speech recognition uses Google's online service; the AI brain needs an API key.
- Gesture recognition is rule-based. Sign-language recognition is **not** implemented.
- Closing tabs/windows and locking the screen require spoken confirmation.

## Roadmap
1. One-click installer and a shareable "Lia setup" profile for each user
2. More South African languages in the command engine
3. Trained gesture model with accuracy results
4. Shareable demo clips users can post ("Look what I did with just my voice")
