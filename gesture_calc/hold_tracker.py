"""
hold_tracker.py
---------------
"Hold the sign for ~0.5 s to confirm it" logic.

Why we need this
  * The camera sees a gesture on every frame (15-30 times per second).  We must
    NOT type a digit on every frame - only once the user has *held* the sign
    steadily for `hold_seconds`.
  * After a sign is accepted it is "locked": the user has to change the sign (or
    lower the hand) before the same sign can be accepted again.  This is what
    makes "5" then "6" become 56, and "5, hand down, 5" become 55.
"""
from __future__ import annotations

from collections import Counter, deque
from typing import Deque, Optional, Tuple

from .gestures import Gesture


class HoldTracker:
    def __init__(self, hold_seconds: float = 0.5, smooth_frames: int = 5):
        self.hold_seconds = hold_seconds
        # Majority vote over the last few frames removes one-frame flicker
        self._window: Deque[Optional[Gesture]] = deque(maxlen=smooth_frames)
        self._candidate: Optional[Gesture] = None  # sign currently being held
        self._since: float = 0.0                    # when the candidate first appeared
        self._locked: Optional[Gesture] = None      # last accepted sign (blocks repeats)

    def reset(self) -> None:
        self._window.clear()
        self._candidate = None
        self._locked = None

    def update(self, gesture: Optional[Gesture], now: float) -> Tuple[Optional[Gesture], float]:
        """Feed the gesture seen in the current frame.

        Returns (accepted_gesture, progress):
          accepted_gesture - the sign that was just confirmed, otherwise None
          progress         - 0.0 .. 1.0 hold progress (for the progress bar)
        """
        # 1) Smooth: take the most common value of the last few frames
        self._window.append(gesture)
        stable = Counter(self._window).most_common(1)[0][0]

        # 2) Track how long the same stable sign has been visible
        if stable != self._candidate:
            self._candidate = stable
            self._since = now

        # 3) No hand / unknown sign -> re-arm, so the same digit can be typed again
        if stable is None:
            self._locked = None
            return None, 0.0

        # 4) A different sign than the locked one -> unlock
        if self._locked is not None and stable != self._locked:
            self._locked = None

        # 5) Same sign was already accepted -> wait until the user changes it
        if stable == self._locked:
            return None, 1.0

        # 6) Held long enough? -> accept
        progress = min((now - self._since) / self.hold_seconds, 1.0)
        if progress >= 1.0:
            self._locked = stable
            return stable, 1.0
        return None, progress
