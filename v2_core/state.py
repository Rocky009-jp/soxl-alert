"""Market state carried between sessions. Contains no account, holding or order data."""
from dataclasses import dataclass
from typing import Optional

from .errors import InputError
from .tri import Tri


@dataclass(frozen=True)
class MarketState:
    as_of_d: Optional[str] = None
    armed: Tri = Tri.UNKNOWN
    streak: int = 0                      # confirmed consecutive observed F&G >= 30 sessions
    prev_normal_raw: Tri = Tri.UNKNOWN
    fixed_decision: Optional[dict] = None  # {"d", "record_id", "fingerprint"} of the last applied D
    base: Optional["MarketState"] = None   # state before the last applied D (for same-D re-run)

    @classmethod
    def initial(cls):
        return cls()

    def to_dict(self):
        return {
            "as_of_d": self.as_of_d,
            "armed": self.armed.value,
            "streak": self.streak,
            "prev_normal_raw": self.prev_normal_raw.value,
            "fixed_decision": self.fixed_decision,
            "base": self.base.to_dict() if self.base else None,
        }

    @classmethod
    def from_dict(cls, data):
        try:
            streak = data["streak"]
            if isinstance(streak, bool) or not isinstance(streak, int) or streak < 0:
                raise ValueError
            base = data.get("base")
            return cls(
                as_of_d=data["as_of_d"],
                armed=Tri(data["armed"]),
                streak=streak,
                prev_normal_raw=Tri(data["prev_normal_raw"]),
                fixed_decision=data.get("fixed_decision"),
                base=cls.from_dict(base) if base else None,
            )
        except (KeyError, ValueError, TypeError):
            raise InputError("state_invalid", "state")
