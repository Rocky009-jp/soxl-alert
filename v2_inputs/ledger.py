"""The user's F&G observations: observations.csv on a ref of the git remote, read at the SHA that the fetch decided. The rows
go to the core as text (the core reads the numbers and the times and applies the observation rules); only the file, the
header, the columns and "not observed after now" are checked here. The runner never writes the ledger."""
import csv
import io

from v2_core.errors import CoreError, InputError
from v2_core.sessions import parse_aware_datetime

NAME = "observations.csv"
COLUMNS = ("record_id", "target_us_session_date", "observation_role", "observation_status", "current_fg_value",
           "observed_at_iso8601")


def _read_table(data):
    """(header, body rows) of the CSV text, or None when the bytes are not UTF-8, not CSV, or empty. No exception is raised
    in a handler."""
    header = body = None
    try:
        text = data.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text, newline=""))
        header = next(reader)
        body = [row for row in reader if any(cell.strip() for cell in row)]
    except (UnicodeDecodeError, csv.Error, StopIteration):
        return None
    return header, body


def _observed_after(row, now):
    """True when the observed_at of a row is a readable time later than now (an unreadable one is left to the core)."""
    text = row["observed_at_iso8601"]
    if not text:
        return False
    when = None
    try:
        when = parse_aware_datetime(text, "observed_at_iso8601")
    except CoreError:
        when = None
    return when is not None and when > now


def read_ledger(git, ref, now):
    """(rows, head SHA): a list of dicts of the six columns (each value stripped, still text) and the SHA that was read.
    InputError for a missing ledger or file, an unreadable file, a wrong header, a row of the wrong width, or a readable
    observed_at later than now (a time zone written wrongly makes one). The ledger is fetched once; nothing is written."""
    head = git.fetch(ref)
    data = None if head is None else git.blob(head, NAME)
    if data is None:
        raise InputError("input_ledger_missing", "ledger")
    table = _read_table(data)
    if table is None:
        raise InputError("input_ledger_unreadable", "ledger")
    header, body = table
    if tuple(cell.strip() for cell in header) != COLUMNS:
        raise InputError("input_ledger_header_invalid", "ledger")
    rows = []
    for cells in body:
        if len(cells) != len(COLUMNS):
            raise InputError("input_ledger_row_invalid", "ledger")
        row = dict(zip(COLUMNS, (cell.strip() for cell in cells)))
        if _observed_after(row, now):
            raise InputError("input_ledger_observation_after_now", "observed_at_iso8601")
        rows.append(row)
    return rows, head
