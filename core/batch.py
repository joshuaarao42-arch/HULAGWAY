from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Sequence

from .image_ops import ProcessOptions, ProcessResult, process_image


@dataclass
class BatchSummary:
    results: list = field(default_factory=list)
    total: int = 0
    succeeded: int = 0
    skipped: int = 0
    failed: int = 0
    cancelled: int = 0
    orig_bytes: int = 0       # successful files only
    new_bytes: int = 0
    elapsed: float = 0.0
    was_cancelled: bool = False

    @property
    def saved_bytes(self) -> int:
        return self.orig_bytes - self.new_bytes

    @property
    def saved_pct(self) -> float:
        return (1 - self.new_bytes / self.orig_bytes) * 100 if self.orig_bytes else 0.0


def summarize(results: Sequence[ProcessResult], total: int, elapsed: float, cancelled: bool) -> BatchSummary:
    s = BatchSummary(results=list(results), total=total, elapsed=elapsed, was_cancelled=cancelled)
    for r in results:
        if r.status == "success":
            s.succeeded += 1
            s.orig_bytes += r.orig_size
            s.new_bytes += r.new_size
        elif r.status == "skipped":
            s.skipped += 1
        elif r.status == "failed":
            s.failed += 1
        elif r.status == "cancelled":
            s.cancelled += 1
    return s


class BatchProcessor:
    """Run process_image over many files on a background thread pool."""

    def __init__(self, max_workers: Optional[int] = None):
        self.max_workers = max(1, max_workers or min(4, os.cpu_count() or 2))
        self._cancel = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def cancel(self) -> None:
        self._cancel.set()

    def start(self, files: Sequence[Path], out_dir: Path, options: ProcessOptions,
              on_progress: Optional[Callable[[int, int, ProcessResult], None]] = None,
              on_finished: Optional[Callable[[BatchSummary], None]] = None) -> None:
        self._cancel.clear()
        self._thread = threading.Thread(
            target=self._run, args=(list(files), Path(out_dir), options, on_progress, on_finished),
            daemon=True, name="hulagway-batch")
        self._thread.start()

    def _run(self, files, out_dir, options, on_progress, on_finished) -> None:
        t0, total, results = time.perf_counter(), len(files), []
        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="pp-worker") as pool:
            futures = {pool.submit(process_image, f, out_dir, options, self._cancel): f for f in files}
            for done, fut in enumerate(as_completed(futures), start=1):
                try:
                    res = fut.result()
                except Exception as exc:  # noqa: BLE001
                    res = ProcessResult(src=futures[fut], status="failed", error=str(exc))
                results.append(res)
                if on_progress:
                    try:
                        on_progress(done, total, res)
                    except Exception:
                        pass
        summary = summarize(results, total, time.perf_counter() - t0, self._cancel.is_set())
        if on_finished:
            try:
                on_finished(summary)
            except Exception:
                pass
