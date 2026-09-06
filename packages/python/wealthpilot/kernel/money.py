"""Deterministic money primitives used by the MVP wealth context."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

CNY = "CNY"
_CENT = Decimal("0.01")


def format_decimal(value: Decimal) -> str:
    """Return a non-exponential, two-decimal representation."""

    return format(value.quantize(_CENT), ".2f")


@dataclass(frozen=True, slots=True)
class Money:
    """A currency-safe immutable amount."""

    amount: Decimal
    currency: str = CNY

    def __post_init__(self) -> None:
        if self.currency != CNY:
            raise ValueError("MVP wealth calculations only support CNY")
        if not self.amount.is_finite():
            raise ValueError("money amount must be finite")

    def __add__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError("cannot add different currencies")
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError("cannot subtract different currencies")
        return Money(self.amount - other.amount, self.currency)

    def to_dict(self) -> dict[str, str]:
        return {"amount": format_decimal(self.amount), "currency": self.currency}
