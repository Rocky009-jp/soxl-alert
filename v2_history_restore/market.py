"""The market inputs of the days that are applied again or consumed (design 9; C-1 design 3.5): the current rows are read
once, from a copy of the series made at each day, and fixed as the series inputs that the plan binds to.

The rows are read and fixed here (a re-applied day also compares them with the saved ones, in build.py); no indicator is
calculated. The injected series is
only asked for through(D), row(date) and previous_date(D)."""
from v2_core.errors import CoreError, InputError
from v2_persistence.codec import canonical_json, sha256_text
from v2_persistence.errors import PersistenceError
from v2_persistence.events import row_dict

from .errors import restore_invalid
from .values import CONSUME, REAPPLY


def _bad():
    return restore_invalid("series", "market_input")


def fixed_days(events, plan_ops, sl):
    """The days whose market values the plan fixes, in the order of the operations: (from_seq, d, previous session date)
    of each REAPPLY (the previous session date the superseded APPLY saved) and of each CONSUME (no superseded record,
    so from_seq is None; the previous session date is the injected sessions' previous(D), None when D has none, which
    series_inputs then refuses)."""
    out = []
    for entry in plan_ops:
        if entry["op"] == REAPPLY:
            old = events[entry["from_seq"]]
            out.append((old["seq"], old["d"], old["confirmed_inputs"]["prev_session_date"]))
        elif entry["op"] == CONSUME:
            before = sl.previous(entry["d"])
            out.append((None, entry["d"], None if before is None else before.date))
    return out


def series_inputs(series, sl, days):
    """For each day that is applied again or consumed (in order): the cut of the series at D and the fixed input item.
    days is fixed_days(...). Returns (items, cuts {d: cut}). A series that does not answer in the expected form is
    restore_invalid / series / market_input; the core's own input errors are kept as they are."""
    items, cuts = [], {}
    for from_seq, d, saved_previous in days:
        session = sl.get(d)
        if session is None:
            raise InputError("target_not_in_sessions", "sessions")
        if not session.confirmed:
            raise InputError("target_unconfirmed", "sessions")
        if sl.next(d) is None:
            raise InputError("next_session_missing", "sessions")
        prev_session = sl.previous(d)
        if prev_session is None:
            raise InputError("previous_session_missing", "sessions")
        try:
            cut = series.through(d)
            row = cut.row(d)
            try:
                prev_row = cut.row(saved_previous)
            except InputError:
                prev_row = None                       # as the core does: the previous indicators are unavailable
            series_previous = cut.previous_date(d)
            item = {"from_seq": from_seq, "d": d, "prev_session_date": saved_previous,
                    "series_previous_date": series_previous, "row": row_dict(row),
                    "prev_row": None if prev_row is None else row_dict(prev_row, "prev_row")}
            canonical_json(item)                        # a value that cannot be written as JSON is refused here
        except PersistenceError:
            raise _bad() from None                      # row_dict: not a number, or beyond the float range
        except CoreError:
            raise
        except (AttributeError, TypeError, KeyError, ValueError, IndexError, OverflowError, RecursionError):
            raise _bad() from None
        if not (series_previous == prev_session.date == saved_previous):
            raise InputError("session_series_mismatch", "market")
        items.append(item)
        cuts[d] = cut
    return items, cuts


def digest_of(items):
    return sha256_text(canonical_json(items))
