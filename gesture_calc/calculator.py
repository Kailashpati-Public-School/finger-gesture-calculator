"""
calculator.py
-------------
The calculator "brain": collects digits into numbers, stores operators and
evaluates the expression when the EQUALS gesture is accepted.

Key rule (from the project brief):
    Digits keep joining the SAME number until an operator is entered.
    5 then 6           -> "56"      (no operator in between)
    5, 6, 7, +, 8, 7, 9, +, 3, 5, 5, =   ->   567 + 879 + 355 = 1801

No GUI / camera code here, so it is easy to unit-test.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from typing import List, Optional

MAX_DIGITS = 9  # longest number a child can type
OPERATORS = ("+", "-", "*", "/")
# Nice symbols for the screen (the internal value stays + - * /)
PRETTY_OPS = {"+": "+", "-": "\u2212", "*": "\u00d7", "/": "\u00f7"}
PLAIN_OPS = {"+": "+", "-": "-", "*": "x", "/": "/"}


@dataclass
class CalcEvent:
    """What just happened - used by the UI (e.g. to decide what to speak)."""

    kind: str                      # digit | operator | equals | clear | back | error | ignored
    number: str = ""               # number that was completed by an operator
    operator: str = ""             # operator that was entered
    tokens: List[str] = field(default_factory=list)  # full expression (for "equals")
    result: str = ""               # final answer (for "equals")
    message: str = ""              # hint / error text


def _format(value: Fraction) -> str:
    """Show whole numbers without decimals and cut long decimals at 6 places."""
    if value.denominator == 1:
        return str(value.numerator)
    text = f"{float(value):.6f}".rstrip("0").rstrip(".")
    return text or "0"


def evaluate(tokens: List[str]) -> str:
    """Evaluate ["567", "+", "879", "*", "2"] using normal maths (BODMAS) rules.

    Multiplication / division are done first, then addition / subtraction.
    Raises ZeroDivisionError for x / 0.  We never use eval() - it is unsafe.
    """
    # Pass 1: resolve * and /, keep + and - for pass 2
    values = [Fraction(tokens[0])]
    pending_ops: List[str] = []
    for i in range(1, len(tokens), 2):
        op, number = tokens[i], Fraction(tokens[i + 1])
        if op == "*":
            values[-1] = values[-1] * number
        elif op == "/":
            if number == 0:
                raise ZeroDivisionError
            values[-1] = values[-1] / number
        else:
            pending_ops.append(op)
            values.append(number)

    # Pass 2: left-to-right + and -
    total = values[0]
    for op, number in zip(pending_ops, values[1:]):
        total = total + number if op == "+" else total - number
    return _format(total)


class Calculator:
    def __init__(self) -> None:
        self.history: List[str] = []  # finished calculations, newest last
        self.clear()

    # ------------------------------------------------------------------ state
    def clear(self) -> CalcEvent:
        """Reset the current calculation (history is kept)."""
        self.tokens: List[str] = []      # ["567", "+", "879", "+"]  numbers and operators
        self.current: str = ""           # digits typed so far for the number in progress
        self.result: Optional[str] = None
        self.error: Optional[str] = None
        self.done: bool = False          # True after "=" until a new calculation starts
        self.message: str = ""
        return CalcEvent("clear")

    def _ignored(self, message: str) -> CalcEvent:
        self.message = message
        return CalcEvent("ignored", message=message)

    # ----------------------------------------------------------------- inputs
    def input_digit(self, digit: str) -> CalcEvent:
        if self.done:               # a digit after "=" starts a fresh calculation
            self.clear()
        if len(self.current) >= MAX_DIGITS:
            return self._ignored(f"Max {MAX_DIGITS} digits")
        if self.current == "0":     # avoid numbers like "007"
            if digit == "0":
                return self._ignored("Already 0")
            self.current = ""
        self.current += digit
        self.message = ""
        return CalcEvent("digit", number=digit)

    def input_operator(self, op: str) -> CalcEvent:
        if self.done and self.result is not None:
            # Continue with the previous answer:  1801 = then "+" -> "1801 +"
            self.tokens = [self.result]
            self.result, self.error, self.done, self.current = None, None, False, ""
            self.tokens.append(op)
            self.message = ""
            return CalcEvent("operator", operator=op)
        if self.done:               # previous calculation ended with an error
            self.clear()

        if self.current:            # normal case: "567" then "+"
            number = self.current
            self.tokens += [number, op]
            self.current = ""
            self.message = ""
            return CalcEvent("operator", number=number, operator=op)

        if self.tokens and self.tokens[-1] in OPERATORS:  # changed mind: "5 +" -> "5 -"
            self.tokens[-1] = op
            self.message = ""
            return CalcEvent("operator", operator=op)

        return self._ignored("Show a number first")

    def equals(self) -> CalcEvent:
        if self.done:
            return self._ignored("Already calculated - show a new number")
        if not self.current and (not self.tokens or self.tokens[-1] in OPERATORS):
            return self._ignored("Show a number before '='")

        tokens = self.tokens + ([self.current] if self.current else [])
        self.tokens, self.current, self.done = tokens, "", True
        try:
            self.result = evaluate(tokens)
        except ZeroDivisionError:
            self.result, self.error = None, "Cannot divide by zero"
            self.message = self.error
            return CalcEvent("error", tokens=tokens, message=self.error)

        self.message = ""
        self.history.append(f"{self.expression_text()} = {self.result}")
        self.history = self.history[-20:]  # keep memory small
        return CalcEvent("equals", tokens=tokens, result=self.result)

    def backspace(self) -> CalcEvent:
        if self.done:
            return self._ignored("Show 'C' to clear")
        if self.current:                       # remove last digit
            self.current = self.current[:-1]
        elif self.tokens:                      # remove operator and re-open the previous number
            self.tokens.pop()
            self.current = self.tokens.pop()
        else:
            return self._ignored("Nothing to delete")
        self.message = ""
        return CalcEvent("back")

    # ---------------------------------------------------------------- display
    def expression_text(self, pretty: bool = True) -> str:
        """The expression as shown on screen, e.g. '567 + 879 + 35'."""
        symbols = PRETTY_OPS if pretty else PLAIN_OPS
        parts = [symbols.get(t, t) for t in self.tokens]
        if self.current:
            parts.append(self.current)
        return " ".join(parts)
