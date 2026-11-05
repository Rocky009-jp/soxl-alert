"""load_inputs: the sessions, the pinned market series and the ledger. An input failure is returned (not raised) and turned
into the STOPPED report of the morning run by guarded_store (its read() raises it inside run_morning), so that the morning
still sends the one "no verdict" notice of the right target day. Only a `now` past the table is raised (no D can be named)."""
import datetime as dt
import hashlib
import re

from v2_core.errors import CoreError, InputError
from v2_git_store import GitError

from .ledger import read_ledger
from .market import (CLOSE_MARGIN, PREHISTORY_START, SYMBOLS, MarketPin, parse_chart, read_snapshot, series_of,
                     snapshot_bytes)
from .xnys import build_sessions, calendar_sha256, coverage_failure, ny_offset

_REF = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")      # the shape of a ref name of v2_git_store
_FETCH_FAILED = object()


class Inputs(object):
    """series (None on a failure), sessions (always), raw_observations ([] on a failure), failure (None or an InputError),
    provenance (a dict of text and int: calendar_sha256, market_through, market_sha256, market_commit, pinned_by,
    fetch_count, ledger_commit; on a failure only the keys decided so far)."""

    def __init__(self, series, sessions, raw, failure, provenance):
        self.series, self.sessions, self.raw_observations = series, sessions, raw
        self.failure, self.provenance = failure, provenance


class _Guard(object):
    """A store whose read() raises the input failure; publish and reconcile go to the real store as they are."""

    def __init__(self, store, failure):
        self._store, self._failure = store, failure

    def read(self):
        raise self._failure

    def publish(self, publication):
        return self._store.publish(publication)

    def reconcile(self, publication):
        return self._store.reconcile(publication)


def guarded_store(store, failure):
    """The store itself when there is no failure; else a store that raises the failure when it is read."""
    return store if failure is None else _Guard(store, failure)


def _ref_ok(ref):
    return type(ref) is str and _REF.fullmatch(ref) is not None


def _args_ok(now, refs, fetch, clock):
    if not isinstance(now, dt.datetime) or now.utcoffset() is None or not callable(fetch) or not callable(clock):
        return False
    if type(refs) is not dict or set(refs) != {"market", "ledger"}:
        return False
    return _ref_ok(refs["market"]) and _ref_ok(refs["ledger"]) and refs["market"] != refs["ledger"]


def _ny_date(now):
    utc = now.astimezone(dt.timezone.utc)
    return (utc + ny_offset(utc.date())).date()


def _fetch_all(fetch, end, target, counter):
    """({symbol: rows}, None), or (None, InputError). A fetch that raises is input_market_fetch_failed. counter[0] counts
    the calls."""
    out = {}
    for symbol in SYMBOLS:
        counter[0] += 1
        try:
            data = fetch(symbol, PREHISTORY_START, end)
        except Exception:
            data = _FETCH_FAILED
        if data is _FETCH_FAILED:
            return None, InputError("input_market_fetch_failed", "market")
        out[symbol] = parse_chart(data, symbol, through=target)
    if PREHISTORY_START not in out["SOXX"]:
        return None, InputError("input_market_history_short", "market", detail=PREHISTORY_START)
    return out, None


def _last_complete(sessions, closed, by_symbol, now):
    """The date of the last closed session (in order) that is at least CLOSE_MARGIN after its close and has a row of every
    symbol. InputError for a data day that the table does not have (against every session of the table, closed or not), and
    for a hole (a day without all symbols) followed by a complete day."""
    table = set(s.date for s in sessions)
    extra = sorted(d for s in SYMBOLS[:3] for d in by_symbol[s] if d >= sessions[0].date and d not in table)
    if extra:
        raise InputError("input_calendar_data_mismatch", "market", detail=extra[0])
    last = hole = None
    for session in closed:
        if session.close_at + CLOSE_MARGIN > now:
            break
        if not all(session.date in by_symbol[s] for s in SYMBOLS):
            hole = session.date if hole is None else hole
        elif hole is not None:
            raise InputError("input_market_rows_missing", "market", detail=hole)
        else:
            last = session.date
    return last


def load_inputs(git, fetch, now, refs, clock):
    """git: the Git of the store. fetch(symbol, start, end) -> the bytes of the chart JSON (S4-E gives the HTTP one). now: an
    aware datetime, read once by the entry. refs: {"market": ref, "ledger": ref}. clock: the time of a pin commit.
    Raises InputError(input_args_invalid) for a wrong argument (nothing is called) and InputError(input_calendar_ended)
    when now is past the table; every other failure is returned in Inputs.failure."""
    if not _args_ok(now, refs, fetch, clock):
        raise InputError("input_args_invalid", "inputs")
    skeleton = build_sessions(now, None)                       # raises only when now is past the table
    provenance = {"calendar_sha256": calendar_sha256(), "fetch_count": 0}
    calls = [0]
    closed = [s for s in skeleton.sessions if s.close_at <= now]
    end = (_ny_date(now) + dt.timedelta(days=1)).isoformat()
    pin = MarketPin(git, refs["market"], clock)
    failure, through, series, raw = None, None, None, []
    try:
        head, through, rows, digest = pin.read()
        if not closed:
            raise InputError("input_market_unavailable", "market")
        target = closed[-1].date
        if through is not None and through >= target:
            provenance["pinned_by"] = "existing"
        else:
            fetched, error = _fetch_all(fetch, end, target, calls)
            if error is not None:
                raise error
            last = _last_complete(skeleton.sessions, closed, fetched, now)
            if last is not None and (through is None or last > through):
                data = snapshot_bytes(last, fetched)
                if pin.pin(head, data, last):
                    head, through, rows = pin.head_after_pin, last, read_snapshot(data)[1]
                    digest = hashlib.sha256(data).hexdigest()
                    provenance["pinned_by"] = "this"
                else:                                          # lost or unknown: the pin on the remote decides
                    head, through, rows, digest = pin.read()
                    if through is None or through < last:
                        raise InputError("input_market_pin_failed", "market")
                    provenance["pinned_by"] = "other"
            else:
                provenance["pinned_by"] = "existing"           # nothing newer was fetched: the pinned bytes are used
        if through is None:
            raise InputError("input_market_unavailable", "market")
        series = series_of(through, rows, digest)
        provenance.update(market_through=through, market_sha256=digest, market_commit=head)
        short = coverage_failure(now)
        if short is not None:
            raise short
        raw, provenance["ledger_commit"] = read_ledger(git, refs["ledger"], now)
    except GitError:                                           # a CoreError too, so it comes first and is replaced
        failure = InputError("input_git_failed", "inputs")
    except CoreError as error:
        failure = error
    provenance["fetch_count"] = calls[0]                       # S4-E (S4-D review P-01): also after a parse error
    if failure is not None:
        series, raw = None, []
    return Inputs(series, build_sessions(now, through), raw, failure, provenance)
