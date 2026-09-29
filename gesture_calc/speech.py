"""
speech.py
---------
Text-to-speech using the BROWSER's built-in Web Speech API.

Why the browser and not a Python library (pyttsx3 / gTTS)?
  * When the app is deployed, Python runs on a remote server that has no speaker.
    Sound has to come out of the *user's* device -> so the browser must speak.
  * No extra pip package, no internet call, works on Chrome / Edge / Android.
"""
from __future__ import annotations

import json
import uuid
from typing import Optional

import streamlit as st

from .calculator import CalcEvent

# UI label -> internal mode
SPEECH_MODES = {
    "Only the final answer": "result",
    "Answer + each operator": "operator",
    "Every accepted gesture": "every",
}

# UI label -> (words key, browser voice language)
LANGUAGES = {"English": ("en", "en-US"), "Hindi": ("hi", "hi-IN")}

WORDS = {
    "en": {
        "+": "plus", "-": "minus", "*": "multiplied by", "/": "divided by",
        "=": "equals", "clear": "cleared", "zero_div": "Cannot divide by zero",
        "test": "Voice is ready",
    },
    "hi": {
        "+": "जोड़", "-": "घटा", "*": "गुणा", "/": "भाग",
        "=": "बराबर", "clear": "साफ़", "zero_div": "शून्य से भाग नहीं हो सकता",
        "test": "आवाज़ चालू है",
    },
}


def _spoken_expression(tokens: list, words: dict) -> str:
    """['567','+','879'] -> '567 plus 879'."""
    return " ".join(words.get(t, t) for t in tokens)


def build_speech(event: CalcEvent, lang: str, mode: str) -> Optional[str]:
    """Decide WHAT to say for a calculator event (None = stay silent)."""
    words = WORDS[lang]

    # The final answer is always spoken: "567 plus 879 plus 355 equals 1801"
    if event.kind == "equals":
        return f"{_spoken_expression(event.tokens, words)} {words['=']} {event.result}"
    if event.kind == "error":
        return words["zero_div"]

    if mode == "result":
        return None
    if event.kind == "operator":
        if mode == "every":  # digits were already spoken one by one
            return words[event.operator]
        return f"{event.number} {words[event.operator]}".strip()  # "567 plus"
    if mode == "every":
        if event.kind == "digit":
            return event.number
        if event.kind == "clear":
            return words["clear"]
    return None


def speak(text: str, voice_lang: str) -> None:
    """Speak `text` in the user's browser.

    A tiny hidden <script> is rendered.  The random id makes every call a NEW
    element, so Streamlit runs the script again even when the text is repeated.
    The speech is started from the parent page so it keeps playing after this
    small iframe is replaced by the next one.
    """
    script = f"""
    <script>
    // id: {uuid.uuid4().hex}
    (function () {{
      var text = {json.dumps(text)};
      var lang = {json.dumps(voice_lang)};
      var host = window;
      try {{ if (window.parent && window.parent.speechSynthesis) host = window.parent; }} catch (e) {{}}
      try {{
        var utterance = new host.SpeechSynthesisUtterance(text);
        utterance.lang = lang;
        utterance.rate = 0.9;
        host.speechSynthesis.cancel();      // newest sentence wins
        host.speechSynthesis.speak(utterance);
      }} catch (e) {{ console.log("Speech failed:", e); }}
    }})();
    </script>
    """
    # `st.iframe` is the new API; older Streamlit versions only have components.html
    if hasattr(st, "iframe"):
        st.iframe(script.strip(), height=1)
    else:
        import streamlit.components.v1 as components

        components.html(script, height=0)
