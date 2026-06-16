"""Application-wide constants.

Single source of truth for sets of statuses, status spellings, and other
enumerated values that were previously inlined in 3-4 places (C4).
"""
from __future__ import annotations

from typing import Final


# ---------------------------------------------------------------------------
# Dispatch / batch terminal status sets
# ---------------------------------------------------------------------------
# These match the values allowed by:
#   chk_collector_batch_run_status    (dbops_assets.py CheckConstraint)
#   chk_collector_dispatch_run_status (dbops_assets.py CheckConstraint)
# Adding a new terminal status: update DB CHECK first, then update this set.
BATCH_TERMINAL_STATUSES: Final[frozenset[str]] = frozenset({
    "success",
    "partial_success",
    "failed",
    "timeout",
    "callback_failed",
    "cancelled",
})
# Dispatch and batch share the same set; alias for clarity at call sites.
DISPATCH_TERMINAL_STATUSES: Final[frozenset[str]] = BATCH_TERMINAL_STATUSES


# ---------------------------------------------------------------------------
# CollectorRun terminal status set
# ---------------------------------------------------------------------------
# NB: collector_run.status uses the US spelling "canceled" (double L) per
# the phase 2 refactor schema, while batch_run / dispatch_run use "cancelled"
# (single L). Do not mix spellings — this set is ONLY compared against
# CollectorRun.status.
RUN_TERMINAL_STATUSES: Final[frozenset[str]] = frozenset({
    "success",
    "failed",
    "partial_success",
    "callback_failed",
    "timeout",
    "canceled",  # double-L, per chk_collector_run_status
})


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
AWX_TERMINAL_STATUSES: Final[frozenset[str]] = frozenset({
    "successful",
    "failed",
    "error",
    "canceled",
    "cancelled",
})
