"""
app.py - Streamlit page for the Finger Gesture Calculator.

Run locally :  streamlit run app.py
Deploy      :  push to GitHub -> https://share.streamlit.io  (see README.md)

Page layout
  +------------------------------+--------------------------+
  |  live camera (WebRTC)        |  big display: 567 + 879  |
  |  with overlay                |  = 1801                  |
  |                              |  current sign + progress |
  |                              |  history                 |
  +------------------------------+--------------------------+
"""
import html
import time

import streamlit as st
from streamlit_webrtc import WebRtcMode, webrtc_streamer

from gesture_calc.guide import build_guide_image
from gesture_calc.processor import GestureVideoProcessor
from gesture_calc.speech import LANGUAGES, SPEECH_MODES, build_speech, speak

st.set_page_config(page_title="Finger Gesture Calculator", page_icon="🖐️", layout="wide")

# A public STUN server lets the browser and the cloud server find each other (WebRTC)
RTC_CONFIG = {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}

# Small camera stream = faster processing on a free cloud CPU
CAMERA = {
    "video": {"width": {"ideal": 640}, "height": {"ideal": 480}, "frameRate": {"ideal": 15}},
    "audio": False,
}


# --------------------------------------------------------------------------- helpers
@st.cache_resource
def get_guide_image():
    """Draw the gesture chart once and reuse it."""
    return build_guide_image()


@st.dialog("🖐️ Gesture Guide - which sign means what?", width="large")
def show_guide() -> None:
    """Start-up popup. Close it with the X, or press the button below to skip and start."""
    st.image(get_guide_image())
    st.markdown(
        "**How it works:** show a sign and **hold it steady for about half a second**. "
        "The green bar on the video shows the progress. "
        "Digits keep joining into ONE number until you show an operator. "
        "Show **Equals** to get the answer."
    )
    st.caption("To type the same digit twice (like 55): lower your hand for a moment, then show it again.")
    if st.button("✅ Got it - start the camera", type="primary"):
        st.session_state.want_camera = True  # the camera starts automatically after this
        st.rerun()                           # rerun closes the popup


def render_panel(state: dict, playing: bool) -> str:
    """HTML for the big 'calculator screen' so a child can read input and output."""
    expression = html.escape(state["expression"]) or "&nbsp;"
    if state["error"]:
        answer = f'<span style="color:#ff6b6b">{html.escape(state["error"])}</span>'
    elif state["result"] is not None:
        answer = f'<span style="color:#4ade80">= {html.escape(state["result"])}</span>'
    else:
        answer = f'<span style="color:#94a3b8;font-size:1.1rem">{html.escape(state["message"]) or "&nbsp;"}</span>'

    percent = int(state["progress"] * 100)
    sign = html.escape(state["gesture"]) if playing else "Camera is off"
    return f"""
    <div style="background:#0f172a;border-radius:16px;padding:20px 22px;color:#fff;font-family:monospace">
      <div style="color:#94a3b8;font-size:.85rem">CALCULATION</div>
      <div style="font-size:2.3rem;min-height:3rem;word-break:break-all">{expression}</div>
      <div style="font-size:3rem;min-height:3.6rem">{answer}</div>
      <hr style="border-color:#334155">
      <div style="color:#94a3b8;font-size:.85rem">SIGN SEEN</div>
      <div style="font-size:1.3rem">{sign}</div>
      <div style="background:#334155;border-radius:6px;height:8px;margin-top:8px">
        <div style="background:#22c55e;height:8px;border-radius:6px;width:{percent}%"></div>
      </div>
    </div>"""


def render_history(state: dict) -> str:
    if not state["history"]:
        return ""
    rows = "".join(f"<li>{html.escape(h)}</li>" for h in reversed(state["history"]))
    return f"<b>Previous answers</b><ul style='font-family:monospace'>{rows}</ul>"


EMPTY_STATE = {"expression": "", "result": None, "error": None, "message": "",
               "history": [], "gesture": "No hand", "progress": 0.0}

# --------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    hold_seconds = st.slider("Hold time to accept a sign (sec)", 0.3, 1.5, 0.5, 0.1)
    sound_on = st.toggle("🔊 Speak the calculation", value=True)
    speech_label = st.selectbox("What to speak", list(SPEECH_MODES))
    language_label = st.radio("Voice language", list(LANGUAGES), horizontal=True)
    show_landmarks = st.toggle("Show hand skeleton on video", value=True)
    if st.button("📖 Show gesture guide"):
        show_guide()
    test_voice = st.button("🔈 Test voice")

speech_mode = SPEECH_MODES[speech_label]
words_key, voice_lang = LANGUAGES[language_label]

# --------------------------------------------------------------------------- first visit
if not st.session_state.get("guide_seen"):
    st.session_state.guide_seen = True  # so the popup opens only once per session
    show_guide()

# Auto-start the camera once, right after the user leaves the guide popup
auto_start = bool(st.session_state.get("want_camera")) and not st.session_state.get("camera_autostarted")
if auto_start:
    st.session_state.camera_autostarted = True

# --------------------------------------------------------------------------- main page
st.title("🖐️ Finger Gesture Calculator")
video_col, panel_col = st.columns([3, 2])

with video_col:
    ctx = webrtc_streamer(
        key="gesture-calculator",
        mode=WebRtcMode.SENDRECV,
        rtc_configuration=RTC_CONFIG,
        media_stream_constraints=CAMERA,
        video_processor_factory=GestureVideoProcessor,
        async_processing=True,
        desired_playing_state=True if auto_start else None,
    )
with panel_col:
    panel_slot = st.empty()
    history_slot = st.empty()
speech_slot = st.empty()  # hidden helper that plays the sound

if test_voice:
    with speech_slot.container():
        speak("Voice is ready" if words_key == "en" else "आवाज़ चालू है", voice_lang)

# --------------------------------------------------------------------------- live loop
# The camera thread updates the calculator; this loop copies its state to the page.
# When the user changes a widget or presses STOP, Streamlit re-runs the script and
# this loop is replaced by a new one.
if ctx.state.playing:
    last_state = None
    while True:
        processor = ctx.video_processor
        if processor is not None:
            processor.tracker.hold_seconds = hold_seconds   # sidebar settings -> processor
            processor.show_landmarks = show_landmarks

            state = processor.get_state()
            if state != last_state:                         # redraw only when something changed
                panel_slot.markdown(render_panel(state, playing=True), unsafe_allow_html=True)
                history_slot.markdown(render_history(state), unsafe_allow_html=True)
                last_state = state

            events = processor.drain_events()
            if sound_on:
                sentences = [s for s in (build_speech(e, words_key, speech_mode) for e in events) if s]
                if sentences:
                    with speech_slot.container():
                        speak(". ".join(sentences), voice_lang)
        time.sleep(0.15)
else:
    panel_slot.markdown(render_panel(EMPTY_STATE, playing=False), unsafe_allow_html=True)
    st.info("Press **START** under the video and allow the camera. Then show a hand sign!")
