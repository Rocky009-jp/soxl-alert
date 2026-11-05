"""V2 S4-D, the inputs of the morning run: the XNYS sessions (a fixed table and the US daylight-saving rule, no calendar
library, no tz database), the market series (the daily chart response of a fetch function that the caller passes in,
interpreted and pinned per target day on a ref of the git remote), and the user's F&G ledger (observations.csv on a ref).
An input failure is not raised: it is returned in Inputs.failure and turned into the STOPPED report of the morning run by
guarded_store. No HTTP, no network, no GitHub, no credential, no clock (the time is passed in), no entry script. Draft, not
adopted for production."""
from .ledger import read_ledger
from .load import Inputs, guarded_store, load_inputs
from .market import (CLOSE_MARGIN, PREHISTORY_START, PRICE_MAX, SYMBOLS, MarketPin, chart_url, parse_chart)
from .xnys import (CALENDAR_END, CALENDAR_START, MARGIN_DAYS, build_sessions, calendar_sha256, coverage_failure)

__all__ = ["CALENDAR_END", "CALENDAR_START", "CLOSE_MARGIN", "Inputs", "MARGIN_DAYS", "MarketPin", "PREHISTORY_START",
           "PRICE_MAX", "SYMBOLS", "build_sessions", "calendar_sha256", "chart_url", "coverage_failure", "guarded_store",
           "load_inputs", "parse_chart", "read_ledger"]
