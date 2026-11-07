"""One runner per machine, enforced rather than arranged.

`web/server.py` runs jobs in its own worker thread and `worker/agent.py`
runs them from a queue, and against the local SQLite BOTH are runners: the
site puts a job on its in-process queue AND leaves the row at
`state='queued'`, which is exactly what the agent claims. Start both and two
processes drive one Resolve.

That is not a race to be narrowed, it is the invariant this whole pipeline
rests on — the API is served on Resolve's GUI thread, and `public/` is
shared. So it is a lock, taken by whichever runner starts first and held for
the life of the process. `flock` releases on exit however the process dies,
including a kill -9, which a pid file does not.
"""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

LOCK = Path(__file__).resolve().parent / ".runner.lock"


class Held(Exception):
    """Another runner has it. Carries what little the holder wrote down."""


def take(who: str):
    """Take the lock, or raise `Held`. Returns the fd — keep a reference to
    it for as long as you mean to hold it, or it closes and lets go."""
    fh = LOCK.open("a+")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.seek(0)
        other = fh.read().strip() or "another process"
        fh.close()
        raise Held(other) from None
    fh.seek(0)
    fh.truncate()
    fh.write(f"{who} (pid {os.getpid()})")
    fh.flush()
    return fh
