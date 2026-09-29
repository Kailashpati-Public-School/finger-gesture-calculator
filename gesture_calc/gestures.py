"""
gestures.py
-----------
Turns MediaPipe hand landmarks into a *gesture* (digit / operator / control).

This module is pure Python (no Streamlit / WebRTC / OpenCV imports), so the
logic can be unit-tested without a camera.

Finger order used everywhere in this project:
    (thumb, index, middle, ring, pinky)   ->   1 = finger is UP, 0 = folded
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

# (thumb, index, middle, ring, pinky) -> True when the finger is extended
Fingers = Tuple[bool, bool, bool, bool, bool]

# ---------------------------------------------------------------------------
# MediaPipe hand landmark ids (21 points per hand)
# ---------------------------------------------------------------------------
WRIST = 0
THUMB_IP, THUMB_TIP = 3, 4
INDEX_MCP = 5
MIDDLE_MCP = 9
PINKY_MCP = 17
# (tip, pip) landmark pairs for index, middle, ring and pinky
FINGER_JOINTS = ((8, 6), (12, 10), (16, 14), (20, 18))

# ---------------------------------------------------------------------------
# Tunable thresholds (change these if detection feels too strict / loose)
# ---------------------------------------------------------------------------
# A finger is "up" when its tip is at least this much farther from the wrist
# than its middle joint (PIP). Works for any hand rotation.
EXT_RATIO = 1.10
# The thumb is "up" when its tip is farther than this fraction of the palm
# size away from the base of the index finger.
THUMB_OPEN_RATIO = 0.55

# For overlay text (OpenCV's default font cannot draw x / division symbols)
ASCII_OPS = {"+": "+", "-": "-", "*": "x", "/": "/"}


@dataclass(frozen=True)
class Gesture:
    """A recognised hand sign.

    kind  : "digit" | "operator" | "equals" | "clear" | "back"
    value : "0".."9"  |  "+", "-", "*", "/"  |  "=", "C", "BACK"
    """

    kind: str
    value: str

    @property
    def label(self) -> str:
        """Human readable name (ASCII only, safe for OpenCV overlay text)."""
        if self.kind == "digit":
            return f"Digit {self.value}"
        if self.kind == "operator":
            return f"Operator {ASCII_OPS[self.value]}"
        return {"equals": "Equals (=)", "clear": "Clear (C)", "back": "Backspace"}[self.kind]


# ---------------------------------------------------------------------------
# Gesture tables.  Key = (thumb, index, middle, ring, pinky) as 0/1
# ---------------------------------------------------------------------------
# One hand shows 0..5.  For 6..9 the user shows TWO hands and the fingers add up.
DIGIT_PATTERNS = {
    (0, 0, 0, 0, 0): 0,  # fist
    (0, 1, 0, 0, 0): 1,  # index
    (0, 1, 1, 0, 0): 2,  # index + middle (victory)
    (0, 1, 1, 1, 0): 3,  # index + middle + ring
    (0, 1, 1, 1, 1): 4,  # four fingers, thumb folded
    (1, 1, 1, 1, 1): 5,  # open palm
}

# Operators and controls.  These shapes are deliberately NOT used by digits,
# so an operator can never be mistaken for a number.
SPECIAL_PATTERNS = {
    (1, 0, 0, 0, 0): Gesture("operator", "+"),  # thumbs up
    (0, 0, 0, 0, 1): Gesture("operator", "-"),  # pinky only
    (0, 1, 0, 0, 1): Gesture("operator", "*"),  # index + pinky ("rock" sign)
    (1, 0, 0, 0, 1): Gesture("operator", "/"),  # thumb + pinky ("call me" sign)
    (1, 1, 0, 0, 0): Gesture("equals", "="),    # thumb + index ("L" shape)
    (1, 1, 1, 0, 0): Gesture("clear", "C"),     # thumb + index + middle
    (0, 0, 1, 1, 1): Gesture("back", "BACK"),   # middle + ring + pinky ("OK" sign)
}


def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def get_finger_states(landmarks: Sequence, width: int, height: int) -> Fingers:
    """Return which of the 5 fingers are up for ONE hand.

    `landmarks` is MediaPipe's list of 21 normalised points (each has .x/.y).
    We use only distances (not "is the tip above the joint"), so the hand can be
    tilted or even sideways and the result stays correct.
    """
    # Convert normalised coords to pixels (keeps the aspect ratio correct)
    pts = [(lm.x * width, lm.y * height) for lm in landmarks]
    wrist = pts[WRIST]
    palm_size = _dist(wrist, pts[MIDDLE_MCP]) or 1.0  # wrist -> middle knuckle

    # --- Thumb: must be far from the index knuckle AND pointing away from the palm
    far_enough = _dist(pts[THUMB_TIP], pts[INDEX_MCP]) > THUMB_OPEN_RATIO * palm_size
    pointing_out = _dist(pts[THUMB_TIP], pts[PINKY_MCP]) > _dist(pts[THUMB_IP], pts[PINKY_MCP])
    thumb_up = far_enough and pointing_out

    # --- Other four fingers: tip must be clearly farther from the wrist than the PIP joint
    others = [
        _dist(wrist, pts[tip]) > EXT_RATIO * _dist(wrist, pts[pip])
        for tip, pip in FINGER_JOINTS
    ]
    return (thumb_up, *others)  # type: ignore[return-value]


def _as_pattern(fingers: Fingers) -> Tuple[int, ...]:
    return tuple(int(f) for f in fingers)


def classify_hands(hands: Sequence[Fingers]) -> Optional[Gesture]:
    """Decide which gesture the visible hand(s) are showing.

    * 0 hands  -> None
    * 1 hand   -> digit 0..5, or an operator / control sign
    * 2 hands  -> BOTH must show digit shapes; the fingers add up (digits 6..9)
    * anything else -> None (unknown sign, ignored)
    """
    if not hands:
        return None

    if len(hands) == 1:
        pattern = _as_pattern(hands[0])
        if pattern in DIGIT_PATTERNS:
            return Gesture("digit", str(DIGIT_PATTERNS[pattern]))
        return SPECIAL_PATTERNS.get(pattern)

    # Two hands: add the finger counts (e.g. open palm 5 + two fingers 2 = 7)
    total = 0
    for fingers in hands[:2]:
        pattern = _as_pattern(fingers)
        if pattern not in DIGIT_PATTERNS:
            return None  # an operator sign is only valid with a single hand
        total += DIGIT_PATTERNS[pattern]
    if total > 9:  # 10 is not a single digit
        return None
    return Gesture("digit", str(total))
