"""S4-D limited defect injection (request section 5, items 1-22, plus extras). One mutant at a time on a throwaway worktree of
the tested commit (the range tests read Git at HEAD, so each mutant is committed there). Nothing is pushed.
usage: python mutate.py <python> <repo> <tested-sha> <out.json> [i/n]
Classification: DETECTED (a test of the S4-D suite fails or errors; the range test 09 is not counted: it reads the changed
file list), UNDETECTED, PREP_FAILED (the pattern was not found exactly once, or the mutant does not parse; nothing was run).
EQUIVALENT is a judgement written in the result document, never decided here. The test files are run from the cheapest to the
dearest and the run of a mutant stops at the first file that has a failure."""
import json
import os
import re
import subprocess
import sys
import tempfile

PY, REPO, SHA, OUT = sys.argv[1:5]
SHARD = tuple(int(x) for x in sys.argv[5].split("/")) if len(sys.argv) > 5 else (0, 1)
XN, MK, LG, LD = "v2_inputs/xnys.py", "v2_inputs/market.py", "v2_inputs/ledger.py", "v2_inputs/load.py"
M = []
ORDER = ["test_s4d_01*.py", "test_s4d_02*.py", "test_s4d_12*.py", "test_s4d_03*.py", "test_s4d_08*.py", "test_s4d_04*.py",
         "test_s4d_05*.py", "test_s4d_10*.py", "test_s4d_06*.py", "test_s4d_11*.py", "test_s4d_07*.py"]


def add(n, title, *edits):
    M.append({"id": n, "title": title, "edits": list(edits)})


def sub(path, old, new):
    return (path, old, new)


add("1", "fetch even when the pin already reaches the target day",
    sub(LD, "        if through is not None and through >= target:\n", "        if False:\n"))
add("2", "pin again when the last complete day equals the pinned day",
    sub(LD, "if last is not None and (through is None or last > through):", "if last is not None and (through is None or last >= through):"))
add("3", "no new pin: the fetched series is used instead of the pinned one",
    sub(LD, '                provenance["pinned_by"] = "existing"           # nothing newer was fetched: the pinned bytes are used',
        '                provenance["pinned_by"] = "existing"\n                rows, through = fetched, (last if last is not None else through)'))
add("4", "the loser of a push uses its own series without reading the pin again",
    sub(LD, "                    head, through, rows, digest = pin.read()\n                    if through is None or through < last:",
        "                    head, through, rows = pin.head_after_pin, last, read_snapshot(data)[1]\n"
        "                    digest = hashlib.sha256(data).hexdigest()\n                    if through is None or through < last:"))
add("5", "load_inputs raises the input failure (it does not return it)",
    sub(LD, "    except CoreError as error:\n        failure = error\n", "    except CoreError as error:\n        raise\n"))
add("6", "the guard's read() reads the real store",
    sub(LD, "    def read(self):\n        raise self._failure", "    def read(self):\n        return self._store.read()"))
add("7", "every session is confirmed",
    sub(LD, "Inputs(series, build_sessions(now, through), raw, failure, provenance)", 'Inputs(series, build_sessions(now, "2999-12-31"), raw, failure, provenance)'))
add("8", "the daylight-saving rule starts a week early (first Sunday of March)",
    sub(XN, "summer = _nth_sunday(day.year, 3, 2) <= day", "summer = _nth_sunday(day.year, 3, 1) <= day"))
add("9", "no margin after the close (0 minutes instead of 60)",
    sub(MK, "CLOSE_MARGIN = dt.timedelta(minutes=60)", "CLOSE_MARGIN = dt.timedelta(minutes=0)"))
add("10", "a null day is a bad value",
    sub(MK, "        if day < PREHISTORY_START or close is None or adjusted is None:\n            continue\n",
        "        if day < PREHISTORY_START:\n            continue\n"))
add("10b", "a bad value is dropped silently",
    sub(MK, "        elif invalid is None or day < invalid:\n            invalid = day\n", "        else:\n            pass\n"))
add("11", "no limit on the price",
    sub(MK, "    return 0 < x < PRICE_MAX", "    return x > 0"))
add("12", "an observed_at after now is accepted",
    sub(LG, "    return when is not None and when > now", "    return False"))
add("13", "a ledger value is turned into a number before the core",
    sub(LG, "        row = dict(zip(COLUMNS, (cell.strip() for cell in cells)))\n",
        "        row = dict(zip(COLUMNS, (cell.strip() for cell in cells)))\n"
        "        row['current_fg_value'] = float(row['current_fg_value']) if row['current_fg_value'] else row['current_fg_value']\n"))
add("14", "a data day that the table does not have is not checked",
    sub(LD, "    if extra:\n        raise InputError(\"input_calendar_data_mismatch\"", "    if False:\n        raise InputError(\"input_calendar_data_mismatch\""))
add("15", "a hole is skipped (the day after it counts)",
    sub(LD, '            raise InputError("input_market_rows_missing", "market", detail=hole)', "            last = session.date"))
add("16", "market.json is written without sorted keys",
    sub(MK, "json.dumps(body, sort_keys=True, separators", "json.dumps(body, sort_keys=False, separators"))
add("17", "the 14-day check of the table is off",
    sub(XN, "timedelta(days=MARGIN_DAYS)).date() > CALENDAR_END", "timedelta(days=0)).date() > CALENDAR_END"))
add("18", "a GitError is not replaced by input_git_failed",
    sub(LD, "    except GitError:", "    except KeyError:"))
add("19", "the check of the start of the SOXX series is off",
    sub(LD, "    if PREHISTORY_START not in out[\"SOXX\"]:", "    if False:"))
add("20", "an InputError is raised in an except body (the cause is chained)",
    sub(LG, "    except (UnicodeDecodeError, csv.Error, StopIteration):\n        return None",
        "    except (UnicodeDecodeError, csv.Error, StopIteration):\n        raise InputError(\"input_ledger_unreadable\", \"ledger\")"))
add("21", "the match with the table is made against the closed sessions only",
    sub(LD, "    table = set(s.date for s in sessions)\n", "    table = set(s.date for s in closed)\n"))
add("22", "the rows after the target day are not dropped before the checks",
    sub(MK, "        if through is not None and day > through:\n            continue\n", "        if False:\n            continue\n"))
add("21+22", "21 and 22 together (review R-01)",
    sub(LD, "    table = set(s.date for s in sessions)\n", "    table = set(s.date for s in closed)\n"),
    sub(MK, "        if through is not None and day > through:\n            continue\n", "        if False:\n            continue\n"))
add("E1", "extra: the pre-history starts a day late",
    sub(MK, 'PREHISTORY_START = "2010-02-11"', 'PREHISTORY_START = "2010-02-12"'))
add("E2", "extra: the schema of market.json is not checked",
    sub(MK, 'if body["schema"] != SCHEMA or body["source"] != SOURCE or not _iso_date(body["through"]):', 'if not _iso_date(body["through"]):'))
add("E3", "extra: the rows of market.json may go past its day",
    sub(MK, 'if dates and (dates[0] < PREHISTORY_START or dates[-1] > body["through"]):', "if dates and dates[0] < PREHISTORY_START:"))
add("E4", "extra: the hole that is named is the last one",
    sub(LD, "            hole = session.date if hole is None else hole", "            hole = session.date"))
add("E5", "extra: the day named for a day the table does not have is the last one",
    sub(LD, "detail=extra[0])", "detail=extra[-1])"))
add("E6", "extra: the cells of the ledger are not stripped",
    sub(LG, "(cell.strip() for cell in cells)", "(cell for cell in cells)"))
add("E7", "extra: a BOM is not accepted",
    sub(LG, 'data.decode("utf-8-sig")', 'data.decode("utf-8")'))
add("E8", "extra: SOXL takes the adjusted close",
    sub(MK, "soxl = {d: v[0] for d, v in by_symbol[\"SOXL\"].items() if d <= through}", "soxl = {d: v[1] for d, v in by_symbol[\"SOXL\"].items() if d <= through}"))
add("E9", "extra: SOXX takes the close",
    sub(MK, "[soxx[d][1] for d in dates]", "[soxx[d][0] for d in dates]"))
add("E10", "extra: SPY takes the close",
    sub(MK, "spy = {d: v[1] for d, v in by_symbol[\"SPY\"].items() if d <= through}", "spy = {d: v[0] for d, v in by_symbol[\"SPY\"].items() if d <= through}"))
add("E11", "extra: IEF takes the close",
    sub(MK, "ief = {d: v[1] for d, v in by_symbol[\"IEF\"].items() if d <= through}", "ief = {d: v[0] for d, v in by_symbol[\"IEF\"].items() if d <= through}"))
add("E12", "extra: market_dates is the dates of SPY or IEF",
    sub(MK, "set(spy) & set(ief)", "set(spy) | set(ief)"))
add("E13", "extra: an early close is closed at 16:00",
    sub(XN, "close = _at(day, 13, 0) if day in EARLY_CLOSES else _at(day, 16, 0)", "close = _at(day, 16, 0)"))
add("E14", "extra: the date of the end of the fetch is the UTC date",
    sub(LD, "    utc = now.astimezone(dt.timezone.utc)\n    return (utc + ny_offset(utc.date())).date()", "    return now.astimezone(dt.timezone.utc).date()"))
add("E15", "extra: the same ref for the market and the ledger is accepted",
    sub(LD, ' and refs["market"] != refs["ledger"]', ""))
add("E16", "extra: a bool is a price",
    sub(MK, "    if isinstance(x, bool) or not isinstance(x, (int, float)):\n        return False", "    if not isinstance(x, (int, float)):\n        return False"))
add("E17", "extra: an observation at now is refused",
    sub(LG, "when > now", "when >= now"))
add("E18", "extra: a pin commit has no parent",
    sub(MK, "commit = self._git.commit_with(head, NAME,", "commit = self._git.commit_with(None, NAME,"))
add("E19", "extra: the table ends one day later in the check (>=)",
    sub(XN, "timedelta(days=MARGIN_DAYS)).date() > CALENDAR_END", "timedelta(days=MARGIN_DAYS)).date() >= CALENDAR_END"))
add("E20", "extra: a now past the table is not refused",
    sub(XN, "    if now.astimezone(dt.timezone.utc).date() > CALENDAR_END:\n        raise InputError(\"input_calendar_ended\", \"calendar\")\n", ""))
add("E21", "extra: the chart URL asks for no dividends and splits",
    sub(MK, "events=div%%2Csplit&", ""))
add("E22", "extra: the values are not turned into floats",
    sub(MK, "rows[day] = (float(close), float(adjusted))", "rows[day] = (close, adjusted)"))
add("E23", "extra: the response is not required to name its symbol",
    sub(MK, "if named != symbol or not (type(stamps) is list", "if not (type(stamps) is list"))
add("E24", "extra: the pin is read without the sha of the bytes (the manifest is the commit)",
    sub(MK, "return head, through, rows, hashlib.sha256(data).hexdigest()", "return head, through, rows, head"))
add("E25", "extra: a failed fetch of a symbol is skipped (an empty response)",
    sub(LD, "        if data is _FETCH_FAILED:\n            return None, InputError(\"input_market_fetch_failed\", \"market\")\n", "        if data is _FETCH_FAILED:\n            continue\n"))
add("E26", "extra: the ledger is read from the ref of the market",
    sub(LD, 'read_ledger(git, refs["ledger"], now)', 'read_ledger(git, refs["market"], now)'))
add("E27", "extra: the fetch count is always 4",
    sub(LD, 'provenance["fetch_count"] = calls[0]', 'provenance["fetch_count"] = 4'))


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
                          timeout=3000)


def git(wt, *a):
    return run(["git", "-c", "user.email=m@example.invalid", "-c", "user.name=mutant"] + list(a), wt)


results = []
base = tempfile.mkdtemp()
for idx, m in enumerate(M):
    if idx % SHARD[1] != SHARD[0]:
        continue
    wt = os.path.join(base, "wt_" + m["id"].replace("+", "_"))
    rec = {"id": m["id"], "title": m["title"]}
    git(REPO, "worktree", "add", "-q", "--detach", wt, SHA)
    ok = True
    for path, old, new in m["edits"]:
        full = os.path.join(wt, path)
        text = open(full).read()
        if text.count(old) != 1:
            ok = False
            rec["status"] = "PREP_FAILED"
            rec["detail"] = "pattern found %d times in %s: %r" % (text.count(old), path, old[:60])
            break
        text = text.replace(old, new)
        open(full, "w").write(text)
    if ok:
        compiled = run([PY, "-B", "-c", "import ast,sys; [ast.parse(open(p).read()) for p in sys.argv[1:]]"] +
                       [os.path.join(wt, p) for p in (XN, MK, LG, LD)], wt)
        if compiled.returncode != 0:
            ok = False
            rec["status"] = "PREP_FAILED"
            rec["detail"] = "the mutant does not parse"
    if ok:
        git(wt, "commit", "-qam", "mutant " + m["id"])
        ran, failed = 0, []
        for pat in ORDER:
            out = run([PY, "-B", "-W", "error::ResourceWarning", "-m", "unittest", "discover", "-s", "tests/v2_inputs",
                       "-p", pat], wt)
            text = out.stdout + out.stderr
            ran += sum(int(x) for x in re.findall(r"^Ran (\d+) tests", text, re.M))
            failed = re.findall(r"^(?:FAIL|ERROR): (\S+) \(([^)]*)\)", text, re.M)
            if failed:
                break
        rec["status"] = "DETECTED" if failed else "UNDETECTED"
        rec["ran"] = ran
        rec["failing_count"] = len(failed)
        rec["failing_examples"] = ["%s (%s)" % (n, c) for n, c in failed[:4]]
    git(REPO, "worktree", "remove", "--force", wt)
    print(m["id"], rec["status"], rec.get("failing_count"), rec["title"], flush=True)
    results.append(rec)
json.dump(results, open(OUT, "w"), indent=1, ensure_ascii=False)
