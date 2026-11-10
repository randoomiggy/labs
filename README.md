# Engineering Practice

Small, reproducible engineering exercises and, later, operational labs. The goals
are personal learning and a credible job-search portfolio—not a contribution
streak or a claim of production experience. Code and documentation are AI-assisted;
passing tests or approving a commit does not establish the user's understanding.

## Start here: EP-001

[EP-001: streaming synthetic HTTP log summary](practice/ep001_log_summary/README.md)
contains the implementation, tests, and a detailed Russian walkthrough of the code
and this project's structure. It processes a single-pass iterable, counts valid
and malformed records, and returns sparse integer-keyed HTTP status counts.
It is an original exercise, not an Apache/nginx parser or a production monitor.

From the repository root:

```sh
python3 -c 'from practice.ep001_log_summary.solution import summarize; print(summarize(["0 GET /health 200", "1 POST /jobs 503", "not a record", "2 GET /health 200"]))'
python3 -m unittest discover -s practice/ep001_log_summary -v
make test-all
```

Python 3.11+ and the standard library are sufficient for the exercise. Workflow
helpers require Git and a POSIX host. Checks are exercised on Linux/CPython 3.14;
the exercise suite also passes on CPython 3.11. Other versions/platforms are not
verified. No package installation is needed.

## Layout

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | Durable project and agent policy |
| `docs/WORKFLOW.md` | Preparation, evidence, live review, publication gates |
| `docs/DECISIONS.md` | Accepted decisions and open choices |
| `ROADMAP.md` / `BACKLOG.json` | Proposed progression / ordered seed queue |
| `templates/task.md` | Complete task-card template |
| `practice/ep001_log_summary/` | EP-001 source, tests, and detailed walkthrough |
| `practice/` / `labs/` | Small exercises / later operational labs |
| `tools/workflow.py` | Immutable snapshots, test evidence, serial approval gate |
| `tools/unittest_driver.py` | Structured counters after normal test completion |
| `tools/daily_gate.py` | Read-only scheduler pre-check; suppresses blocked ticks |
| `tools/report_export.py` | Separate best-effort redacted report exports |
| `tests/` | Workflow, scheduler gate, and export regression tests |
| `.local/` | Gitignored private snapshots, state, and raw evidence |

`BACKLOG.json` contains a proposed seed track, not completed work or proven
mastery. EP-002 and later proposals are not applied merely because they exist
in private drafts. Larger labs and CI/IaC are proposals in `ROADMAP.md`.
No software license has been selected; there is no `LICENSE` file.

## Local checks

```sh
make test        # workflow/gate/export tests
make test-ep001  # exercise tests
make test-all    # both suites; failure in either is fatal
make status     # private local proposal state
make next       # read-only selection, including blockers
```

Each reviewable payload also needs its own actual, nonzero check. Printed `OK`,
early process exits, and all-skipped/expected-failure suites do not count as
success. Disposable workspaces and timeouts are not an OS security sandbox.

## Collaboration and automation

The agent supplies the task, explanation, complete solution, and actual checks
up front; an independent attempt is optional. At **09:30 local America/Vancouver**,
the external scheduler may prepare **one** private proposal only when every
previous exercise has been processed and explicitly approved for commit.
Pending, revision-requested, rejected, or invalid decision state blocks new work.
Existing proposals are preserved. A read-only pre-check skips blocked ticks
without waking the model; the normal draft command enforces the gate again.
This README does not prove the scheduler is active or that delivery occurred.

Telegram receives a short summary and a separately inspected, redacted full
card. Raw evidence stays local and immutable. Redaction is best-effort, not a
guarantee; ignoring a file does not sanitize it. Background runs may not edit
skills, protocols, memories, tracked files, Git state, or their own schedule.

Only an actual matching **live user decision** may be recorded; silence and
quoted/generated approval are not consent. The helper never applies, commits,
pushes, or publishes. Once destination, identity, access, and exact revision
are agreed, one approval covers that unchanged commit + push, not future edits.
A historical approval, an authorized publication, an actual verified remote
write, and demonstrated understanding are separate facts.

See [workflow](docs/WORKFLOW.md), [decisions](docs/DECISIONS.md), and
[roadmap](ROADMAP.md) for the boundaries, commands, and rollback procedure.
