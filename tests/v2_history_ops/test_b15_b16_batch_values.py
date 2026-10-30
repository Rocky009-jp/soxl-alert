"""B2-15 (the batch value and check_append_batch, design 8.3) and B2-16 (types, immutability, secrecy, design 12.8)."""
import ast
import copy
import os
import shutil
import tempfile
import unittest
from unittest import mock

import ho_helpers as T
import v2_history_ops as O
import v2_history_ops.batch as OB
from v2_history_ops.values import digest_of
from v2_persistence.codec import canonical_json
from v2_persistence.errors import PersistenceError
from v2_persistence.store import MemoryStore
from v2_recovery.ledger import LEDGER_KEYS

H, D, P, RH, V = T.H, T.D, T.P, T.RH, T.V
URL = "https://example.invalid/secret-token-path"
FG = 37.71


def rebuilt(body):
    """A batch whose batch_hash fits the (altered) body: only the contents are wrong."""
    return O.HistoryAppendBatch.from_dict({"body": body, "batch_hash": digest_of(body)})


class World(unittest.TestCase):
    def setUp(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        self.h, self.w = b.history(), b.w
        self.x = P.obs("x", D[1], 22.0)
        self.led = list(self.w.ledger) + [self.x]
        self.cmds = [T.ack_cmd(self.h, "ADDED", D[1], [T.fp(self.x)], 1)]
        self.plan = T.plan_for(self.h, self.cmds, self.w.sessions, self.led, D[2], "q1")
        self.res = O.confirm_history_resolution_plan(self.plan, self.plan.plan_hash, self.h, self.w.sessions, self.led)
        self.rbatch = self.res.batch
        ledger2 = list(self.w.ledger) + [P.obs("R2", D[2], 31.0)]
        self.day = O.prepare_history_day(self.h, D[2], self.w.series, self.w.sessions, ledger2)
        self.dbatch = self.day.batch


class Creation(World):
    """B2-15: a batch exists only for a prepared day and a confirmed plan."""

    def test_two_paths_only(self):
        self.assertEqual(self.dbatch.summary()["source"], "DAILY")
        self.assertEqual(self.rbatch.summary()["source"], "RESOLUTION")
        for batch in (self.dbatch, self.rbatch):
            self.assertIsInstance(batch, O.HistoryAppendBatch)
            self.assertFalse(batch.committed)

    def test_no_batch_from_the_other_outcomes(self):
        self.assertFalse(hasattr(self.plan, "batch"))                       # an unconfirmed plan has none
        self.assertEqual(self.day.committable, False)
        ledger = list(self.w.ledger)
        self.assertIsNone(O.prepare_history_day(self.h, D[2], self.w.series, self.w.sessions, ledger).batch)   # NO_COMMIT
        h2 = T.extend(self.h, self.day)
        again = O.prepare_history_day(h2, D[2], self.w.series, self.w.sessions, list(self.w.ledger) + [P.obs("R2", D[2], 31.0)])
        self.assertEqual((again.status, again.batch), ("ALREADY_APPLIED", None))
        nochange_plan = T.plan_for(self.res.history, self.cmds, self.w.sessions, self.led, D[2], "q1")
        res = O.confirm_history_resolution_plan(nochange_plan, nochange_plan.plan_hash, self.res.history,
                                                self.w.sessions, self.led)
        self.assertEqual((res.status, res.batch), ("NO_CHANGE", None))

    def test_the_constructor_is_closed_and_only_two_call_sites_make_a_batch(self):
        with self.assertRaises(TypeError):
            O.HistoryAppendBatch({"body": {}, "batch_hash": "0" * 64})
        root = os.path.dirname(OB.__file__)
        sites, direct = [], []
        for name in sorted(os.listdir(root)):
            if not name.endswith(".py"):
                continue
            with open(os.path.join(root, name), encoding="utf-8") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = node.func
                    called = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else None
                    if called == "make_batch" and name != "batch.py":
                        sites.append(name)
                    if (isinstance(fn, ast.Attribute) and fn.attr == "_make" and isinstance(fn.value, ast.Name)
                            and fn.value.id == "HistoryAppendBatch"):
                        direct.append(name)
        self.assertEqual(sorted(set(sites)), ["daily.py", "plan.py"])
        self.assertEqual(direct, ["batch.py"])                          # only make_batch builds the value

    def test_batch_hash_is_not_in_a_record_and_is_the_hash_of_the_body(self):
        for batch in (self.dbatch, self.rbatch):
            self.assertEqual(batch.batch_hash, digest_of(batch.body))
            for rec in batch.body["records"]:
                self.assertNotIn("batch_hash", rec)
                self.assertNotIn("plan_hash", rec)


class CheckAppendBatch(World):
    """The table of design 8.3: 1 type/form/hash, 2 history, 3 head, 4 records, 5 candidate digests, 6 the candidate."""

    def refuse(self, history, batch):
        e = T.refusal(O.check_append_batch, history, batch)
        return e.code, e.field, getattr(e, "rule", None)

    def test_success_returns_a_checked_candidate(self):
        for batch in (self.dbatch, self.rbatch):
            with mock.patch.object(OB, "validate_history", wraps=OB.validate_history) as vh:
                cand = O.check_append_batch(self.h, batch)
            self.assertEqual(vh.call_count, 2)                              # the history, then the candidate
            self.assertEqual(cand.digest, batch.body["candidate_digest"])
            self.assertEqual((cand.head_seq, cand.head_hash), (batch.body["candidate_head_seq"],
                                                               batch.body["candidate_head_hash"]))
            V.validate_history(cand)

    def test_1_type_form_and_hash(self):
        self.assertEqual(self.refuse(self.h, {"body": self.dbatch.body}), ("batch_invalid", "batch", "type"))
        self.assertEqual(self.refuse(self.h, None), ("batch_invalid", "batch", "type"))
        body = self.dbatch.body
        tampered = O.HistoryAppendBatch.from_dict({"body": body, "batch_hash": "0" * 64})
        self.assertEqual(self.refuse(self.h, tampered), ("batch_invalid", "batch", "batch_hash"))
        body["records"][0]["reason_code"] = "OTHER"                     # changed after the hash was made
        self.assertEqual(self.refuse(self.h, O.HistoryAppendBatch.from_dict(
            {"body": body, "batch_hash": self.dbatch.batch_hash})), ("batch_invalid", "batch", "batch_hash"))
        for key in ("operation", "source"):
            body = self.dbatch.body
            body[key] = "other"
            self.assertEqual(self.refuse(self.h, rebuilt(body)), ("batch_invalid", "batch", "batch_shape"))
        body = self.dbatch.body
        body["extra"] = 1
        self.assertEqual(self.refuse(self.h, rebuilt(body)), ("batch_invalid", "batch", "batch_shape"))
        body = self.dbatch.body
        body["candidate_head_hash"] = "XYZ"
        self.assertEqual(self.refuse(self.h, rebuilt(body)), ("batch_invalid", "batch", "batch_shape"))

    def test_2_history_errors_keep_their_own_codes(self):
        bad = self.h.to_dict()
        bad["events"][1]["event_hash"] = "0" * 64
        e = T.refusal(O.check_append_batch, V.History.from_dict(bad), self.dbatch)
        self.assertEqual((e.code, e.rule), ("history_invalid", "event_hash"))

    def test_3_head(self):
        longer = T.extend(self.h, self.day)
        self.assertEqual(self.refuse(longer, self.dbatch), ("batch_stale", "head", None))     # already holds the batch
        self.assertEqual(self.refuse(longer, self.rbatch), ("batch_stale", "head", None))
        body = self.dbatch.body
        body["expected_head_hash"] = "0" * 64
        self.assertEqual(self.refuse(self.h, rebuilt(body)), ("batch_stale", "head", None))

    def test_4_records(self):
        body = self.rbatch.body
        body["records"] = []
        self.assertEqual(self.refuse(self.h, rebuilt(body)), ("batch_invalid", "batch", "records"))
        body = self.rbatch.body
        body["records"] = ["x"]
        self.assertEqual(self.refuse(self.h, rebuilt(body)), ("batch_invalid", "batch", "records"))
        body = self.dbatch.body
        body["records"][0]["seq"] = 3                                    # a gap
        self.assertEqual(self.refuse(self.h, rebuilt(body)), ("batch_invalid", "batch", "seq"))
        body = self.dbatch.body
        body["records"].append(copy.deepcopy(body["records"][0]))
        body["records"][1]["seq"] = 3
        self.assertEqual(self.refuse(self.h, rebuilt(body)), ("batch_invalid", "batch", "source"))   # DAILY holds one
        body = self.dbatch.body
        body["d"] = D[3]
        self.assertEqual(self.refuse(self.h, rebuilt(body)), ("batch_invalid", "batch", "source"))
        body = self.rbatch.body
        body["request_id"] = "q2"                                        # not the records' request id
        self.assertEqual(self.refuse(self.h, rebuilt(body)), ("batch_invalid", "batch", "source"))
        body = self.rbatch.body
        body["plan_hash"] = None
        self.assertEqual(self.refuse(self.h, rebuilt(body)), ("batch_invalid", "batch", "source"))
        body = self.rbatch.body
        body["records"][0]["kind"] = "APPLY"                             # a RESOLUTION batch holds ACK / DECLARE only
        self.assertEqual(self.refuse(self.h, rebuilt(body)), ("batch_invalid", "batch", "source"))

    def test_4b_the_resolution_batch_of_several_records_is_one_request(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        h, w = b.history(), b.w
        _p, res = T.run_plan(h, [T.decl_cmd(D[2]), T.decl_cmd(D[3])], w.sessions, w.ledger, D[4], "q1")
        batch = res.batch
        self.assertEqual(len(batch.body["records"]), 2)
        O.check_append_batch(h, batch)
        body = batch.body
        body["records"][1]["request_id"] = "q2"
        self.assertEqual(self.refuse(h, rebuilt(body)), ("batch_invalid", "batch", "source"))
        body = batch.body
        body["records"][1]["command_count"] = 1
        self.assertEqual(self.refuse(h, rebuilt(body)), ("batch_invalid", "batch", "source"))

    def test_5_candidate_digests(self):
        body = self.dbatch.body
        body["candidate_digest"] = "0" * 64
        self.assertEqual(self.refuse(self.h, rebuilt(body)), ("batch_invalid", "batch", "candidate_digest"))
        body = self.dbatch.body
        body["candidate_head_hash"] = "0" * 64
        self.assertEqual(self.refuse(self.h, rebuilt(body)), ("batch_invalid", "batch", "candidate_digest"))
        body = self.dbatch.body
        body["candidate_state_digest"] = "0" * 64
        self.assertEqual(self.refuse(self.h, rebuilt(body)), ("batch_invalid", "batch", "candidate_digest"))
        body = self.dbatch.body
        body["records"][0]["reason_code"] = "OTHER"                      # the candidate no longer fits its digest
        self.assertEqual(self.refuse(self.h, rebuilt(body)), ("batch_invalid", "batch", "candidate_digest"))

    def test_6_the_candidate_is_validated_even_when_the_digests_were_made_to_fit(self):
        body = self.dbatch.body
        rec = body["records"][0]
        rec["state_after"] = dict(rec["state_after"], streak=7)          # a record that breaks the history rules
        H.finish(rec)                                                     # the hash fits: only the rules are broken
        cand = V.History.from_dict(dict(self.h.to_dict(), events=self.h.events + [rec]))
        body["candidate_digest"] = cand.digest
        body["candidate_head_seq"], body["candidate_head_hash"] = cand.head_seq, cand.head_hash
        body["candidate_state_digest"] = OB.sha256_text(canonical_json(cand.current_state))
        e = T.refusal(O.check_append_batch, self.h, rebuilt(body))
        self.assertIn(e.code, ("history_invalid", "batch_invalid"))


class Types(World):
    """B2-16 / design 12.8 step 2: two stages that are not mixed."""

    def deep(self):
        cur = top = {}
        for _ in range(2000):
            cur["a"] = {}
            cur = cur["a"]
        return top

    def test_from_dict_rejects_depth_big_numbers_and_non_json_types(self):
        cases = (("depth", self.deep(), "json_depth"), ("big integer", {"k": 10 ** 5000}, "json_number"),
                 ("nan", {"k": float("nan")}, "json_number"), ("tuple", {"k": (1, 2)}, "json_type"),
                 ("set", {"k": {1}}, "json_type"), ("bytes", {"k": b"x"}, "json_type"))
        for name, value, rule in cases:
            with self.subTest(name):
                e = T.refusal(O.HistoryResolutionPlan.from_dict, {"basis": value, "plan_hash": "0" * 64})
                self.assertEqual((e.code, e.rule), ("history_invalid", rule))
                e = T.refusal(O.HistoryAppendBatch.from_dict, {"body": value, "batch_hash": "0" * 64})
                self.assertEqual((e.code, e.rule), ("batch_invalid", rule))
        for bad in (None, [], {"basis": {}}, {"basis": {}, "plan_hash": "0" * 64, "x": 1}):
            self.assertEqual(T.refusal(O.HistoryResolutionPlan.from_dict, bad).rule, "plan_shape")
        for bad in (None, [], {"body": {}}, {"body": {}, "batch_hash": "0" * 64, "x": 1}):
            self.assertEqual(T.refusal(O.HistoryAppendBatch.from_dict, bad).rule, "batch_shape")

    def test_true_and_1_0_in_integer_fields_load_and_are_refused_later(self):
        for bogus in (True, 1.0):
            with self.subTest(bogus=bogus):
                basis = self.plan.basis
                basis["expected_head_seq"] = bogus
                plan = O.HistoryResolutionPlan.from_dict({"basis": basis, "plan_hash": digest_of(basis)})
                self.assertEqual(plan.basis["expected_head_seq"], bogus)           # kept as it came
                e = T.refusal(O.confirm_history_resolution_plan, plan, plan.plan_hash, self.h, self.w.sessions, self.led)
                self.assertEqual((e.code, e.field), ("history_plan_mismatch", "plan"))
                body = self.dbatch.body
                body["expected_head_seq"] = bogus
                batch = rebuilt(body)
                self.assertEqual(batch.body["expected_head_seq"], bogus)
                e = T.refusal(O.check_append_batch, self.h, batch)
                self.assertEqual((e.code, e.rule), ("batch_invalid", "type"))
        for key, where in (("seq", "records"), ("command_index", "plan")):
            body = self.dbatch.body
            body["records"][0]["seq"] = True
            e = T.refusal(O.check_append_batch, self.h, rebuilt(body))
            self.assertEqual((e.code, e.rule), ("batch_invalid", "seq"))
            basis = self.plan.basis
            basis["candidate_history"]["events"][2]["command_index"] = True
            plan = O.HistoryResolutionPlan.from_dict({"basis": basis, "plan_hash": digest_of(basis)})
            self.assertEqual(T.refusal(O.confirm_history_resolution_plan, plan, plan.plan_hash, self.h, self.w.sessions,
                                       self.led).code, "history_plan_mismatch")


class Immutability(World):
    def test_inputs_are_not_changed_and_are_copied(self):
        cmds, led = copy.deepcopy(self.cmds), copy.deepcopy(self.led)
        before = self.h.digest
        plan = T.plan_for(self.h, cmds, self.w.sessions, led, D[2], "q1")
        cmds[0]["d"] = "mutated"
        cmds[0]["record_fingerprints"].append("0" * 64)
        led[0]["current_fg_value"] = 1.0
        led.clear()
        self.assertEqual(plan.basis["commands"][0]["d"], D[1])
        O.confirm_history_resolution_plan(plan, plan.plan_hash, self.h, self.w.sessions, self.led)
        self.assertEqual(before, self.h.digest)

    def test_returned_nested_values_are_copies(self):
        view = O.read_effective(self.res.history)
        ledger = self.res.ledger
        for value, getters in ((view, ("applies", "resolutions", "segments", "requests", "effective_seqs",
                                       "current_boundary", "superseded_seqs")),
                               (ledger, ("rows", "supplemented", "excluded_fingerprints"))):
            snap = canonical_json(value.to_dict())
            for name in getters:
                got = getattr(value, name)
                if isinstance(got, list):
                    got.append("x")
                    got.clear()
                elif isinstance(got, dict):
                    got["x"] = 1
            self.assertEqual(canonical_json(value.to_dict()), snap)
        for value in (self.plan, self.rbatch, self.dbatch):
            snap = (canonical_json(value.to_dict()), hash(value))
            for name in ("basis", "body"):
                got = getattr(value, name, None)
                if isinstance(got, dict):
                    got["records" if name == "body" else "candidate_history"] = "x"
                    got.clear()
            self.assertEqual((canonical_json(value.to_dict()), hash(value)), snap)
        self.assertIsNot(self.day.core_result, self.day.core_result)        # a fresh copy on every read
        self.assertEqual(self.day.core_result, self.day.core_result)

    def test_every_value_is_frozen(self):
        for value in (self.plan, self.rbatch, self.dbatch, self.res, self.day, O.read_effective(self.h), self.res.ledger):
            with self.subTest(type=type(value).__name__):
                with self.assertRaises(AttributeError):
                    value.committed = True
                with self.assertRaises(AttributeError):
                    del value.committed
                with self.assertRaises(AttributeError):
                    value.anything = 1

    def test_equal_values_have_equal_hashes_and_texts(self):
        again = T.plan_for(self.h, self.cmds, self.w.sessions, self.led, D[2], "q1")
        self.assertEqual((again, hash(again), again.plan_hash), (self.plan, hash(self.plan), self.plan.plan_hash))
        self.assertNotEqual(self.dbatch, self.rbatch)


class Secrecy(unittest.TestCase):
    def setUp(self):
        b = H.HB()
        b.apply(D[1], 27.0)
        self.h, self.w = b.history(), b.w
        self.x = dict(P.obs("x", D[1], FG), note=URL, source_url=URL)         # extra columns with a URL
        self.led = [dict(r, note=URL, source_url=URL) for r in self.w.ledger] + [self.x]
        self.cmds = [T.ack_cmd(self.h, "ADDED", D[1], [T.fp(self.x)], 1)]

    def clean(self, text):
        self.assertNotIn("secret-token", text)
        self.assertNotIn("example.invalid", text)
        self.assertNotIn(str(FG), text)

    def test_outputs_do_not_carry_urls_notes_or_values(self):
        plan = T.plan_for(self.h, self.cmds, self.w.sessions, self.led, D[2], "q1")
        res = O.confirm_history_resolution_plan(plan, plan.plan_hash, self.h, self.w.sessions, self.led)
        view = O.read_effective(res.history)
        ledger = O.project_history_ledger(res.history, self.w.sessions, self.led, D[2])
        day = O.prepare_history_day(res.history, D[2], self.w.series, self.w.sessions,
                                    [r for r in self.led if r is not self.x] + [P.obs("R2", D[2], 31.0)])
        for value in (plan, res, view, ledger, day, res.batch, day.batch):
            self.clean(repr(value))
            self.clean(str(value))
        for value in (plan, res.batch, day.batch):
            self.clean(canonical_json(value.to_dict()))
            self.clean(repr(value.summary()))
        self.clean(canonical_json(view.to_dict()))
        self.assertEqual(set(ledger.rows[0]), set(LEDGER_KEYS))              # extra columns are dropped

    def test_error_strings_do_not_carry_them_either(self):
        bad_row = dict(P.obs("y", D[1], FG), note=URL, source_url=URL, observation_status="nonsense")
        calls = [
            lambda: O.project_history_ledger(self.h, self.w.sessions, self.led, D[1]),
            lambda: T.plan_for(self.h, self.cmds, self.w.sessions, [bad_row] + self.led, D[2], "q1"),
            lambda: T.plan_for(self.h, self.cmds, self.w.sessions, self.led, D[2], "q1x" * 100),
            lambda: T.plan_for(self.h, [dict(self.cmds[0], note=URL)], self.w.sessions, self.led, D[2], "q1"),
            lambda: O.prepare_history_day(self.h, D[1], self.w.series, self.w.sessions, self.led),
            lambda: O.HistoryAppendBatch.from_dict({"body": {"source": URL}, "batch_hash": URL, "x": URL}),
            lambda: O.HistoryResolutionPlan.from_dict({"basis": {"k": (URL,)}, "plan_hash": URL}),
        ]
        for call in calls:
            try:
                call()
            except (PersistenceError, Exception) as e:      # any refusal: only fixed identifiers may appear
                text = str(e) + repr(e) + repr(getattr(e, "__dict__", {}))
                self.clean(text)

    def test_unverified_values_show_only_checked_fields(self):
        plan = O.HistoryResolutionPlan.from_dict({"basis": {"request_id": URL, "status": URL, "commands": [URL]},
                                                  "plan_hash": URL})
        batch = O.HistoryAppendBatch.from_dict({"body": {"source": URL, "request_id": URL, "records": URL},
                                                "batch_hash": URL})
        for value in (plan, batch):
            self.clean(repr(value))
            with self.assertRaises(PersistenceError) as cm:
                value.summary()
            self.clean(str(cm.exception) + repr(cm.exception.__dict__))


class StoresRefuseEveryValue(World):
    def things(self):
        out = [self.plan, self.res, self.rbatch, self.dbatch, self.day, self.res.history, self.res.ledger,
               O.read_effective(self.h), O.check_append_batch(self.h, self.dbatch), self.plan.basis, self.dbatch.body]
        return out

    def test_memory_store(self):
        store = MemoryStore()
        for thing in self.things():
            with self.subTest(type=type(thing).__name__):
                with self.assertRaises(PersistenceError) as cm:
                    store.commit(thing)
                self.assertEqual((cm.exception.code, cm.exception.rule), ("snapshot_invalid", "plan_type"))

    def test_local_file_store_with_a_file_sync_only_root(self):
        from v2_persistence.local import LocalFileStore
        root = tempfile.mkdtemp(prefix="v2s3b2_root_")
        try:
            store = LocalFileStore(root, writable=True, durability="file_sync_only")
            for thing in self.things():
                with self.subTest(type=type(thing).__name__):
                    with self.assertRaises(PersistenceError) as cm:
                        store.commit(thing)
                    self.assertEqual((cm.exception.code, cm.exception.rule), ("snapshot_invalid", "plan_type"))
            self.assertEqual(os.listdir(root), [])
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
