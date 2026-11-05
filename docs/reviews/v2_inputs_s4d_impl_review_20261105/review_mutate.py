"""S4-D implementation review: independent mutants V01-V24 (the runner of the implementer's mutate.py, list replaced). One mutant at a time on a throwaway worktree of
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


add("V01", "the New York date of a time is its UTC date",
    sub(MK, "    return (utc + ny_offset(utc.date())).date().isoformat()", "    return utc.date().isoformat()"))
add("V02", "read_snapshot: the dates need not increase",
    sub(MK, " or any(a >= b for a, b in zip(dates, dates[1:]))", ""))
add("V03", "read_snapshot: SOXX need not start on the pre-history start",
    sub(MK, '        if PREHISTORY_START not in out["SOXX"]:\n            return None\n', ""))
add("V04", "read_snapshot: rows before the pre-history start are accepted",
    sub(MK, "if dates and (dates[0] < PREHISTORY_START or dates[-1] > body", "if dates and (dates[-1] > body"))
add("V05", "parse_chart: a day with only one null value is a bad value",
    sub(MK, "close is None or adjusted is None:", "close is None and adjusted is None:"))
add("V06", "a fetch that raises something other than OSError escapes",
    sub(LD, "        except Exception:\n            data = _FETCH_FAILED", "        except OSError:\n            data = _FETCH_FAILED"))
add("V07", "on a failure the series is not dropped",
    sub(LD, "        series, raw = None, []\n", "        raw = []\n"))
add("V08", "on a failure every session is unconfirmed",
    sub(LD, "Inputs(series, build_sessions(now, through), raw", "Inputs(series, build_sessions(now, through if failure is None else None), raw"))
add("V09", "a ref name may have capital letters",
    sub(LD, '_REF = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")', '_REF = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,39}")'))
add("V10", "refs may have more keys than market and ledger",
    sub(LD, 'set(refs) != {"market", "ledger"}', 'not {"market", "ledger"} <= set(refs)'))
add("V11", "the end of the table is judged on the New York date (UTC-5)",
    sub(XN, "    if now.astimezone(dt.timezone.utc).date() > CALENDAR_END:", "    if (now.astimezone(dt.timezone.utc) - dt.timedelta(hours=5)).date() > CALENDAR_END:"))
add("V12", "the 14 days are counted from the New York date (UTC-5)",
    sub(XN, "if (now.astimezone(dt.timezone.utc) + dt.timedelta(days=MARGIN_DAYS)).date() > CALENDAR_END:",
        "if (now.astimezone(dt.timezone.utc) - dt.timedelta(hours=5) + dt.timedelta(days=MARGIN_DAYS)).date() > CALENDAR_END:"))
add("V13", "ledger: the header is compared without stripping",
    sub(LG, "if tuple(cell.strip() for cell in header) != COLUMNS:", "if tuple(header) != COLUMNS:"))
add("V14", "ledger: a row of spaces is not a blank row",
    sub(LG, "body = [row for row in reader if any(cell.strip() for cell in row)]", "body = [row for row in reader if row]"))
add("V15", "ledger: an unreadable observed_at counts as after now",
    sub(LG, "    except CoreError:\n        when = None\n    return when is not None and when > now",
        "    except CoreError:\n        return True\n    return when is not None and when > now"))
add("V16", "a push of unknown result is taken as arrived",
    sub(MK, "return self._git.push(commit, self._ref) == OK", 'return self._git.push(commit, self._ref) in (OK, "UNCERTAIN")'))
add("V17", "a loser accepts a pin older than its own last day",
    sub(LD, "                    if through is None or through < last:", "                    if through is None:"))
add("V18", "the close margin is reached one tick early (>=)",
    sub(LD, "        if session.close_at + CLOSE_MARGIN > now:", "        if session.close_at + CLOSE_MARGIN >= now:"))
add("V19", "read_snapshot: the source of market.json is not checked",
    sub(MK, ' or body["source"] != SOURCE', ""))
add("V20", "summer time ends on the fourth Sunday of October",
    sub(XN, "<= day < _nth_sunday(day.year, 11, 1)", "<= day < _nth_sunday(day.year, 10, 4)"))
add("V21", "the days the table does not have are checked for SOXX only",
    sub(LD, "for s in SYMBOLS[:3] for d in by_symbol[s]", "for s in SYMBOLS[:1] for d in by_symbol[s]"))
add("V22", "the target day is the last session that opened (not closed)",
    sub(LD, "    closed = [s for s in skeleton.sessions if s.close_at <= now]", "    closed = [s for s in skeleton.sessions if s.open_at <= now]"))
add("V23", "the pin is pushed before the 14-day check and the check is skipped when the pin is existing",
    sub(LD, "        short = coverage_failure(now)\n", "        short = coverage_failure(now) if provenance.get(\"pinned_by\") != \"existing\" else None\n"))
add("V24", "the ledger keeps its last row only once per record id (later wins)",
    sub(LG, "        rows.append(row)\n    return rows, head", "        rows = [r for r in rows if r[\"record_id\"] != row[\"record_id\"]] + [row]\n    return rows, head"))


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
