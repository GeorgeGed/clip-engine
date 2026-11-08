"""The pipeline chain is defined in THREE places and they drifted.

`editorial` is the stage that decides where a clip starts and what it is
called; `specs` only copies that decision across. It was added to the web
server's chain and to nothing else, so:

* `worker/agent.py` had no command for it. `worker/backend.py` derives the
  stage LIST from `web/server.py`'s ALL_STAGES, so a claimed job would hand
  `editorial` to `run_stage()` and KeyError on a dict that had never heard of
  it;
* `worker/schema.sql`'s default `stages_remaining` omitted it, so any job
  created in the control plane would skip the judging pass outright and every
  clip would be written with `in_point 0.0` — the top of the candidate region,
  an acoustic cluster boundary and not where the argument starts. That is
  George's "the clip starts too early", reintroduced one runner over.

Both were silent. This file is the gate, and it fails against the code as it
stood before: remove `"editorial"` from STAGE_ARGV and `test_every_stage_has_a_command`
fails; drop it from the SQL default and `test_sql_default_matches_the_chain`
fails.

The repo's most-repeated defect is two numbers that are supposed to be the
same number, derived twice. A chain is the same thing with four values.
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

import server as site          # noqa: E402  web/server.py
sys.path.insert(0, str(ROOT / "worker"))
import agent                   # noqa: E402  worker/agent.py

CHAIN = [s.key for s in site.ALL_STAGES]
FAILURES: list[str] = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not cond:
        FAILURES.append(name)


def test_every_stage_has_a_command():
    """The agent runs whatever the backend hands it, and the backend hands it
    ALL_STAGES. A stage with no argv is a KeyError mid-job, after the
    expensive stages have already run."""
    missing = [k for k in CHAIN if k not in agent.STAGE_ARGV]
    check("every stage in the chain has an agent command", not missing,
          f"missing: {missing}" if missing else f"{len(CHAIN)} stages")
    extra = [k for k in agent.STAGE_ARGV if k not in CHAIN]
    check("the agent has no command for a stage not in the chain", not extra,
          f"orphaned: {extra}" if extra else "")


def test_editorial_runs_before_specs():
    """`specs` reads each clip's in-point and hook out of editorial.json. In
    the other order it reads a file that does not exist yet and writes
    placeholders, which is the defect."""
    for where, keys in (("the chain", CHAIN),
                        ("the agent's commands", list(agent.STAGE_ARGV))):
        ok = ("editorial" in keys and "specs" in keys
              and keys.index("editorial") < keys.index("specs"))
        check(f"editorial before specs in {where}", ok, " -> ".join(keys))


def test_build_is_last_and_the_only_resolve_stage():
    """Everything that can fail cheaply has to fail before Resolve starts, or
    a VOD dropped with Resolve closed transcribes for an hour and then dies."""
    needs = set(agent.NEEDS_RESOLVE)
    check("build is the only Resolve stage", needs == {"build"}, str(needs))
    before = [k for k in CHAIN if k not in ("build", "report")]
    check("nothing that needs Resolve runs before the cheap stages",
          all(CHAIN.index(n) > max(CHAIN.index(b) for b in before) for n in needs),
          f"build at {CHAIN.index('build')} of {len(CHAIN)}")


def test_sql_default_matches_the_chain():
    """`stages_remaining` is what a fresh row in the control plane will run.
    It is the same list as ALL_STAGES and must be derived from it by hand
    only once — so compare them rather than trusting that it was."""
    sql = (ROOT / "worker" / "schema.sql").read_text()
    m = re.search(r"stages_remaining[^=]*default\s+array\[(.*?)\]", sql, re.S)
    check("schema.sql declares a stages_remaining default", bool(m))
    if not m:
        return
    got = re.findall(r"'([a-z_]+)'", m.group(1))
    check("the SQL default is the chain, in order", got == CHAIN,
          f"sql={got}\n            chain={CHAIN}")


def test_stage_commands_name_a_real_batch_subcommand():
    """A typo'd subcommand is an argparse exit 2 the agent reports as a bare
    exit code, with the real reason only in the stage log."""
    batch = (ROOT / "batch.py").read_text()
    m = re.search(r'ap\.add_argument\("cmd",\s*choices=\[(.*?)\]', batch, re.S)
    check("batch.py declares its subcommands", bool(m))
    if not m:
        return
    known = set(re.findall(r'"([a-z_]+)"', m.group(1)))
    # argv is (script, "{job}", subcommand, ...)
    bad = [(k, v[2]) for k, v in agent.STAGE_ARGV.items()
           if v[0] == "batch.py" and v[2] not in known]
    check("every batch.py stage names a real subcommand", not bad, str(bad))


if __name__ == "__main__":
    print(__doc__.strip().splitlines()[0])
    print()
    for fn in (test_every_stage_has_a_command,
               test_editorial_runs_before_specs,
               test_build_is_last_and_the_only_resolve_stage,
               test_sql_default_matches_the_chain,
               test_stage_commands_name_a_real_batch_subcommand):
        print(fn.__name__)
        fn()
        print()
    if FAILURES:
        sys.exit(f"{len(FAILURES)} failed: {FAILURES}")
    print("all stage-chain checks pass")
