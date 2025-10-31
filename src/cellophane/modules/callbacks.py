"""Callbacks for runners and hooks executed as jobs"""

import time
from functools import partial
from logging import LoggerAdapter, getLogger
from multiprocessing import Queue
from multiprocessing.synchronize import Lock as LockType
from pathlib import Path
from typing import Sequence
from uuid import UUID

from mpire import WorkerPool

from cellophane.cfg import Config
from cellophane.cleanup import Cleaner, DeferredCleaner
from cellophane.data import Samples
from cellophane.executors import Executor
from cellophane.logs import handle_warnings, redirect_logging_to_queue
from cellophane.util import Timestamp

from .hook import Hook, run_hooks


def _run_per_sample_hooks(
    log_queue: Queue,
    *,
    log_label: str,
    hooks: Sequence[Hook],
    samples: Samples,
    config: Config,
    root: Path,
    executor_cls: type[Executor],
    timestamp: Timestamp,
) -> tuple[Samples, DeferredCleaner]:
    handle_warnings()
    redirect_logging_to_queue(log_queue)
    logger = LoggerAdapter(getLogger(), {"label": log_label})
    cleaner = DeferredCleaner(root=root)

    _samples = run_hooks(
        hooks,
        when="post",
        per="sample",
        samples=samples,
        config=config,
        root=root,
        executor_cls=executor_cls,
        log_queue=log_queue,
        timestamp=timestamp,
        cleaner=cleaner,
        logger=logger,
        checkpoint_suffix=f"sample_{samples[0].id}"
    )

    return _samples, cleaner


def _hook_callback(
    result: tuple[Samples, DeferredCleaner],
    *,
    samples: Samples,
    logger: LoggerAdapter,
    cleaner: Cleaner,
) -> None:
    try:
        cleaner &= result[1]
    except Exception as exc:
        logger.error(f"Exception when merging cleaners: {exc!r}", exc_info=True)

    samples |= result[0]



def runner_callback(
    result: tuple[Samples, DeferredCleaner],
    *,
    logger: LoggerAdapter,
    samples: Samples,
    cleaner: Cleaner,
    pool: WorkerPool,
    sample_runner_count: dict[UUID, int],
    sample_locks: dict[UUID, LockType],
    hooks: Sequence[Hook],
    config: Config,
    root: Path,
    executor_cls: type[Executor],
    timestamp: time.struct_time,
    lock: LockType,
) -> None:
    try:
        cleaner &= result[1]
    except Exception as exc:
        logger.error(f"Exception when merging cleaners: {exc!r}", exc_info=True)

    if len(samples) == 0:
        # No samples have been returned yet, so do an in-place copy of the result samples into 'samples'
        samples ^= result[0]
    else:
        try:
            samples &= result[0]
        except Exception as exc:
            _msg = f"Exception when merging samples: {exc!r}"
            logger.error(_msg, exc_info=True)
            for sample in result[0]:
                if sample.uuid not in samples:
                    samples.append(sample)
                samples[sample.uuid].fail(_msg)

    for uuid, sample in ((u, s) for u, s in samples.split() if u in result[0]):
        with sample_locks[uuid]:
            sample_runner_count[uuid] -= 1
            if sample_runner_count[uuid] != 0:
                continue  # Wait for other runners to finish for this sample

        pool.apply_async(
            _run_per_sample_hooks,
            kwargs={
                "log_label": (logger.extra or {"label": "cellophane"})["label"],
                "hooks": hooks,
                "samples": sample,
                "config": config,
                "root": root,
                "executor_cls": executor_cls,
                "timestamp": timestamp,
            },
            callback=partial(
                _hook_callback,
                samples=samples,
                logger=logger,
                cleaner=cleaner,
            )
        )
    lock.release()