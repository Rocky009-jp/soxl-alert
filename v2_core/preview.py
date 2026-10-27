"""Local preview: reads explicit files, prints text to stdout. Writes nothing, sends nothing.

  python -m v2_core.preview --fixture-dir DIR --date YYYY-MM-DD --sessions sessions.json \
      [--observations obs.json] [--state state.json] [--json]
"""
import argparse
import json
import sys

from .display import render
from .engine import ErrorResult, RunClass, run_day_safe
from .errors import InputError
from .fixture import load_research_fixture
from .sessions import SessionList
from .state import MarketState


def _read_json(path, name):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        raise InputError("file_unreadable", name)


def main(argv=None):
    p = argparse.ArgumentParser(description="V2 offline core preview (no send, no save)")
    p.add_argument("--fixture-dir", required=True)
    p.add_argument("--date", required=True)
    p.add_argument("--sessions", required=True)
    p.add_argument("--observations")
    p.add_argument("--state")
    p.add_argument("--json", action="store_true", help="print the next-state candidate as JSON after the text")
    args = p.parse_args(argv)
    state = MarketState.initial()
    try:
        series, _fg = load_research_fixture(args.fixture_dir)
        sessions = SessionList.from_dicts(_read_json(args.sessions, "sessions"))
        observations = _read_json(args.observations, "observations") if args.observations else []
        if args.state:
            state = MarketState.from_dict(_read_json(args.state, "state"))
        result = run_day_safe(state, args.date, series, sessions, observations)
    except InputError as e:
        result = ErrorResult(args.date, e.code, e.field, RunClass.DATA_ERROR, state)
    print(render(result))
    if args.json:
        print(json.dumps(result.next_state.to_dict(), ensure_ascii=False, indent=2))
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main())
