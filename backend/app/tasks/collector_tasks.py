"""Collector Celery tasks (Phase 3.4 P0-4 / P0-5).

These tasks are scheduled by Celery beat (see app.tasks.queue.beat_schedule).
They give DBOPS a single, central place to throttle and recover AWX jobs
so we can safely run 1000+ instances per batch.

Conventions
-----------
- Every task creates its own DB session via SessionLocal; long-running
  tasks must commit their own work and never hold a connection across
  network I/O.
- A scheduler tick is allowed to do partial work; leftover pending
  dispatches are picked up by the next tick.
- We use `with_for_update(skip_locked=True)` to avoid two workers
  launching the same dispatch at the same time.
"""
from __future__ import annotations

import enum
import logging
import time
from typing import Any

from sqlalchemy import func

from app.utils.datetime import now_local

from app.config import get_settings
from app.constants import RUNNING_DISPATCH_STATUSES
from app.database import SessionLocal
from app.models.dbops_assets import (
    CollectorBatchRun,
    CollectorDispatchRun,
    CollectorRun,
    CollectorRunItem,
)
from app.services.awx_service import AwxService, AwxServiceError
from app.services.batch_collector_service import BatchCollectorService
from app.tasks.queue import celery

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# P0-4: dispatch scheduler
# ----------------------------------------------------------------------


_RUNNING_DISPATCH_STATUSES = tuple(RUNNING_DISPATCH_STATUSES)


def _precompute_running_counts(db) -> tuple[dict[str, int], dict[str, int], dict[int, int], int]:
    """Single GROUP BY query to feed the per-scope quota checks.

    Returns:
        ig_running: {awx_instance_group → running count}
        nz_running: {network_zone → running count}
        batch_running: {batch_run_id → running count}
        global_running: sum of all running dispatches
    """
    rows = (
        db.query(
            CollectorDispatchRun.awx_instance_group,
            CollectorDispatchRun.network_zone,
            CollectorDispatchRun.batch_run_id,
            func.count(CollectorDispatchRun.id),
        )
        .filter(CollectorDispatchRun.status.in_(_RUNNING_DISPATCH_STATUSES))
        .group_by(
            CollectorDispatchRun.awx_instance_group,
            CollectorDispatchRun.network_zone,
            CollectorDispatchRun.batch_run_id,
        )
        .all()
    )
    ig_running: dict[str, int] = {}
    nz_running: dict[str, int] = {}
    batch_running: dict[int, int] = {}
    global_running = 0
    for ig, nz, batch_id, count in rows:
        c = int(count)
        global_running += c
        if ig:
            ig_running[ig] = ig_running.get(ig, 0) + c
        if nz:
            nz_running[nz] = nz_running.get(nz, 0) + c
        if batch_id is not None:
            batch_running[int(batch_id)] = batch_running.get(int(batch_id), 0) + c
    return ig_running, nz_running, batch_running, global_running


def _quota_check(
    dispatch: CollectorDispatchRun,
    settings,
    *,
    global_running: int,
    batch_running: int,
    ig_running: int,
    nz_running: int,
) -> tuple[bool, str]:
    """Return (allowed, reason) for a single dispatch under the per-scope
    concurrency limits configured in app.config.Settings.

    Counts are precomputed by the caller via _precompute_running_counts;
    this avoids N+1 COUNT queries in the dispatcher loop.
    """
    if global_running >= settings.COLLECTOR_GLOBAL_MAX_RUNNING_DISPATCHES:
        return False, f"global cap reached ({global_running})"
    if (
        dispatch.batch_run_id is not None
        and batch_running >= settings.COLLECTOR_BATCH_MAX_RUNNING_DISPATCHES
    ):
        return False, f"batch cap reached ({batch_running})"
    if (
        dispatch.awx_instance_group
        and ig_running >= settings.COLLECTOR_IG_MAX_RUNNING_DISPATCHES
    ):
        return False, f"ig cap reached ({ig_running})"
    if (
        dispatch.network_zone
        and nz_running >= settings.COLLECTOR_NETWORK_ZONE_MAX_RUNNING_DISPATCHES
    ):
        return False, f"network_zone cap reached ({nz_running})"
    return True, ""


class LaunchOutcome(str, enum.Enum):
    """Outcome of a single dispatch launch attempt.

    I1: distinguish "actually launched" from "permanent data error" so the
    scheduler summary['launched'] counter does not over-count failures.
    """
    LAUNCHED = "launched"
    DATA_ERROR = "data_error"          # missing collector_run FK row
    AWX_ERROR = "awx_error"            # AwxService.launch_job raised


def _launch_one_dispatch(db, dispatch: CollectorDispatchRun) -> LaunchOutcome:
    """Try to launch a single dispatch. Returns a LaunchOutcome.

    Failure here is non-fatal — we mark the dispatch as failed and let the
    callback path / user see the error. Concurrent beats are protected by
    skip_locked on the SELECT, plus the dispatcher_scheduler_task
    pg_advisory_xact_lock (C1).
    """
    dispatch.status = "launching"
    db.flush()

    collector_run = (
        db.query(CollectorRun)
        .filter(CollectorRun.id == dispatch.collector_run_id)
        .first()
    )
    if collector_run is None:
        dispatch.status = "failed"
        dispatch.error_message = "dispatch has no collector_run"
        dispatch.finished_at = now_local()
        db.commit()
        return LaunchOutcome.DATA_ERROR

    extra_vars = collector_run.extra_vars if collector_run.extra_vars else {"items": []}
    credential_ids = BatchCollectorService._extract_credential_ids(extra_vars)

    try:
        result = AwxService.launch_job(
            extra_vars=extra_vars,
            credentials=credential_ids or None,
        )
    except (AwxServiceError, RuntimeError) as exc:
        logger.warning(
            "scheduler launch failed: dispatch_id=%s error=%s",
            dispatch.id,
            exc,
        )
        dispatch.status = "failed"
        dispatch.error_message = str(exc)
        dispatch.finished_at = now_local()
        if collector_run is not None:
            collector_run.status = "failed"
            collector_run.error_message = str(exc)
            collector_run.finished_at = now_local()
        db.commit()
        return LaunchOutcome.AWX_ERROR

    dispatch.status = "launched"
    dispatch.awx_job_id = result.get("awx_job_id")
    dispatch.awx_job_template_id = result.get("awx_job_template_id")
    dispatch.launched_at = now_local()

    if collector_run is not None:
        collector_run.status = "launched"
        collector_run.awx_job_id = result.get("awx_job_id")
        collector_run.awx_job_url = result.get("awx_job_url")
        collector_run.awx_job_template_id = result.get("awx_job_template_id")
        collector_run.awx_job_template_name = result.get("awx_job_template_name")
        collector_run.started_at = now_local()

    db.commit()
    return LaunchOutcome.LAUNCHED


@celery.task(name='app.tasks.collector_tasks.dispatch_scheduler_task')
def dispatch_scheduler_task() -> dict[str, Any]:
    """Pick up pending dispatches and launch them under the configured caps.

    Returns a small summary dict for log/metrics — Celery discards it by
    default but it's handy when invoking this from a REPL.
    """
    settings = get_settings()
    qps = float(settings.COLLECTOR_AWX_LAUNCH_QPS or 0.0)
    min_interval = (1.0 / qps) if qps > 0 else 0.0

    summary: dict[str, Any] = {
        "considered": 0,
        "launched": 0,
        "skipped_cap": 0,
        "skipped_error": 0,
    }

    # C1 v2: pg_try_advisory_lock (session-level, non-blocking) + explicit
    # unlock. The lock key 0x434F4C4C = 'COLL' namespaces the collector
    # scheduler. v2 differences from the original xact-lock approach:
    #
    #  (a) session-level lock (not xact-level): survives per-dispatch
    #      db.commit() calls inside _launch_one_dispatch, so the entire
    #      tick is protected.
    #  (b) non-blocking (pg_try_*): a second worker that arrives while
    #      another tick is in-flight immediately returns with
    #      "scheduler_already_running" instead of queuing behind the lock.
    #  (c) explicit unlock in finally: QueuePool returns connections to
    #      the pool on Session.close() but does NOT close the underlying
    #      PG connection. Without an explicit unlock the advisory lock
    #      would leak to the next worker that happens to draw the same
    #      pooled connection.
    from sqlalchemy import text
    LOCK_KEY = 0x434F4C4C  # 'COLL'
    acquired = False
    db = SessionLocal()
    try:
        acquired = bool(
            db.execute(
                text("SELECT pg_try_advisory_lock(:k)"),
                {"k": LOCK_KEY},
            ).scalar()
        )
        # Commit the lock acquisition as its own micro-transaction so the
        # SELECT FOR UPDATE later in this tick starts in a fresh tx.
        db.commit()

        if not acquired:
            logger.info("dispatch scheduler skipped: another tick holds the lock")
            return {"detail": "scheduler_already_running", "considered": 0}

        # Pre-compute running-dispatch counts in one GROUP BY query
        # (avoids N+1 COUNT queries in the per-candidate loop).
        ig_running_map, nz_running_map, batch_running_map, global_running = (
            _precompute_running_counts(db)
        )

        # Enumerate candidate IDs WITHOUT holding a long-running SELECT FOR
        # UPDATE. We re-select each row inside the loop with skip_locked=True
        # so the lock window is one row at a time — _launch_one_dispatch
        # commits inside its own work, releasing that row's lock before the
        # next iteration. This prevents a single long tick (QPS-throttled,
        # AWX HTTP call) from holding 64 row locks at once and lets other
        # workers make progress concurrently.
        candidate_ids = [
            row.id
            for row in (
                db.query(CollectorDispatchRun.id)
                .filter(CollectorDispatchRun.status == "pending")
                .order_by(
                    CollectorDispatchRun.batch_run_id.asc(),
                    CollectorDispatchRun.id.asc(),
                )
                .limit(64)
                .all()
            )
        ]

        for dispatch_id in candidate_ids:
            summary["considered"] += 1
            try:
                dispatch = (
                    db.query(CollectorDispatchRun)
                    .filter(
                        CollectorDispatchRun.id == dispatch_id,
                        CollectorDispatchRun.status == "pending",
                    )
                    .with_for_update(skip_locked=True)
                    .first()
                )
                if dispatch is None:
                    # Another worker grabbed it, or it transitioned out of
                    # pending between enumeration and lock acquisition.
                    continue
                ig_running = (
                    ig_running_map.get(dispatch.awx_instance_group, 0)
                    if dispatch.awx_instance_group
                    else 0
                )
                nz_running = (
                    nz_running_map.get(dispatch.network_zone, 0)
                    if dispatch.network_zone
                    else 0
                )
                batch_running = (
                    batch_running_map.get(int(dispatch.batch_run_id), 0)
                    if dispatch.batch_run_id is not None
                    else 0
                )
                allowed, reason = _quota_check(
                    dispatch,
                    settings,
                    global_running=global_running,
                    batch_running=batch_running,
                    ig_running=ig_running,
                    nz_running=nz_running,
                )
                if not allowed:
                    summary["skipped_cap"] += 1
                    logger.debug("dispatch %s throttled: %s", dispatch.id, reason)
                    db.rollback()  # release the FOR UPDATE lock
                    # don't break — other batches may still have room
                    continue
                # I1: bucket the outcome so the summary counter does not
                # over-report. The previous implementation counted every
                # return-True as a "launched" success even when the actual
                # launch failed (data error / AWX error) and the dispatch
                # was marked failed.
                outcome = _launch_one_dispatch(db, dispatch)
                if outcome is LaunchOutcome.LAUNCHED:
                    summary["launched"] += 1
                elif outcome is LaunchOutcome.DATA_ERROR:
                    summary["skipped_data_error"] = (
                        summary.get("skipped_data_error", 0) + 1
                    )
                elif outcome is LaunchOutcome.AWX_ERROR:
                    summary["skipped_awx_error"] = (
                        summary.get("skipped_awx_error", 0) + 1
                    )
                else:
                    # A new LaunchOutcome was added without updating this
                    # dispatcher. Log loudly so the regression is visible
                    # in production logs (do NOT silently fold into
                    # skipped_error — that masks the contract drift).
                    logger.error(
                        "dispatch_scheduler_tick: unmapped LaunchOutcome %r "
                        "(dispatch_id=%s); incrementing skipped_error as "
                        "fallback. Update collector_tasks.py dispatcher.",
                        outcome,
                        dispatch.id,
                    )
                    summary["skipped_error"] += 1
                # The launch may have flipped a dispatch from pending→launching;
                # bump the relevant counters so sibling candidates in the same
                # tick are checked against fresh values.
                global_running += 1
                if dispatch.awx_instance_group:
                    ig_running_map[dispatch.awx_instance_group] = ig_running + 1
                if dispatch.network_zone:
                    nz_running_map[dispatch.network_zone] = nz_running + 1
                if dispatch.batch_run_id is not None:
                    batch_running_map[int(dispatch.batch_run_id)] = batch_running + 1
            except Exception as exc:  # noqa: BLE001
                summary["skipped_error"] += 1
                db.rollback()  # critical: release lock and clear poisoned txn
                logger.exception(
                    "dispatch_scheduler unexpected error dispatch_id=%s: %s",
                    dispatch_id,
                    exc,
                )
            if min_interval > 0:
                time.sleep(min_interval)

        # Refresh all affected batch statuses in one go.
        affected_batch_ids: set[int] = set()
        for batch_id in (
            db.query(CollectorDispatchRun.batch_run_id)
            .filter(
                CollectorDispatchRun.id.in_(candidate_ids),
                CollectorDispatchRun.batch_run_id.isnot(None),
            )
            .distinct()
            .all()
        ):
            if batch_id[0] is not None:
                affected_batch_ids.add(int(batch_id[0]))
        for batch_id in affected_batch_ids:
            try:
                BatchCollectorService.refresh_batch_status(db, batch_id)
            except Exception:  # noqa: BLE001
                logger.exception("refresh_batch_status failed for batch_id=%s", batch_id)
                db.rollback()
    finally:
        if acquired:
            try:
                # Release the lock in its own micro-transaction so it
                # commits independent of any prior in-flight work.
                db.rollback()
                unlocked = bool(
                    db.execute(
                        text("SELECT pg_advisory_unlock(:k)"),
                        {"k": LOCK_KEY},
                    ).scalar()
                )
                db.commit()
                if not unlocked:
                    logger.warning(
                        "dispatch scheduler advisory lock not held at unlock (leaked?)"
                    )
            except Exception:
                db.rollback()
                logger.exception(
                    "advisory lock unlock failed; lock will release on conn close"
                )
        db.close()

    if any(summary.values()):
        logger.info("dispatch_scheduler_tick: %s", summary)
    return summary


# ----------------------------------------------------------------------
# P0-5: timeout recovery
# ----------------------------------------------------------------------


from app.constants import AWX_TERMINAL_STATUSES as _TIMEOUT_TERMINAL_AWX


@celery.task(name='app.tasks.collector_tasks.timeout_recovery_task')
def timeout_recovery_task() -> dict[str, Any]:
    """Find collector_runs that exceeded COLLECTOR_RUN_TIMEOUT_MINUTES and:

    1. ask AWX for the current job status;
    2. if the AWX job is still running, mark the local run as `timeout`
       (it is no longer expected to callback — the operator can re-run it);
    3. if the AWX job is already terminal, leave the run alone: the
       callback should arrive shortly and the existing post-process will
       converge.
    """
    settings = get_settings()
    timeout_minutes = int(settings.COLLECTOR_RUN_TIMEOUT_MINUTES or 30)

    summary = {
        "considered": 0,
        "recovered": 0,
        "skipped_running_in_awx": 0,
    }

    from app.constants import RUN_TERMINAL_STATUSES, DISPATCH_TERMINAL_STATUSES

    db = SessionLocal()
    try:
        # I3 v2: enumerate candidate IDs WITHOUT holding FOR UPDATE locks,
        # then re-select each row one-at-a-time with skip_locked so a
        # parallel tick or callback writer is not blocked. Also re-check
        # run.status under the lock — a callback may have finalized it
        # between enumeration and lock acquisition.
        candidate_ids = [
            row.id
            for row in (
                db.query(CollectorRun.id)
                .filter(
                    CollectorRun.status.in_(["pending", "launched", "running"]),
                    CollectorRun.awx_job_id.isnot(None),
                    CollectorRun.started_at.isnot(None),
                    CollectorRun.started_at
                    < func.now() - func.make_interval(0, 0, 0, 0, 0, int(timeout_minutes), 0),
                )
                .limit(50)
                .all()
            )
        ]

        for run_id in candidate_ids:
            run = (
                db.query(CollectorRun)
                .filter(CollectorRun.id == run_id)
                .with_for_update(skip_locked=True)
                .first()
            )
            if run is None:
                # Another worker grabbed it, or it transitioned out of
                # pending between enumeration and lock acquisition.
                continue
            # I3 v2: use RUN_TERMINAL_STATUSES (canceled double-L), not
            # BATCH_TERMINAL_STATUSES (cancelled single-L). run.status
            # uses US spelling per chk_collector_run_status.
            if (run.status or "").lower() in RUN_TERMINAL_STATUSES:
                # Callback (or other) already finalized while we waited.
                continue
            summary["considered"] += 1
            try:
                awx_status = AwxService.get_job_status(int(run.awx_job_id))
            except AwxServiceError as exc:
                # I4: release this row's lock so a parallel tick can retry.
                # Without rollback the FOR UPDATE lock persists until the
                # next commit/close, blocking other workers.
                db.rollback()
                logger.warning(
                    "timeout_recovery awx_status failed: run_id=%s err=%s",
                    run.run_id,
                    exc,
                )
                continue

            if not awx_status.get("is_terminal"):
                # AWX still says running — respect that. Don't mark timeout
                # unless we believe the job is stuck.
                summary["skipped_running_in_awx"] += 1
                continue

            # The job is done in AWX but never called us back. Map the AWX
            # status to the local run status so a job that finished
            # `successful` in AWX is not labelled `timeout` locally. Only
            # unknown / unexpected AWX terminal states fall through to
            # `timeout` (the legacy behaviour).
            awx_final = (awx_status.get("status") or "").lower()
            if awx_final == "successful":
                run.status = "success"
            elif awx_final in ("failed", "error"):
                run.status = "failed"
            elif awx_final in ("canceled", "cancelled"):
                run.status = "canceled"
            else:
                run.status = "timeout"
            run.error_message = (
                f"AWX job {run.awx_job_id} reached terminal state "
                f"({awx_status.get('status')}) but no callback was received "
                f"within {timeout_minutes} minutes."
            )
            run.finished_at = now_local()
            if run.dispatch_run_id is not None:
                dispatch = (
                    db.query(CollectorDispatchRun)
                    .filter(CollectorDispatchRun.id == run.dispatch_run_id)
                    .with_for_update(skip_locked=True)
                    .first()
                )
                if dispatch is not None:
                    # A2: use the canonical DISPATCH_TERMINAL_STATUSES constant
                    # (subtract "timeout" — a dispatch we are about to mark
                    # timeout should not be skipped because it merely happens
                    # to be in the terminal set). All other terminal states
                    # (success, failed, cancelled, callback_failed, etc.)
                    # are genuinely terminal and must not be clobbered.
                    _dispatch_terminal = DISPATCH_TERMINAL_STATUSES - {"timeout"}
                    current = (dispatch.status or "").lower()
                    if current in _dispatch_terminal:
                        logger.info(
                            "timeout_recovery skipping dispatch_id=%s already in terminal status=%s",
                            dispatch.id,
                            current,
                        )
                    else:
                        dispatch.status = "timeout"
                        dispatch.error_message = run.error_message
                        dispatch.finished_at = now_local()
            if run.batch_run_id is not None:
                BatchCollectorService.refresh_batch_status(db, int(run.batch_run_id))
            summary["recovered"] += 1
        db.commit()
    finally:
        db.close()

    if any(summary.values()):
        logger.info("timeout_recovery_tick: %s", summary)
    return summary
