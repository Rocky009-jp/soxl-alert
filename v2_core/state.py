"""Market state carried between sessions. Contains no account, holding or order data."""
from dataclasses import dataclass
from typing import Optional

from .errors import InputError
from .fixture import parse_iso_date
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
    def from_dict(cls, data, _nested=False):
        try:
            if not isinstance(data, dict):
                raise ValueError
            streak = data["streak"]
            if isinstance(streak, bool) or not isinstance(streak, int) or streak < 0:
                raise ValueError
            as_of = data["as_of_d"]
            if as_of is not None:
                parse_iso_date(as_of, "state")
            fixed = data.get("fixed_decision")
            if fixed is not None:
                if (not isinstance(fixed, dict) or not isinstance(fixed.get("record_id"), str)
                        or not isinstance(fixed.get("fingerprint"), str)):
                    raise ValueError
                parse_iso_date(fixed.get("d"), "state")
            base = data.get("base")
            if base is not None and _nested:
                raise ValueError
            return cls(
                as_of_d=as_of,
                armed=Tri(data["armed"]),
                streak=streak,
                prev_normal_raw=Tri(data["prev_normal_raw"]),
                fixed_decision=fixed,
                base=cls.from_dict(base, True) if base else None,
            )
        except (KeyError, ValueError, TypeError, InputError):
            raise InputError("state_invalid", "state")
