"""
Unit tests for the camera-free logic.   Run:   pytest -q
"""
from types import SimpleNamespace

from gesture_calc.calculator import Calculator, evaluate
from gesture_calc.gestures import Gesture, classify_hands, get_finger_states
from gesture_calc.hold_tracker import HoldTracker


# ------------------------------------------------------------------ calculator
def type_number(calc, digits):
    for d in digits:
        calc.input_digit(d)


def test_example_from_brief_567_879_355():
    c = Calculator()
    type_number(c, "567"); c.input_operator("+")
    type_number(c, "879"); c.input_operator("+")
    type_number(c, "355")
    assert c.expression_text() == "567 + 879 + 355"
    event = c.equals()
    assert event.kind == "equals" and c.result == "1801"


def test_digits_without_operator_form_one_number():
    c = Calculator()
    type_number(c, "56")
    assert c.current == "56" and c.tokens == []


def test_bodmas_and_division():
    assert evaluate(["2", "+", "3", "*", "4"]) == "14"
    assert evaluate(["10", "/", "4"]) == "2.5"
    assert evaluate(["1", "/", "3"]) == "0.333333"
    assert evaluate(["9", "-", "10"]) == "-1"


def test_divide_by_zero_is_reported():
    c = Calculator()
    type_number(c, "5"); c.input_operator("/"); type_number(c, "0")
    assert c.equals().kind == "error" and c.error


def test_result_is_not_shown_before_equals():
    c = Calculator()
    type_number(c, "2"); c.input_operator("+"); type_number(c, "2")
    assert c.result is None


def test_continue_after_equals_and_new_calculation():
    c = Calculator()
    type_number(c, "2"); c.input_operator("+"); type_number(c, "3"); c.equals()
    c.input_operator("*"); type_number(c, "4")            # 5 * 4
    assert c.equals().result == "20"
    type_number(c, "7")                                    # digit after '=' starts fresh
    assert c.expression_text() == "7" and c.result is None


def test_operator_can_be_changed_and_backspace_works():
    c = Calculator()
    type_number(c, "8"); c.input_operator("+"); c.input_operator("-")
    assert c.expression_text() == "8 \u2212"
    c.backspace()                                          # removes the operator, re-opens 8
    assert c.current == "8" and c.tokens == []
    c.backspace()
    assert c.current == ""


def test_incomplete_expression_is_ignored():
    c = Calculator()
    assert c.equals().kind == "ignored"
    type_number(c, "3"); c.input_operator("+")
    assert c.equals().kind == "ignored"


def test_max_digits_and_leading_zero():
    c = Calculator()
    type_number(c, "1234567890")
    assert len(c.current) == 9
    c.clear(); type_number(c, "007")
    assert c.current == "7"


# ---------------------------------------------------------------- hold tracker
def test_hold_needs_half_a_second_and_does_not_repeat():
    t = HoldTracker(hold_seconds=0.5, smooth_frames=3)
    five = Gesture("digit", "5")
    accepted = []
    now = 0.0
    for _ in range(40):                                    # 40 frames * 0.05 s = 2 s
        got, _ = t.update(five, now)
        if got:
            accepted.append(now)
        now += 0.05
    assert len(accepted) == 1 and 0.45 <= accepted[0] <= 0.7  # accepted once, at ~0.5 s

    # lower the hand, then show 5 again -> can be accepted a second time (55)
    for _ in range(5):
        t.update(None, now); now += 0.05
    again = [t.update(five, now + i * 0.05)[0] for i in range(15)]
    assert any(again)


def test_short_flicker_is_not_accepted():
    t = HoldTracker(hold_seconds=0.5, smooth_frames=3)
    now, got_any = 0.0, False
    for _ in range(6):                                     # only 0.3 s
        got_any |= t.update(Gesture("digit", "3"), now)[0] is not None
        now += 0.05
    assert not got_any


# ------------------------------------------------------------ classification
UP, DOWN = True, False


def test_single_hand_signs():
    assert classify_hands([(DOWN, UP, DOWN, DOWN, DOWN)]) == Gesture("digit", "1")
    assert classify_hands([(UP, UP, UP, UP, UP)]) == Gesture("digit", "5")
    assert classify_hands([(DOWN,) * 5]) == Gesture("digit", "0")
    assert classify_hands([(UP, DOWN, DOWN, DOWN, DOWN)]) == Gesture("operator", "+")
    assert classify_hands([(UP, UP, DOWN, DOWN, DOWN)]) == Gesture("equals", "=")
    assert classify_hands([(DOWN, DOWN, UP, DOWN, DOWN)]) is None  # unknown sign
    assert classify_hands([]) is None


def test_two_hands_add_up_to_6_to_9():
    five, two = (UP,) * 5, (DOWN, UP, UP, DOWN, DOWN)
    assert classify_hands([five, two]) == Gesture("digit", "7")
    assert classify_hands([five, five]) is None            # 10 is not a digit
    assert classify_hands([five, (UP, DOWN, DOWN, DOWN, DOWN)]) is None  # '+' needs one hand


def test_every_sign_is_unique():
    from gesture_calc.gestures import DIGIT_PATTERNS, SPECIAL_PATTERNS
    assert not set(DIGIT_PATTERNS) & set(SPECIAL_PATTERNS)


# ------------------------------------------------------ finger detection maths
def _hand(fingers_up):
    """Build 21 synthetic landmarks for an upright hand (wrist at the bottom)."""
    pts = [(0.5, 0.9)] * 21
    pts = list(pts)
    pts[0] = (0.5, 0.9)                                    # wrist
    knuckle_x = {5: 0.42, 9: 0.48, 13: 0.54, 17: 0.60}     # MCP x of index..pinky
    for mcp_id, up in zip((5, 9, 13, 17), fingers_up[1:]):
        x = knuckle_x[mcp_id]
        pts[mcp_id] = (x, 0.65)
        pts[mcp_id + 1] = (x, 0.55)                        # PIP
        pts[mcp_id + 2] = (x, 0.47 if up else 0.62)        # DIP
        pts[mcp_id + 3] = (x, 0.38 if up else 0.68)        # TIP (folded = curls back to palm)
    # thumb: base near the palm, tip far to the left when up, on the palm when folded
    pts[1], pts[2], pts[3] = (0.40, 0.82), (0.36, 0.76), (0.32, 0.72)
    pts[4] = (0.24, 0.66) if fingers_up[0] else (0.46, 0.72)
    return [SimpleNamespace(x=x, y=y) for x, y in pts]


def test_finger_state_detection():
    for pattern in [(0, 0, 0, 0, 0), (1, 1, 1, 1, 1), (0, 1, 1, 0, 0), (1, 0, 0, 0, 1), (0, 1, 0, 0, 1)]:
        assert tuple(int(f) for f in get_finger_states(_hand(pattern), 640, 480)) == pattern
