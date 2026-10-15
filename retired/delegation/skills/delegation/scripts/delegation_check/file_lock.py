"""Process locks using flock on POSIX and a fixed byte on Windows."""

from __future__ import annotations

import contextlib
import errno
import os
from pathlib import Path
import time
from typing import BinaryIO, Iterator

from . import DelegationError

if os.name == "nt":
    import msvcrt
else:
    import fcntl


def try_acquire(path: Path) -> BinaryIO | None:
    """Return a locked handle, or None on contention; propagate other errors."""
    handle = path.open("a+b")
    try:
        handle.seek(0)
        if os.name == "nt":
            # Windows permits locking beyond EOF, including an empty lock file.
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        handle.close()
        if error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
            return None
        raise
    except BaseException:
        handle.close()
        raise
    return handle


def release(handle: BinaryIO) -> None:
    """Unlock the same byte/descriptor and always close the handle."""
    try:
        if os.name == "nt":
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        handle.close()


@contextlib.contextmanager
def exclusive(path: Path, timeout: float | None = None) -> Iterator[None]:
    """Wait for an exclusive process lock without Windows' ten-retry limit."""
    started = time.monotonic()
    while True:
        handle = try_acquire(path)
        if handle is not None:
            break
        if timeout is not None and time.monotonic() - started >= timeout:
            raise DelegationError(f"lock still busy after {timeout:g}s: {path}")
        time.sleep(0.05)
    try:
        yield
    finally:
        release(handle)
