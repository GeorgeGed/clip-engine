"""READ-MERGE-WRITE A SHARED JSON FILE, once at a time, atomically.

Three files in this pipeline are read whole, changed, and written whole:
`jobs/<job>/editorial.json`, `jobs/<job>/manifest.json` and a clip's spec.
Serial builds hid that. Two clips building at once — which is what George
asked for — makes every one of them a lost-update, and the manifest's worst
case is not a lost entry but a TRUNCATED FILE: a write interrupted part way
leaves JSON that `json.loads` refuses, so every later read of that job fails.

So two things, and neither is sufficient alone:

* an **`flock`** around read-merge-write, which makes the window atomic
  across processes — `batch.py` runs as a subprocess of the site, of the
  agent, and by hand, so a thread lock cannot see all the writers;
* **`os.replace`** off a temp path in the same directory, which is atomic on
  POSIX, so a reader never sees a half-written file even without the lock.
  This is the pattern the thumbnails already use.

**It is a DEDICATED lock file, deliberately.** `web/runlock.py`'s lock is
held for the life of the server process, so a child taking `LOCK_EX` on it
blocks forever and every build click would hang until its 180s timeout. And
its `take()` uses `LOCK_NB`, which DECLINES rather than waits — right for
"is another runner up", wrong for "wait your turn to append one entry".

Scope the lock as narrowly as the merge: never hold it across model calls or
a render. `cmd_editorial` makes 27 model calls; holding this through them
would serialise them behind an HTTP handler on a 180-second timeout.
"""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def locked(path: Path):
    """Hold an exclusive lock for `path`, in a sibling `.<name>.lock`.

    The lock is a separate file so it survives `os.replace` of the data —
    locking the data file itself would release the moment it was replaced.
    """
    path = Path(path)
    lf = path.with_name(f".{path.name}.lock")
    lf.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lf, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def write_atomic(path: Path, text: str) -> None:
    """Replace `path`'s contents in one step a reader cannot see half of."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def merge(path: Path, changes: dict, *, indent: int = 1,
          sort_keys: bool = False) -> dict:
    """Merge `changes` into the JSON object at `path` and return the result.

    The read and the write are one critical section: reading, changing and
    writing without the lock is exactly the lost update, and it is how a
    routine stage has eaten hand-tuned state four times in this repo.
    """
    path = Path(path)
    with locked(path):
        cur = json.loads(path.read_text()) if path.exists() else {}
        cur.update(changes)
        write_atomic(path, json.dumps(cur, indent=indent, sort_keys=sort_keys))
        return cur
