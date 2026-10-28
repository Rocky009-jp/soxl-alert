"""Market state carried between sessions. Contains no account, holding or order data."""
import re
from dataclasses import dataclass
from typing import Optional

from .errors import InputError
from .fixture import parse_iso_date
from .observations import is_valid_record_id
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
        """Read a persisted state, checking the current state and its base by separate rules.

        The top level is the current state: I-01..I-07. The nested `base` is the state before the last applied D,
        stored without its own fixed_decision and base: IB-01..IB-03. The top-level rules are never applied to
        the base (it legitimately has an as_of_d but no fixed_decision). Any violation raises StateInvalid
        (code state_invalid, exit code 1); no value is echoed.

        These checks belong to reading persisted data only. A MarketState built directly (constructor, tests,
        internal callers) is a trusted internal input: neither the constructor nor evaluate_day checks it, and
        a directly built value is not guaranteed to be a persistable state (for example as_of_d with no
        fixed_decision, which evaluate_day accepts and returns unchanged on days without a decision).
        """
        try:
            top = cls._read_fields(data)
            base = None
            if top["base"] is not None:
                raw = cls._read_fields(top["base"])
                _check_base(raw)
                base = cls(raw["as_of_d"], raw["armed"], raw["streak"], raw["prev_normal_raw"])
            _check_current(top, base)
            return cls(top["as_of_d"], top["armed"], top["streak"], top["prev_normal_raw"],
                       fixed_decision=top["fixed_decision"], base=base)
        except StateInvalid:
            raise
        except (KeyError, ValueError, TypeError, InputError):
            raise StateInvalid("shape")

    @staticmethod
    def _read_fields(data):
        """Types and formats of one level; no cross-field rules. `base` is returned unparsed."""
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
        if base is not None and not isinstance(base, dict):
            raise ValueError
        return {"as_of_d": as_of, "armed": Tri(data["armed"]), "streak": streak,
                "prev_normal_raw": Tri(data["prev_normal_raw"]), "fixed_decision": fixed, "base": base}


class StateInvalid(InputError):
    """state_invalid raised by a persisted-state check. `rule` is an internal id (I-03, IB-02, shape), never a value."""

    def __init__(self, rule):
        super().__init__("state_invalid", "state")
        self.rule = rule


_FINGERPRINT = re.compile(r"[0-9a-f]{64}")


def _check_arithmetic(f, current):
    """Rules shared by both levels: I-05/I-06 and IB-03."""
    if f["streak"] >= 3 and f["armed"] is not Tri.TRUE:
        raise StateInvalid("I-05" if current else "IB-03")
    if f["streak"] >= 1 and f["prev_normal_raw"] is not Tri.FALSE:
        raise StateInvalid("I-06" if current else "IB-03")


def _is_initial(f):
    return f["armed"] is Tri.UNKNOWN and f["streak"] == 0 and f["prev_normal_raw"] is Tri.UNKNOWN


def _check_current(f, base):
    """I-01..I-07 on the top-level state only. `base` is the already-read base MarketState or None."""
    as_of, fixed = f["as_of_d"], f["fixed_decision"]
    if not ((as_of is None) == (fixed is None) == (base is None)):
        raise StateInvalid("I-01")
    if as_of is None and not _is_initial(f):
        raise StateInvalid("I-02")
    if fixed is not None and fixed["d"] != as_of:
        raise StateInvalid("I-03")
    if base is not None and base.as_of_d is not None and not base.as_of_d < as_of:
        raise StateInvalid("I-04")
    _check_arithmetic(f, True)
    if fixed is not None and not (_FINGERPRINT.fullmatch(fixed["fingerprint"])
                                  and is_valid_record_id(fixed["record_id"])):
        raise StateInvalid("I-07")


def _check_base(f):
    """IB-01..IB-03 on the nested base only."""
    if f["fixed_decision"] is not None or f["base"] is not None:
        raise StateInvalid("IB-01")
    if f["as_of_d"] is None and not _is_initial(f):
        raise StateInvalid("IB-02")
    _check_arithmetic(f, False)
