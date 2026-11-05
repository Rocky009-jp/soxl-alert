"""S4D-14: the ledger observations.csv of the ref v2-ledger: BOM, CRLF, blank lines and spaces are accepted and the values go to
the core as stripped text; each wrong file has its code; an observation later than now is refused and one at now is not; an
unreadable time is left to the core; the SHA that was read is recorded; the runner writes nothing."""
import unittest
from datetime import datetime, timedelta, timezone

import s4d_helpers as H

I = H.I
D = "2026-07-28"
START = "2026-07-27"
NOW = datetime(2026, 7, 29, 7, 40, tzinfo=H.JST)


def put(rig, data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    rig.remote.plant("v2-ledger", {"observations.csv": data}, parent="HEAD~")


def read(rig, now=NOW, git=None):
    return I.read_ledger(git or rig.clone.git, "v2-ledger", now)


def refuse(case, rig, code, field="ledger", now=NOW):
    with case.assertRaises(H.InputError) as cm:
        read(rig, now)
    err = cm.exception
    case.assertEqual((err.code, err.field, err.detail), (code, field, None))
    case.assertIsNone(err.__context__)
    case.assertIsNone(err.__cause__)


class Accepted(H.Case):
    def test_bom_crlf_blank_lines_and_spaces(self):
        rig = H.Rig(self, start=START)
        text = ("﻿" + H.HEADER + "\r\n  \r\n" + "fg-2026-07-27 , 2026-07-27 ,decision, observed , 023 ,"
                " 2026-07-28T07:05+09:00 \r\n" + "\r\n" + ",,,,,\r\n" + "fg-2026-07-28,2026-07-28,decision,not_checked,,\r\n"
                ).replace(H.HEADER + "\r\n", H.HEADER.rstrip("\n") + "\r\n")
        put(rig, text)
        rows, head = read(rig)
        self.assertEqual(rows, [
            {"record_id": "fg-2026-07-27", "target_us_session_date": "2026-07-27", "observation_role": "decision",
             "observation_status": "observed", "current_fg_value": "023",
             "observed_at_iso8601": "2026-07-28T07:05+09:00"},
            {"record_id": "fg-2026-07-28", "target_us_session_date": "2026-07-28", "observation_role": "decision",
             "observation_status": "not_checked", "current_fg_value": "", "observed_at_iso8601": ""}])
        for row in rows:
            for value in row.values():
                self.assertIs(type(value), str)                       # no number, no time: the core reads them
        self.assertEqual(head, rig.remote.sha("v2-ledger"))

    def test_a_header_with_spaces_and_only_a_header(self):
        rig = H.Rig(self, start=START)
        put(rig, " " + H.HEADER.replace(",", " , "))
        self.assertEqual(read(rig)[0], [])
        put(rig, "﻿" + H.HEADER)
        self.assertEqual(read(rig)[0], [])

    def test_a_quoted_cell_and_the_order_of_the_rows_is_kept(self):
        rig = H.Rig(self, start=START)
        put(rig, H.HEADER + '"fg, one",2026-07-27,decision,observed,50,2026-07-28T07:05+09:00\n'
                            'b,2026-07-27,supplemental,observed,51,2026-07-28T07:06+09:00\n'
                            'a,2026-07-27,supplemental,observed,52,2026-07-28T07:07+09:00\n')
        rows, _head = read(rig)
        self.assertEqual([r["record_id"] for r in rows], ["fg, one", "b", "a"])

    def test_the_rows_reach_the_core_as_text_and_the_morning_uses_them(self):
        rig = H.Rig(self, start=START)
        text = H.HEADER.rstrip("\n") + "\r\n" + "\r\n" + " fg-2026-07-27 ,2026-07-27,decision,observed, 31 ,2026-07-28T07:05+09:00\r\n"
        put(rig, "﻿" + text)
        rig.ledger = "﻿" + text
        inp, _now = rig.inputs(D, H.Provider(D))
        self.assertIsNone(inp.failure)
        self.assertEqual(inp.raw_observations, [{"record_id": "fg-2026-07-27", "target_us_session_date": "2026-07-27",
                                                 "observation_role": "decision", "observation_status": "observed",
                                                 "current_fg_value": "31", "observed_at_iso8601": "2026-07-28T07:05+09:00"}])


class Refused(H.Case):
    def setUp(self):
        super().setUp()
        self.rig = H.Rig(self, start=START)

    def test_no_ref_and_no_file(self):
        refuse(self, self.rig, "input_ledger_missing")
        self.rig.remote.plant("v2-ledger", {"other.csv": b"x"}, parent=None)
        refuse(self, self.rig, "input_ledger_missing")

    def test_not_utf8_not_csv_or_empty(self):
        for data in (b"\xff\xfe\x00bad", b"\x80", b"", b"\xef\xbb\xbf", H.HEADER.encode("utf-8")[:-1] + b"\xc3"):
            put(self.rig, data)
            refuse(self, self.rig, "input_ledger_unreadable")

    def test_a_header_that_is_not_the_six_columns_in_order(self):
        cols = list(H.COLUMNS)
        swapped = cols[:]
        swapped[0], swapped[1] = swapped[1], swapped[0]
        bad = [",".join(cols[:-1]), ",".join(cols + ["extra"]), ",".join(swapped), ",".join(c.upper() for c in cols),
               ",".join(cols[1:]), "id" + "," + ",".join(cols[1:]), "\n", "   ", "a,b,c", "record_id"]
        for header in bad:
            put(self.rig, header + "\n" + H.decision_line("2026-07-27"))
            refuse(self, self.rig, "input_ledger_header_invalid")

    def test_a_row_with_another_number_of_columns(self):
        for line in ("a,b,c,d,e\n", "a,b,c,d,e,f,g\n", "only\n", "a,b,c,d,e,f,\n"):
            put(self.rig, H.HEADER + H.decision_line("2026-07-27") + line)
            refuse(self, self.rig, "input_ledger_row_invalid")

    def test_the_first_wrong_row_decides_the_code_a_wrong_row_before_a_late_time_wins(self):
        put(self.rig, H.HEADER + "a,b,c,d,e\n" + "x,2026-07-27,decision,observed,50,2030-01-01T00:00+00:00\n")
        refuse(self, self.rig, "input_ledger_row_invalid")


class ObservedAfterNow(H.Case):
    def line(self, when):
        return "x,2026-07-28,decision,observed,50,%s\n" % when

    def test_a_second_after_now_is_refused_and_now_itself_is_accepted(self):
        rig = H.Rig(self, start=START)
        for text, offset_hours in (("2026-07-29T07:40:00+09:00", 9), ("2026-07-28T22:40:00Z", 0),
                                   ("2026-07-28T17:40:00-05:00", -5), ("2026-07-29T07:40+09:00", 9)):
            now = datetime(2026, 7, 28, 22, 40, tzinfo=timezone.utc)
            put(rig, H.HEADER + self.line(text))
            self.assertEqual(len(read(rig, now)[0]), 1, text)
            refuse(self, rig, "input_ledger_observation_after_now", "observed_at_iso8601", now - timedelta(seconds=1))
            self.assertEqual(len(read(rig, now + timedelta(seconds=1))[0]), 1, text)
        # fractions of a second count
        put(rig, H.HEADER + self.line("2026-07-28T22:40:00.5Z"))
        refuse(self, rig, "input_ledger_observation_after_now", "observed_at_iso8601",
               datetime(2026, 7, 28, 22, 40, tzinfo=timezone.utc))

    def test_a_time_zone_written_wrongly_makes_a_future_time(self):
        rig = H.Rig(self, start=START)
        # 07:05 Japan time written as +00:00 is 9 hours later than it was
        put(rig, H.HEADER + self.line("2026-07-29T07:05+00:00"))
        refuse(self, rig, "input_ledger_observation_after_now", "observed_at_iso8601", NOW)

    def test_a_row_without_a_time_or_with_an_unreadable_one_is_not_judged_here(self):
        rig = H.Rig(self, start=START)
        for when in ("", "yesterday", "2026-07-28T07:05", "2026-07-28 07:05+09:00", "2999-13-45T99:99+09:00"):
            put(rig, H.HEADER + self.line(when))
            self.assertEqual(len(read(rig)[0]), 1, when)


class LeftToTheCore(H.Case):
    def test_an_unreadable_time_passes_load_inputs_and_the_core_stops_the_morning(self):
        rig = H.Rig(self, start=START)
        extra = "x,2026-07-27,supplemental,observed,50,2026-07-28T07:05\n"           # no time zone
        report, inp = rig.morning(D, H.Provider(D), extra=extra)
        self.assertIsNone(inp.failure)
        self.assertEqual(len(inp.raw_observations), 2)
        self.assertEqual((report.run_outcome, report.kind, report.delivery), ("STOPPED", "halt", "SENT"))
        self.assertNotIn(report.code, ("input_ledger_observation_after_now", "input_ledger_header_invalid"))
        self.assertTrue(report.code.startswith("datetime_"), report.code)


class CommitAndReadOnly(H.Case):
    def test_the_sha_read_is_in_the_provenance_and_the_runner_writes_nothing(self):
        rig = H.Rig(self, start=START)
        rig.sync_ledger(D)
        before = rig.remote.refs()
        ledger_head = rig.remote.sha("v2-ledger")
        git = H.C.Spy(rig.clone.dir)
        report, inp = rig.morning(D, H.Provider(D), git=git)
        self.assertIsNone(inp.failure)
        self.assertEqual(inp.provenance["ledger_commit"], ledger_head)
        after = rig.remote.refs()
        self.assertEqual(after["refs/heads/v2-ledger"], before["refs/heads/v2-ledger"])
        self.assertEqual(rig.remote.log("v2-ledger")[-1]["sha"], ledger_head)
        self.assertEqual(len(rig.remote.log("v2-ledger")), 1)
        pushed = [c for c in git.calls if c[0] == "push"]
        self.assertEqual(len(pushed), 1)                                    # the pin only
        self.assertTrue(pushed[0][-1].endswith(":refs/heads/v2-market"))
        self.assertTrue(all("v2-ledger" not in " ".join(c) for c in git.calls if c[0] in ("push", "commit-tree", "update-ref")))

    def test_the_ledger_is_read_at_the_sha_that_the_fetch_decided(self):
        rig = H.Rig(self, start=START)
        put(rig, H.HEADER + H.decision_line("2026-07-27"))
        first = rig.remote.sha("v2-ledger")
        spy = H.C.Spy(rig.clone.dir)
        rows, head = read(rig, git=spy)
        self.assertEqual(head, first)
        put(rig, H.HEADER)                                                  # the user commits again afterwards
        rows2, head2 = read(rig, git=spy)
        self.assertEqual((len(rows), len(rows2)), (1, 0))
        self.assertEqual(head2, rig.remote.sha("v2-ledger"))
        self.assertNotEqual(head, head2)
        self.assertEqual([c[0] for c in spy.calls].count("fetch"), 2)


if __name__ == "__main__":
    unittest.main()
