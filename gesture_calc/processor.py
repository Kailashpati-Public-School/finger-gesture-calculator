"""
processor.py
------------
The glue.  For every camera frame it:

    frame -> MediaPipe hands -> finger states -> gesture -> hold tracker -> calculator
                                                                   |
                                          draws overlay <----------+

Thread model (important for Streamlit):
  * `recv()` runs on a WORKER THREAD created by streamlit-webrtc (once per frame).
  * The Streamlit script runs on the MAIN thread and only *reads* our state
    through `get_state()` / `drain_events()`.
  * A lock protects the shared calculator state between the two threads.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Dict, List

import av
import cv2
import mediapipe as mp
from streamlit_webrtc import VideoProcessorBase

from .calculator import CalcEvent, Calculator
from .gestures import Gesture, classify_hands, get_finger_states
from .hold_tracker import HoldTracker

_mp_hands = mp.solutions.hands
_mp_draw = mp.solutions.drawing_utils
_FONT = cv2.FONT_HERSHEY_SIMPLEX


def _fit_text(text: str, max_width: int, base_scale: float = 1.0, thickness: int = 2):
    """Shrink the text (and finally cut its left part) so it fits inside the frame."""
    scale = base_scale
    while scale > 0.5:
        if cv2.getTextSize(text, _FONT, scale, thickness)[0][0] <= max_width:
            return text, scale
        scale -= 0.1
    # Still too long: keep the END of the expression - the newest input matters most
    while len(text) > 4 and cv2.getTextSize(".." + text, _FONT, 0.5, thickness)[0][0] > max_width:
        text = text[1:]
    return ".." + text, 0.5


class GestureVideoProcessor(VideoProcessorBase):
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calc = Calculator()
        self.tracker = HoldTracker(hold_seconds=0.5)
        self.show_landmarks = True                 # set from the sidebar
        self._events: "queue.Queue[CalcEvent]" = queue.Queue()  # consumed by the UI (speech)
        self._gesture_label = "No hand"
        self._progress = 0.0
        # model_complexity=0 is the light model: fast enough for a free cloud CPU
        self._hands = _mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,                       # two hands are needed for digits 6-9
            model_complexity=0,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.5,
        )

    # ------------------------------------------------------------ worker thread
    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        image = frame.to_ndarray(format="bgr24")
        image = cv2.flip(image, 1)                 # mirror view feels natural
        height, width = image.shape[:2]

        # 1) Find hands
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False                # small speed-up for MediaPipe
        results = self._hands.process(rgb)

        # 2) Landmarks -> finger states (one entry per visible hand)
        hands = []
        for hand in results.multi_hand_landmarks or []:
            hands.append(get_finger_states(hand.landmark, width, height))
            if self.show_landmarks:
                _mp_draw.draw_landmarks(image, hand, _mp_hands.HAND_CONNECTIONS)

        # 3) Finger states -> gesture -> "held long enough?"
        gesture = classify_hands(hands)
        accepted, progress = self.tracker.update(gesture, time.monotonic())

        # 4) Update the calculator + prepare overlay text (under the lock)
        with self._lock:
            if gesture:
                self._gesture_label = gesture.label
            else:
                self._gesture_label = "Unknown sign" if hands else "No hand"
            self._progress = progress
            if accepted:
                self._apply(accepted)
            expression = self.calc.expression_text(pretty=False)
            answer = self._answer_line()

        # 5) Draw what the child should see on the video itself
        self._draw_overlay(image, self._gesture_label, progress, expression, answer)
        return av.VideoFrame.from_ndarray(image, format="bgr24")

    def _apply(self, gesture: Gesture) -> None:
        """Send an accepted gesture to the calculator (called with the lock held)."""
        if gesture.kind == "digit":
            event = self.calc.input_digit(gesture.value)
        elif gesture.kind == "operator":
            event = self.calc.input_operator(gesture.value)
        elif gesture.kind == "equals":
            event = self.calc.equals()
        elif gesture.kind == "clear":
            event = self.calc.clear()
        else:  # "back"
            event = self.calc.backspace()
        self._events.put(event)

    def _answer_line(self) -> str:
        if self.calc.error:
            return self.calc.error
        return f"= {self.calc.result}" if self.calc.result is not None else self.calc.message

    @staticmethod
    def _draw_overlay(image, label: str, progress: float, expression: str, answer: str) -> None:
        height, width = image.shape[:2]
        # Semi-transparent dark bars so white text is readable on any background
        shade = image.copy()
        cv2.rectangle(shade, (0, 0), (width, 44), (0, 0, 0), -1)
        cv2.rectangle(shade, (0, height - 84), (width, height), (0, 0, 0), -1)
        cv2.addWeighted(shade, 0.55, image, 0.45, 0, image)

        cv2.putText(image, f"Sign: {label}", (10, 31), _FONT, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.rectangle(image, (0, 44), (int(width * progress), 50), (0, 220, 0), -1)  # hold progress

        text, scale = _fit_text(expression or "-", width - 20)
        cv2.putText(image, text, (10, height - 50), _FONT, scale, (255, 255, 255), 2, cv2.LINE_AA)
        colour = (0, 255, 0) if answer.startswith("=") else (80, 180, 255)
        cv2.putText(image, answer, (10, height - 14), _FONT, 0.9, colour, 2, cv2.LINE_AA)

    # -------------------------------------------------------- main (UI) thread
    def get_state(self) -> Dict:
        """Thread-safe snapshot for the Streamlit page."""
        with self._lock:
            return {
                "expression": self.calc.expression_text(),
                "result": self.calc.result,
                "error": self.calc.error,
                "message": self.calc.message,
                "history": list(self.calc.history[-5:]),
                "gesture": self._gesture_label,
                "progress": round(self._progress, 1),
            }

    def drain_events(self) -> List[CalcEvent]:
        """Return (and remove) all calculator events since the last call."""
        events: List[CalcEvent] = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except queue.Empty:
                return events
