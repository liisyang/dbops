"""Application-wide constants.

Single source of truth for sets of statuses, status spellings, and other
enumerated values that were previously inlined in 3-4 places (C4).
"""
from __future__ import annotations

from typing import Final, NewType


# ---------------------------------------------------------------------------
# I-7: Branded types for terminal status sets.
# ---------------------------------------------------------------------------
# NewType gives mypy a thin veneer: it cannot stop you from comparing
# the wrong set, but it does surface in `reveal_type` output and will
# catch accidental cross-set assignments in strict callers. The runtime
# cost is zero (NewType is a no-op at runtime; the values are str).
RunTerminalStatus = NewType("RunTerminalStatus", str)
BatchTerminalStatus = NewType("BatchTerminalStatus", str)
DispatchTerminalStatus = NewType("DispatchTerminalStatus", str)
AwxTerminalStatus = NewType("AwxTerminalStatus", str)


# ---------------------------------------------------------------------------
# Dispatch / batch terminal status sets
# ---------------------------------------------------------------------------
# These match the values allowed by:
#   chk_collector_batch_run_status    (dbops_assets.py CheckConstraint)
#   chk_collector_dispatch_run_status (dbops_assets.py CheckConstraint)
# Adding a new terminal status: update DB CHECK first, then update this set.
BATCH_TERMINAL_STATUSES: Final[frozenset[BatchTerminalStatus]] = frozenset(
    {
        "success",
        "partial_success",
        "failed",
        "timeout",
        "callback_failed",
        "cancelled",
    }  # type: ignore[arg-type]
)
# Dispatch and batch share the same set; alias for clarity at call sites.
DISPATCH_TERMINAL_STATUSES: Final[frozenset[DispatchTerminalStatus]] = (
    BATCH_TERMINAL_STATUSES  # type: ignore[assignment]
)


# ---------------------------------------------------------------------------
# CollectorRun terminal status set
# ---------------------------------------------------------------------------
# NB: collector_run.status uses the US spelling "canceled" (double L) per
# the phase 2 refactor schema, while batch_run / dispatch_run use "cancelled"
# (single L). Do not mix spellings — this set is ONLY compared against
# CollectorRun.status.
RUN_TERMINAL_STATUSES: Final[frozenset[RunTerminalStatus]] = frozenset(
    {
        "success",
        "failed",
        "partial_success",
        "callback_failed",
        "timeout",
        "canceled",  # double-L, per chk_collector_run_status
    }  # type: ignore[arg-type]
)


# ---------------------------------------------------------------------------
# Callback replay guard set (subset of RUN_TERMINAL_STATUSES)
# ---------------------------------------------------------------------------
# P3: A callback arriving for an already-terminal run is normally a no-op
# replay (AWX retry storms, network blips). BUT — `failed` and
# `partial_success` are transient terminal states where a later callback
# may legitimately want to overwrite (e.g. the dispatcher marked
# partial_success, but a real `successful` callback arrives afterwards).
# Only reject replays for the states from which recovery is impossible.
CALLBACK_REPLAY_GUARD_STATUSES: Final[frozenset[RunTerminalStatus]] = frozenset(
    {
        "canceled",   # double-L, per chk_collector_run_status
        "timeout",
        "callback_failed",
    }  # type: ignore[arg-type]
)


# ---------------------------------------------------------------------------
# Running (non-terminal) dispatch statuses
# ---------------------------------------------------------------------------
# Used by the dispatch scheduler to count in-flight work for quota checks
# and by /collector/scheduler/status to surface running counts.
RUNNING_DISPATCH_STATUSES: Final[frozenset[str]] = frozenset({
    "launching",
    "launched",
    "running",
})


# ---------------------------------------------------------------------------
# AWX job terminal statuses (as reported by AWX `/api/v2/jobs/{id}/`)
# ---------------------------------------------------------------------------
# Mirrors AwxService.get_job_status's is_terminal computation. AWX emits
# both "canceled" (US) and "cancelled" (UK) for a cancelled job; accept both.
AWX_TERMINAL_STATUSES: Final[frozenset[AwxTerminalStatus]] = frozenset(
    {
        "successful",
        "failed",
        "error",
        "canceled",
        "cancelled",
    }  # type: ignore[arg-type]
)
