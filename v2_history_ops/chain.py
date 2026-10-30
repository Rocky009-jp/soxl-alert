"""The effective chain of a checked History: segments, fixed facts for the rule functions, the current segment as an
S1 Snapshot, and the effective view.

Only the effective records are read (HistoryCheck.effective_seqs); a superseded record is never used as an ACK, a
declaration or an APPLY. References are always the v2 physical seq and event hash. The temporary S1 numbers that the
S1 projection of the current segment gives are used inside prepare_day only and never leave this package.
No rule, threshold or state formula is written here: S1 recalculates (project_segment, prepare_day), the S3-A rule
functions judge the ledger.
"""
from v2_history.values import (ACK, APPLY, DECLARE_MISSING, GENESIS, RECOVERY_RESTORE, RESTART_UNKNOWN,
                               SCHEMA_MIGRATION)
from v2_history.view import Segment, project_segment
from v2_persistence.codec import canonical_json, sha256_text
from v2_persistence.events import make_apply_event, make_genesis_event, snapshot_of
from v2_recovery.facts import FixedFacts

from .values import EffectiveView

NATIVE, MIGRATED, REPLAYED = "NATIVE", "MIGRATED", "REPLAYED"
RESOLUTION = "RESOLUTION"
_REQUEST_KINDS = {ACK: RESOLUTION, DECLARE_MISSING: RESOLUTION, RESTART_UNKNOWN: RESTART_UNKNOWN,
                  RECOVERY_RESTORE: RECOVERY_RESTORE, SCHEMA_MIGRATION: SCHEMA_MIGRATION}


def source_of(rec):
    """Where a record comes from. A record that carries an origin was made by the explicit migration (its request
    basis is in the S3-A namespace, even if a restore replayed it later); a replayed one points at its original."""
    if rec.get("origin") is not None:
        return MIGRATED
    if rec.get("replay_of") is not None:
        return REPLAYED
    return NATIVE


class Chain:
    """Everything read from one checked History. `events` is the physical list, `recs` the effective chain."""

    def __init__(self, history, check):
        self.history = history
        self.check = check
        self.events = history.events
        self.recs = [self.events[s] for s in check.effective_seqs]
        self.segments = []                     # [Segment]
        self.seg_declares = []                 # per segment: effective DECLARE_MISSING seqs
        self.seg_resolutions = []              # per segment: effective ACK / DECLARE_MISSING seqs
        for rec in self.recs:
            kind = rec["kind"]
            if kind == GENESIS:
                self._open(Segment(GENESIS, rec["seq"], rec["start_after"], rec["boundary_session"]))
            elif kind == RESTART_UNKNOWN:
                self._open(Segment(RESTART_UNKNOWN, rec["seq"], rec["resume_after"], rec["boundary_session"]))
            elif kind == APPLY:
                self.segments[-1].applies.append(rec)
            elif kind in (ACK, DECLARE_MISSING):
                self.seg_resolutions[-1].append(rec["seq"])
                if kind == DECLARE_MISSING:
                    self.seg_declares[-1].append(rec["seq"])
        # the S1 checker's own reading of every segment (skipped sessions; the reference for fingerprints)
        self.projected = [project_segment(seg) for seg in self.segments]
        self.resolutions = [rec for rec in self.recs if rec["kind"] in (ACK, DECLARE_MISSING)]
        self.facts = self._facts()

    def _open(self, segment):
        self.segments.append(segment)
        self.seg_declares.append([])
        self.seg_resolutions.append([])

    def _facts(self):
        applies = []
        for seg, validated in zip(self.segments, self.projected):
            for rec, applied in zip(seg.applies, validated.applies):
                ci = rec["confirmed_inputs"]
                applies.append({"seq": rec["seq"], "event_hash": rec["event_hash"], "d": rec["d"],
                                "decision": ci["decision"], "context": ci["session_context"],
                                "skipped": applied.skipped})
        declares = [{"seq": r["seq"], "event_hash": r["event_hash"], "d": r["d"], "context": r["session_context"]}
                    for r in self.resolutions if r["kind"] == DECLARE_MISSING]
        boundaries = [{"date": seg.date, "session": seg.session} for seg in self.segments]
        return FixedFacts.from_parts(applies, declares, boundaries, self.segments[-1].date, self.check.head_seq)

    # --- the current segment as an S1 Snapshot -----------------------------------------------------------------
    def current_snapshot(self):
        """GENESIS(boundary) and the current segment's APPLY records, re-attached with temporary S1 numbers. The
        rebuilt input hash must equal the one the v2 record carries (it was checked when the history was checked)."""
        seg = self.segments[-1]
        events = [make_genesis_event(seg.date, seg.session)]
        for i, rec in enumerate(seg.applies, 1):
            ev = make_apply_event(i, events[-1]["event_hash"], rec["d"], rec["confirmed_inputs"],
                                  rec["skipped_sessions"], rec["transition_result"], rec["state_after"])
            events.append(ev)
        return snapshot_of(events)

    def request_groups(self):
        """Every request id of the physical history (superseded records included), grouped by id, kind, source and
        request hash. `effective` is true when a record of the group is on the effective chain."""
        effective = set(self.check.effective_seqs)
        groups = {}
        for rec in self.events:
            kind = _REQUEST_KINDS.get(rec["kind"])
            if kind is None:
                continue
            key = (rec["request_id"], kind, source_of(rec), rec["request_hash"])
            group = groups.setdefault(key, {"request_id": rec["request_id"], "record_kind": kind,
                                            "request_hash": rec["request_hash"], "seqs": [],
                                            "effective": False, "source": key[2]})
            group["seqs"].append(rec["seq"])
            if rec["seq"] in effective:
                group["effective"] = True
        return list(groups.values())

    # --- the effective view ---------------------------------------------------------------------------------------
    def view(self):
        check, events = self.check, self.events
        segment_of = {}
        for seg in self.segments:
            for rec in seg.applies:
                segment_of[rec["seq"]] = seg.seq
        seg_res_of = {}
        for seg, seqs in zip(self.segments, self.seg_resolutions):
            for s in seqs:
                seg_res_of[s] = seg.seq
        applies = []
        for rec in self.recs:
            if rec["kind"] == APPLY:
                fa = self.facts.by_seq[rec["seq"]]
                applies.append({"seq": rec["seq"], "event_hash": rec["event_hash"], "d": rec["d"],
                                "segment_seq": segment_of[rec["seq"]], "record_id": fa.record_id,
                                "fingerprint": fa.fingerprint, "skipped": list(fa.skipped)})
        resolutions = [{
            "seq": r["seq"], "event_hash": r["event_hash"], "kind": r["kind"], "variant": r["variant"],
            "d": r["d"], "request_id": r["request_id"], "command_index": r["command_index"],
            "command_count": r["command_count"], "source": source_of(r), "applied_ref": r["applied_ref"],
            "missing_ref": r["missing_ref"], "record_fingerprints": list(r["record_fingerprints"]),
            "segment_seq": seg_res_of[r["seq"]]} for r in self.resolutions]
        segments = [{"kind": seg.kind, "seq": seg.seq, "after": seg.date,
                     "apply_seqs": [r["seq"] for r in seg.applies], "declare_seqs": list(declares),
                     "resolution_seqs": list(res)}
                    for seg, declares, res in zip(self.segments, self.seg_declares, self.seg_resolutions)]
        migration = [r["seq"] for r in events if r["kind"] == SCHEMA_MIGRATION]
        boundary = check.current_boundary
        return EffectiveView._make({
            "history_digest": check.history_digest, "head_seq": check.head_seq, "head_hash": check.head_hash,
            "state_digest": check.state_digest, "migrated": check.migrated,
            "migration_seq": migration[0] if migration else None,
            "effective_seqs": list(check.effective_seqs), "superseded_seqs": list(check.superseded_seqs),
            "current_boundary": {"kind": boundary.kind, "seq": boundary.seq, "after": boundary.after},
            "processing_after": check.processing_after, "latest_apply_d": check.latest_apply_d,
            "segments": segments, "applies": applies, "resolutions": resolutions,
            "requests": self.request_groups()})


def state_digest_of(state):
    return sha256_text(canonical_json(state))
