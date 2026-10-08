# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""Background worker for long file operations (move, .modelinfo dump).

The worker never touches GUI state and never reads tensor payloads. Move uses a
no-clobber ``safe_move`` that never overwrites an existing destination and never
moves a file into a nested directory. Dump reuses the existing ``back.reporting``
write routines, which read only model headers, never tensor data.
"""

from pathlib import Path
import errno
import os
import shutil

from PyQt6.QtCore import QThread, pyqtSignal

from back.reporting import write_modelinfo_dump, write_modelinfo_json


_SKIP_LABELS = {
    "skipped_same": "source and destination are the same path",
    "skipped_exists": "destination already exists",
}


class FileOperationWorker(QThread):
    """Run move or dump operations off the GUI thread with per-file progress.

    ``items`` is a list of ``(src, dst)`` tuples for ``mode="move"`` or a list
    of file paths for ``mode="dump"``.

    ``operation_done`` is emitted from ``run()`` for worker-level consumers;
    the owning controller must key its lifecycle off the terminal ``finished``
    signal (see ``FileOperationControllerMixin``) so the QThread is never
    released while it is still winding down.
    """

    progress_updated = pyqtSignal(dict)
    operation_done = pyqtSignal(dict)

    def __init__(
        self,
        mode: str,
        items,
        *,
        dump_json: bool = False,
        dump_options: dict | None = None,
    ):
        super().__init__()
        self.mode = mode  # "move" | "dump"
        self.items = list(items)
        self.dump_json = dump_json
        self.dump_options = dict(dump_options or {})
        self.result: dict = {}

    def cancel(self) -> None:
        """Request cooperative cancellation between files."""
        self.requestInterruption()

    def _cancelled(self) -> bool:
        return self.isInterruptionRequested()

    def run(self) -> None:
        try:
            if self.mode == "move":
                result = self._run_move()
            else:
                result = self._run_dump()
        except Exception as exc:  # noqa: BLE001 - terminal fallback, never crash the thread
            result = self._terminal_failure(str(exc))
        self.result = result
        self.operation_done.emit(result)

    def _terminal_failure(self, reason: str) -> dict:
        if self.mode == "move":
            return {
                "mode": "move",
                "moved": [],
                "skipped": [],
                "failed": [[src, reason] for src, _ in self.items],
                "cancelled": self._cancelled(),
            }
        return {
            "mode": "dump",
            "dumped": [],
            "failed": [[fp, reason] for fp in self.items],
            "cancelled": self._cancelled(),
        }

    def _run_move(self) -> dict:
        moved: list[str] = []
        skipped: list[list[str]] = []
        failed: list[list[str]] = []
        total = len(self.items)
        for index, (src, dst) in enumerate(self.items):
            if self._cancelled():
                break
            self.progress_updated.emit(
                {
                    "phase": "move",
                    "index": index,
                    "total": total,
                    "filename": Path(src).name,
                }
            )
            try:
                # ponytail: no byte-level copy progress; per-file indeterminate
                # is enough. Add a chunked cross-volume copy here if users need
                # byte granularity for very large multi-GB moves.
                status = safe_move(src, dst)
            except Exception as exc:  # noqa: BLE001 - report, never discard
                failed.append([src, str(exc)])
                continue
            if status == "moved":
                moved.append(src)
            else:
                skipped.append([src, _SKIP_LABELS.get(status, status)])
        return {
            "mode": "move",
            "moved": moved,
            "skipped": skipped,
            "failed": failed,
            "cancelled": self._cancelled(),
        }

    def _run_dump(self) -> dict:
        dumped: list[dict] = []
        failed: list[list[str]] = []
        total = len(self.items)
        for index, filepath in enumerate(self.items):
            if self._cancelled():
                break
            self.progress_updated.emit(
                {
                    "phase": "dump",
                    "index": index,
                    "total": total,
                    "filename": Path(filepath).name,
                }
            )
            try:
                outputs = [write_modelinfo_dump(filepath)]
                if self.dump_json:
                    outputs.append(
                        write_modelinfo_json(filepath, options=self.dump_options)
                    )
                dumped.append({"filepath": filepath, "outputs": outputs})
            except Exception as exc:  # noqa: BLE001 - report, never discard
                failed.append([filepath, str(exc)])
        return {
            "mode": "dump",
            "dumped": dumped,
            "failed": failed,
            "cancelled": self._cancelled(),
        }


def safe_move(src: str, dst: str) -> str:
    """Move ``src`` to ``dst`` without ever clobbering an existing destination.

    Returns ``"moved"``, ``"skipped_same"`` (source and destination resolve to
    the same path, a no-op that never removes the source), or
    ``"skipped_exists"`` (destination already exists, including a dangling
    symlink). Raises ``OSError`` on a genuine failure; a failed move preserves
    the source and removes only the reservation this call created.

    The ``lexists`` check below is only a fast path. The actual mutation is
    atomic and no-clobber, so a concurrent writer is never silently overwritten
    even if it creates the destination after that check:

    * Windows ``os.rename`` fails with ``FileExistsError`` when the destination
      exists (it never replaces).
    * POSIX ``os.rename`` *does* replace, so a same-device move uses
      ``os.link`` (atomic, no-clobber) then unlinks the source, and a
      cross-device move falls back to an ``O_EXCL`` copy.

    A symlink source is moved as a symlink: its target is re-created at ``dst``
    (``os.symlink`` is atomic no-clobber) and the source link is unlinked.
    """
    src = os.path.abspath(src)
    dst = os.path.abspath(dst)
    if os.path.normcase(src) == os.path.normcase(dst):
        return "skipped_same"
    # No-clobber fast path: an existing file OR directory is never overwritten,
    # so a directory destination can never swallow the source into a nested
    # directory the way ``shutil.move`` would.
    if os.path.lexists(dst):
        return "skipped_exists"
    try:
        _rename_no_clobber(src, dst)
        return "moved"
    except FileExistsError:
        # Lost the race: someone else created the destination after our check.
        return "skipped_exists"
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
    # Cross-device: reserve the destination exclusively, copy, then unlink the
    # source only after the copy fully succeeds.
    try:
        _copy_exclusive(src, dst)
    except FileExistsError:
        # Lost the race: someone else created the destination after our check.
        return "skipped_exists"
    try:
        os.unlink(src)
    except BaseException:
        # Remove only our own reservation; the source is preserved on failure.
        _unlink_quiet(dst)
        raise
    return "moved"


def _rename_no_clobber(src: str, dst: str) -> None:
    """Atomically move ``src`` to ``dst`` without replacing an existing ``dst``.

    Windows ``os.rename`` is already atomic no-clobber. POSIX ``os.rename``
    silently replaces an existing destination (the historical data-loss
    shortcut), so a same-device move uses ``os.link`` (atomic; raises
    ``FileExistsError`` on collision and ``EXDEV`` across devices) followed by
    ``os.unlink`` of the source. Symlink sources re-create their target at
    ``dst``; on failure only the reservation this call created is removed.
    """
    if os.name == "nt":
        os.rename(src, dst)
        return
    if os.path.islink(src):
        _copy_symlink_exclusive(src, dst)
        try:
            os.unlink(src)
        except BaseException:
            _unlink_quiet(dst)
            raise
        return
    os.link(src, dst)
    try:
        os.unlink(src)
    except BaseException:
        _unlink_quiet(dst)
        raise


def _copy_exclusive(src: str, dst: str) -> None:
    """Copy ``src`` to ``dst`` under an atomic exclusive destination reservation.

    The destination is created with ``O_CREAT | O_EXCL`` so a concurrent writer
    can never be silently overwritten. On any failure the partially written
    destination (our own reservation) is removed and the source is untouched.
    """
    if os.path.islink(src):
        _copy_symlink_exclusive(src, dst)
        return
    fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    try:
        with os.fdopen(fd, "wb") as out, open(src, "rb") as inp:
            shutil.copyfileobj(inp, out)
    except BaseException:
        _unlink_quiet(dst)
        raise


def _copy_symlink_exclusive(src: str, dst: str) -> None:
    """Re-create a symlink source at ``dst``; ``os.symlink`` is atomic no-clobber.

    ``os.symlink`` either creates the link or fails without creating anything,
    so no cleanup is needed on failure. Never unlink here: a concurrent
    writer's destination must not be removed.
    """
    target = os.readlink(src)
    os.symlink(target, dst)


def _unlink_quiet(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
