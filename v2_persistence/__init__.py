"""V2 persistence domain, stage S1: in-memory transition records, single-day preparation and compare-and-swap.

Offline only. No files, no clock, no network, no notification, no credentials. Draft, not adopted for production.
Depends on the standard library and v2_core (unchanged). A MemoryStore is not durable storage.
"""

__all__ = ["errors", "codec", "events", "recompute", "plan", "runner", "store"]
