"""S4D-06 and S4D-07: the form of market.json (canonical bytes, what is refused), the pin on the remote, and the equality of
the series read from a pin with the research fixture on the six days of the trial (T-4)."""
import json
import unittest

import s4d_helpers as H
import v2_inputs.market as M
from v2_core.fixture import MarketSeries, load_research_fixture

I = H.I
InputError = H.InputError
SIX = ("2024-10-01", "2025-01-02", "2025-06-02", "2026-03-02", "2026-07-28", "2026-08-10")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def expected_body(through, rows):
    out = {"schema": "v2_inputs.market.1", "through": through, "source": "yahoo_chart_v8", "symbols": {}}
    for s in H.SYMBOLS:
        dates = sorted(d for d in rows[s] if H.PRE <= d <= through)
        out["symbols"][s] = {"dates": dates, "close": [rows[s][d][0] for d in dates],
                             "adjclose": [rows[s][d][1] for d in dates]}
    return out


class Shape(H.Case):
    def test_the_bytes_are_canonical_and_hold_the_expected_content(self):
        rows = H.research("2026-07-28")
        data = M.snapshot_bytes("2026-07-28", rows)
        self.assertEqual(json.loads(data.decode("ascii")), expected_body("2026-07-28", rows))
        self.assertEqual(canonical(json.loads(data)), data)                    # sorted keys, "," ":" separators, ASCII
        self.assertEqual(list(json.loads(data)), ["schema", "source", "symbols", "through"])
        self.assertTrue(data.isascii())
        self.assertNotIn(b" ", data)

    def test_the_same_content_in_another_order_gives_the_same_bytes(self):
        rows = H.research("2026-07-28")
        reversed_rows = {s: dict(reversed(list(rows[s].items()))) for s in reversed(list(rows))}
        self.assertEqual(M.snapshot_bytes("2026-07-28", rows), M.snapshot_bytes("2026-07-28", reversed_rows))
        # rows after the day or before the start do not enter
        more = {s: dict(rows[s]) for s in rows}
        for s in more:
            more[s]["2026-08-03"] = (1.0, 1.0)
            more[s]["2009-01-02"] = (1.0, 1.0)
        self.assertEqual(M.snapshot_bytes("2026-07-28", rows), M.snapshot_bytes("2026-07-28", more))

    def test_read_and_write_again_gives_the_same_bytes(self):
        rows = H.research("2026-07-28")
        data = M.snapshot_bytes("2026-07-28", rows)
        through, back = M.read_snapshot(data)
        self.assertEqual(through, "2026-07-28")
        self.assertEqual(M.snapshot_bytes(through, back), data)
        self.assertEqual(back["SOXX"]["2026-07-28"], rows["SOXX"]["2026-07-28"])

    def test_what_is_not_a_snapshot_is_refused(self):
        good = json.loads(M.snapshot_bytes("2026-07-28", H.research("2026-07-28")))

        def variant(edit):
            data = json.loads(json.dumps(good))
            edit(data)
            return canonical(data)

        sx = lambda d: d["symbols"]["SOXX"]    # noqa: E731
        bad = [b"", b"x", b"{", b"null", b"[]", b"\xff", "not bytes", None, 3,
               json.dumps(good, ensure_ascii=False).replace("2026", "٢026").encode("utf-8"),
               variant(lambda d: d.update(schema="v2_inputs.market.2")), variant(lambda d: d.pop("schema")),
               variant(lambda d: d.update(source="other")), variant(lambda d: d.pop("source")),
               variant(lambda d: d.update(through="2026-7-28")), variant(lambda d: d.update(through=None)),
               variant(lambda d: d.pop("through")), variant(lambda d: d.pop("symbols")),
               variant(lambda d: d["symbols"].pop("SPY")), variant(lambda d: d["symbols"].pop("SOXL")),
               variant(lambda d: sx(d).pop("dates")), variant(lambda d: sx(d).pop("close")),
               variant(lambda d: sx(d).pop("adjclose")),
               variant(lambda d: sx(d)["close"].pop()), variant(lambda d: sx(d)["adjclose"].append(1.0)),
               variant(lambda d: sx(d)["dates"].pop()),
               variant(lambda d: sx(d)["close"].__setitem__(5, 0)), variant(lambda d: sx(d)["close"].__setitem__(5, -1.0)),
               variant(lambda d: sx(d)["adjclose"].__setitem__(5, 1000000)),
               variant(lambda d: sx(d)["adjclose"].__setitem__(5, None)),
               variant(lambda d: sx(d)["adjclose"].__setitem__(5, True)),
               variant(lambda d: sx(d)["close"].__setitem__(5, "9.5")),
               variant(lambda d: sx(d)["dates"].__setitem__(5, "2010-02-30")),
               variant(lambda d: sx(d)["dates"].reverse()),
               variant(lambda d: sx(d)["dates"].__setitem__(6, sx(d)["dates"][5])),
               variant(lambda d: d.update(through="2026-07-27")),       # the rows go past the day
               variant(lambda d: [sx(d)[k].pop(0) for k in ("dates", "close", "adjclose")])]   # no row on the start day
        for data in bad:
            with self.assertRaises(InputError) as cm:
                M.read_snapshot(data)
            self.assertEqual((cm.exception.code, cm.exception.field, cm.exception.detail),
                             ("input_market_pin_invalid", "market", None))

    def test_the_pin_on_the_remote_a_missing_ref_a_missing_file_and_a_bad_file(self):
        rig = H.Rig(self)
        pin = M.MarketPin(rig.clone.git, "v2-market", H.C.clock)
        self.assertEqual(pin.read(), (None, None, None, None))
        rig.remote.plant("v2-market", {"other.txt": b"x"}, parent=None)
        with self.assertRaises(InputError) as cm:
            pin.read()
        self.assertEqual(cm.exception.code, "input_market_pin_invalid")
        rig.remote.plant("v2-market", {"market.json": b"{}"}, parent="HEAD~")
        with self.assertRaises(InputError) as cm:
            pin.read()
        self.assertEqual(cm.exception.code, "input_market_pin_invalid")
        data = M.snapshot_bytes("2026-07-28", H.research("2026-07-28"))
        rig.remote.plant("v2-market", {"market.json": data}, parent="HEAD~")
        head, through, rows, digest = pin.read()
        self.assertEqual((head, through, digest), (rig.remote.sha("v2-market"), "2026-07-28", H.blob_sha256(data)))
        self.assertEqual(rows["SOXL"]["2026-07-28"], H.research()["SOXL"]["2026-07-28"])

    def test_a_response_without_a_row_on_the_prehistory_start_is_a_short_history(self):
        rig = H.Rig(self)
        rig.with_decisions("2026-07-28")
        rows = H.research()
        del rows["SOXX"][H.PRE]
        report, inp = rig.morning("2026-07-28", H.Provider("2026-07-28", rows=rows))
        self.assertEqual((inp.failure.code, inp.failure.field, inp.failure.detail),
                         ("input_market_history_short", "market", "2010-02-11"))
        self.assertIsNone(rig.remote.sha("v2-market"))                         # nothing was pinned
        self.assertEqual((report.run_outcome, report.code, report.kind, report.delivery),
                         ("STOPPED", "input_market_history_short", "halt", "SENT"))
        # a null on that day is the same thing
        rows = H.research()
        rows["SOXX"][H.PRE] = (None, None)
        provider = H.Provider("2026-07-28", rows=rows)
        inp, _now = rig.inputs("2026-07-28", provider)
        self.assertEqual(inp.failure.code, "input_market_history_short")
        # the research data has the row: no failure
        inp, _now = rig.inputs("2026-07-28", H.Provider("2026-07-28"))
        self.assertIsNone(inp.failure)


class ResearchEquality(H.Case):
    def check(self, series, day, reference):
        self.assertEqual(series.row(day), reference.row(day), day)
        self.assertEqual(series.soxl_close(day), reference.soxl_close(day), day)
        self.assertEqual(series.dates, reference.dates)
        self.assertEqual(series.soxx, reference.soxx)
        for d in [x for x in reference.dates if x <= day][-30:]:
            self.assertEqual(series.shd_at(d), reference.shd_at(d), d)
            self.assertEqual(series.soxl_close(d), reference.soxl_close(d), d)

    def test_the_series_read_from_a_pin_equals_the_research_fixture_on_six_days(self):
        for day in SIX:
            reference, _fg = load_research_fixture(H.DATA_DIR, through=day)
            data = M.snapshot_bytes(day, H.research())
            through, rows = M.read_snapshot(data)
            series = M.series_of(through, rows, H.blob_sha256(data))
            self.check(series, day, reference)
            self.assertEqual(series.meta["price_definition"], reference.meta["price_definition"])
            self.assertEqual(series.meta["soxl_close_definition"], reference.meta["soxl_close_definition"])
            self.assertEqual(series.meta["input_manifest"], [{"file": "market.json", "sha256": H.blob_sha256(data)}])

    def test_the_series_of_load_inputs_equals_the_research_fixture_on_the_days_inside_the_table(self):
        for day in ("2026-03-02", "2026-07-28", "2026-08-10"):
            rig = H.Rig(self, start="2026-02-27")
            rig.with_decisions(day)
            inp, _now = rig.inputs(day, H.Provider(day))
            self.assertIsNone(inp.failure, day)
            reference, _fg = load_research_fixture(H.DATA_DIR, through=day)
            self.check(inp.series, day, reference)
            self.assertEqual(inp.provenance["market_through"], day)
            self.assertEqual(inp.provenance["market_sha256"], H.blob_sha256(rig.remote.blob("v2-market", "market.json")))


class Columns(H.Case):
    """Which column goes where: dates and values of SOXX are the adjusted close, SPY and IEF the adjusted close, the dates of the
    return spread (market_dates) are those where both exist, and SOXL is the close. The reference is assembled here from that
    rule on rows whose close and adjusted close differ everywhere."""

    DAY = "2026-07-28"

    def rows(self):
        base = H.research(self.DAY)
        mod = {}
        for k, s in enumerate(H.SYMBOLS):
            mod[s] = {d: (v[0] * (1.0 + 0.01 * (k + 1)), v[1] * (1.0 - 0.0005 * ((i + k) % 7)))
                      for i, (d, v) in enumerate(sorted(base[s].items()))}
        del mod["IEF"]["2026-07-20"]                       # SPY has the day, IEF has not
        return mod

    def reference(self, mod, spy_column=1, ief_column=1, soxx_column=1, soxl_column=0, both=True):
        dates = sorted(d for d in mod["SOXX"] if d >= H.PRE)
        spy = {d: v[spy_column] for d, v in mod["SPY"].items()}
        ief = {d: v[ief_column] for d, v in mod["IEF"].items()}
        series = M.series_of(self.DAY, mod, "x")
        return MarketSeries(dates, [mod["SOXX"][d][soxx_column] for d in dates], spy, ief,
                            (set(spy) & set(ief)) if both else (set(spy) | set(ief)),
                            soxl_close={d: v[soxl_column] for d, v in mod["SOXL"].items()}, meta=dict(series.meta))

    def test_the_series_takes_the_documented_columns(self):
        mod = self.rows()
        data = M.snapshot_bytes(self.DAY, mod)
        through, back = M.read_snapshot(data)
        series = M.series_of(through, back, H.blob_sha256(data))
        ref = self.reference(mod)
        self.assertEqual(series.dates, ref.dates)
        self.assertEqual(series.soxx, ref.soxx)
        self.assertEqual(series.row(self.DAY), ref.row(self.DAY))
        self.assertEqual(series.soxl_close(self.DAY), ref.soxl_close(self.DAY))
        for d in [x for x in ref.dates if x <= self.DAY][-40:]:
            self.assertEqual(series.shd_at(d), ref.shd_at(d), d)
            self.assertEqual(series.soxl_close(d), ref.soxl_close(d), d)

    def test_the_reference_does_tell_the_other_columns_and_sets_apart(self):
        mod = self.rows()
        ref = self.reference(mod)
        for kw in ({"spy_column": 0}, {"ief_column": 0}, {"soxx_column": 0}, {"both": False}):
            other = self.reference(mod, **kw)
            different = (other.row(self.DAY) != ref.row(self.DAY)
                         or any(other.shd_at(d) != ref.shd_at(d) for d in ref.dates[-40:]) or other.soxx != ref.soxx)
            self.assertTrue(different, kw)
        self.assertNotEqual(self.reference(mod, soxl_column=1).soxl_close(self.DAY), ref.soxl_close(self.DAY))


if __name__ == "__main__":
    unittest.main()
