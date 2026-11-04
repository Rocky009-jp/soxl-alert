"""C3-06: the values the store does not take. None of these takes the lock (the recorded FileOps calls show no creation
of write.lock) or changes the root. This file may call the private constructor to make a value by hand, for the N-01
item only (second edition of the request); the runtime may not (test_c3_09)."""
import unittest

import c3_helpers as H
from v2_history_publish import CREATE, GENESIS, HistoryPublication


def no_lock(case, ops):
    case.assertEqual(ops.ops("create_exclusive"), [])
    case.assertEqual(ops.ops("create_exclusive:lock"), [])
    case.assertEqual(ops.ops("unlink"), [])


class WrongTypes(H.RootCase):
    def things(self):
        c = H.C2.day_case()
        g = H.C2.genesis_case()
        return {
            "dict": c.pub.to_dict(), "body dict": c.pub.body, "none": None, "string": "publication",
            "history": c.candidate, "confirm result": c.conf if hasattr(c, "conf") else c.candidate,
            "reconciliation": H.U.reconcile_publication(c.current, c.pub), "list": [c.pub], "int": 1,
            "bytes": c.current, "subclass-like object": object(), "genesis history": g.candidate,
        }

    def test_initialize_publish_and_reconcile_refuse_by_type_before_the_lock(self):
        H.C2.restore_case(consume=False)          # (only to make the cases of c2_helpers once)
        for name, value in self.things().items():
            for op in ("initialize", "publish", "reconcile"):
                with self.subTest(thing=name, op=op):
                    ops = H.C3Ops()
                    store = self.store(ops)
                    e = self.run_err(getattr(store, op), value)
                    self.assertStore(e, "store_publication_invalid", "publication", "args", rule="type")
                    no_lock(self, ops)
                    self.assertEqual(H.listing(self.root), [])

    def test_a_subclass_of_the_class_is_not_the_class(self):
        # type(p) is HistoryPublication: an instance of a subclass, made through the class's own wrapping function with
        # the content of a real value, is refused by its exact type
        class Sub(HistoryPublication):
            __slots__ = ()
        with self.assertRaises(TypeError):
            Sub()
        c = H.C2.day_case()
        self.put_current(c)
        sub = Sub._wrap({"body": c.pub.body, "publication_hash": c.pub.publication_hash}, ValueError)
        self.assertIsInstance(sub, HistoryPublication)
        self.assertEqual(sub.publication_hash, c.pub.publication_hash)
        for op in ("publish", "reconcile"):
            ops = H.C3Ops()
            e = self.run_err(getattr(self.store(ops), op), sub)
            self.assertStore(e, "store_publication_invalid", "publication", "args", rule="type")
            no_lock(self, ops)
        self.assertEqual(H.raw(self.root), c.current)


class WrongKinds(H.RootCase):
    def test_publish_takes_append_only(self):
        for case in (H.C2.genesis_case(), H.C2.migration_case(), H.C2.adoption_case()):
            with self.subTest(source=case.source):
                ops = H.C3Ops()
                e = self.run_err(self.store(ops).publish, case.pub)
                self.assertStore(e, "store_operation_unsupported", "publication", "args", rule="not_append")
                no_lock(self, ops)

    def test_initialize_takes_a_genesis_only(self):
        cases = H.append_cases() + [H.C2.migration_case(), H.C2.adoption_case()]
        for case in cases:
            with self.subTest(source=case.source):
                ops = H.C3Ops()
                e = self.run_err(self.store(ops).initialize, case.pub)
                self.assertStore(e, "store_operation_unsupported", "publication", "args", rule="not_genesis")
                no_lock(self, ops)
        self.assertEqual(H.listing(self.root), [])

    def test_the_kind_is_judged_before_writability(self):
        # a read-only store with a wrong value says what is wrong with the value first (the order of the design)
        e = self.run_err(self.store(writable=False).publish, "x")
        self.assertEqual(e.code, "store_publication_invalid")
        e = self.run_err(self.store(writable=False).publish, H.C2.genesis_case().pub)
        self.assertEqual(e.code, "store_operation_unsupported")
        e = self.run_err(self.store(writable=False).publish, H.C2.day_case().pub)
        self.assertEqual(e.code, "store_read_only")


class HandMadeBodiesWithoutMode(H.RootCase):
    """N-01 (second edition): a value made by hand whose body has no mode (for an initialization, no source either) is
    refused before the lock with a fixed code, never with a raw KeyError."""

    def forged(self, base, drop):
        body = base.pub.body
        for key in drop:
            body.pop(key)
        return HistoryPublication._make(body)

    def test_publish_without_mode(self):
        c = H.C2.day_case()
        for drop in (["mode"], ["mode", "source"]):
            with self.subTest(drop=drop):
                ops = H.C3Ops()
                self.put_current(c)
                before = H.state_of(self.root)
                e = self.run_err(self.store(ops).publish, self.forged(c, drop))
                self.assertStore(e, "store_publication_invalid", "publication", "args", rule="shape")
                no_lock(self, ops)
                self.assertEqual(H.state_of(self.root), before)

    def test_initialize_without_mode_or_without_source(self):
        g = H.C2.genesis_case()
        for drop in (["mode"], ["source"], ["mode", "source"]):
            with self.subTest(drop=drop):
                ops = H.C3Ops()
                e = self.run_err(self.store(ops).initialize, self.forged(g, drop))
                self.assertStore(e, "store_publication_invalid", "publication", "args", rule="shape")
                no_lock(self, ops)
                self.assertEqual(H.listing(self.root), [])

    def test_a_body_that_is_not_a_dictionary(self):
        for body in ("text", [], None, 5, [1, 2]):
            for op in ("initialize", "publish"):
                with self.subTest(body=repr(body), op=op):
                    ops = H.C3Ops()
                    e = self.run_err(getattr(self.store(ops), op), HistoryPublication._make(body))
                    self.assertStore(e, "store_publication_invalid", "publication", "args", rule="shape")
                    no_lock(self, ops)

    def test_the_error_carries_no_value_and_no_chained_error(self):
        c = H.C2.day_case()
        e = self.run_err(self.store().publish, self.forged(c, ["mode"]))
        self.assertIsNone(e.__cause__)
        self.assertTrue(e.__suppress_context__)
        self.assertNotIn("KeyError", repr(e))
        self.assertNotIn("mode", str(e))

    def test_a_publish_with_a_mode_but_no_source_reaches_the_check_and_is_refused_there(self):
        # publish reads only the mode; the missing source is the form error of the value that check_publication names
        c = H.C2.day_case()
        self.put_current(c)
        e = self.run_err(self.store().publish, self.forged(c, ["source"]))
        self.assertEqual((e.code, e.rule), ("publication_invalid", "shape"))
        self.assertEqual(H.raw(self.root), c.current)

    def test_a_create_value_with_a_wrong_source_is_not_a_genesis(self):
        g = H.C2.genesis_case()
        body = g.pub.body
        body["source"] = "MIGRATION"
        ops = H.C3Ops()
        e = self.run_err(self.store(ops).initialize, HistoryPublication._make(body))
        self.assertStore(e, "store_operation_unsupported", rule="not_genesis")
        no_lock(self, ops)
        self.assertEqual((CREATE, GENESIS), ("CREATE", "GENESIS"))


if __name__ == "__main__":
    unittest.main()
