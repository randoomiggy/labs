# Engineering Practice — project policy

## Purpose and scope
- Build a credible job-search portfolio and learn Python, algorithms, AI tooling,
  SRE methodology, DevOps, and system tools through small reproducible changes.
- Local preparation is the default. The live user separately authorized publishing
  the reviewed foundation, workflow improvements, and EP-001 to the agreed existing
  repository using the configured Git identity. See `docs/DECISIONS.md`.
  This does not authorize future automatic publication, installs, global config,
  a different destination, a visibility change, or a license choice.
- Communicate in Russian; use English code identifiers and an English root README.
- Provide the task, explanation, and complete solution up front; an initial user
  attempt is optional, not a gate.

## Sources of truth
- `AGENTS.md`: durable policy, not a plan, queue, or journal.
- `docs/WORKFLOW.md`: exact preparation, testing, review, and publication gates.
- `docs/DECISIONS.md`: accepted design decisions and unresolved choices.
- `ROADMAP.md`: proposed progression; `BACKLOG.json`: ordered exercise proposals.
- `.local/`: private workflow state, immutable snapshots, actual test evidence,
  and decision records. Use CLI output for paths; do not invent state filenames.
- `templates/task.md`: task card; `practice/`: exercises; `labs/`: later labs.
- Proposed, reviewed, approved, published, and understood are different claims.
  Neither a decision record nor a contribution count proves learning. The helper
  records `pending`, `approved`, `rejected`, `revision_requested`, `superseded`;
  it never records pushed/publication evidence. A future live assistant must
  verify the remote and journal actual publication separately.

## Start every run
1. Confirm the project workdir; inspect loaded context for higher-priority overrides.
2. Explicitly read this file, `docs/WORKFLOW.md`, `docs/DECISIONS.md`,
   `ROADMAP.md`, and `BACKLOG.json`; run `status` and `next` below.
3. `next` must explicitly return `blocked: false` before a NEW exercise can be
   prepared. Pending, revision-requested, rejected, unknown or corrupt decision
   state blocks progression. Preserve existing proposals; silence is not consent.
   Only a live requested revision of the earliest unresolved exercise may proceed.
   `depends_on` is a pedagogical hint, not evidence of publication or learning.
   Include unavailable prerequisite code only in an otherwise permitted bundle;
   never apply old unapproved code as a prerequisite.
4. Follow the accepted scope; show new curriculum as a proposal. Once seed keys
   are exhausted, `next` may suggest a generated key/topic without editing backlog.

## Commands (from project root)
```sh
python3 -m unittest discover -s tests -v
python3 tools/workflow.py status
python3 tools/workflow.py next
```
- `make test`, `make status`, and `make next` wrap those commands.
- See `docs/WORKFLOW.md` for `init-state`, `draft`, `verify`, `test`, and
  live-only `decide`. An optional global `--root ROOT` precedes the subcommand.
- There is no workflow commit, push, apply, or publish command.

## Daily automation boundary
- Required schedule: 09:30 local `America/Vancouver`, not a fixed UTC offset.
- Cron starts a fresh session. Project workdir enables context discovery;
  `.hermes.md` / `HERMES.md` or `AGENTS.override.md` can supersede `AGENTS.md`.
- Attached skills: `igor-work-protocol`, `github`, `it-systems-coding-research`.
  `attach_to_session` and continuity help follow-up; they do not grant consent.
- Automatic work may prepare private pending payloads/snapshots and run verification
  in `.local/` only. Never edit the tracked tree or Git state from cron.
- `tools/daily_gate.py` is a read-only scheduler pre-check. While earlier proposals
  lack explicit commit approval it emits `wakeAgent: false`; no new daily task,
  revision, or repeated reminder is generated. Missing/broken state fails closed.
  The normal helper also enforces selection under its write lock.
- Never call `decide` from cron, infer a decision from history, or close an
  unanswered task. Send ID, version, fingerprint, paths, and real test evidence.
- Meaningful persistent workflow changes need explicit local approval too.
  Changes to policy, tracked docs, or backlog are separate proposed diffs.
- Loading a skill is not permission to edit it. Cron must not change skills,
  memories, protocols, configuration, schedules, or unrelated project files.
- Keep Telegram to one useful status/decision screen. Put complete solutions and
  evidence in a separately checked export via `tools/report_export.py`, never a
  raw snapshot attachment. Mask home usernames and contact/account identifiers;
  preserve immutable originals locally. Masking is not a complete security scan.

## Verification and immutable review
- Each proposal has task ID `GH-YYYYMMDD` (Vancouver date), task key, version,
  manifest, fingerprint, base Git commit, and destination/content hashes.
- Versions are immutable. Changes require a new version and fresh review;
  prior approval never transfers to changed content or a changed base.
- Run real, nonzero `unittest` tests: normal, boundary, and relevant invalid cases.
  Record commands, counts, outputs, exit status, and failures; do not invent results.
- Counters come from `tools/unittest_driver.py` after normal runner completion,
  not from printed stderr. Early exits and all-skipped suites are not passes.
- Disposable copied test workspaces, sanitized environments, and a 60-second
  timeout reduce accidents; they are NOT an OS security sandbox for hostile code.
- Only a live agent receiving the matching Telegram message may record a decision.
  Exact evidence is `Одобряю GH-YYYYMMDD v1`, `Отклоняю GH-YYYYMMDD v1`, or
  `Доработать GH-YYYYMMDD v1` with the actual ID/version substituted.
- `approve` also requires the current pending version, exact fingerprint,
  unchanged base, and actual passing tests (not only skips/expected failures).
  The CLI cannot authenticate Telegram.

## Publication is separate live work
- No operation in the workflow copies proposed files into the tracked tree,
  commits, or pushes. Approval records a decision, not publication.
- Before any publication, obtain explicit destination/visibility/identity approval,
  verify the authenticated account and repository access, and review exact paths.
  Global Git author fields do not verify account ownership or push permission.
- Once destination, identity, and publication mode are explicitly configured,
  one matching live card approval covers commit + push of that exact payload.
  Do not ask for redundant approval of an unchanged diff; cron still never publishes.
- Recheck the manifest, base, destination contents, and tests before applying a
  separately authorized change. Stage only reviewed paths, never `git add .`.
- `approved` is decision history. Before applying, require
  `verify.local_approval_valid == true`; that still does not prove GitHub access.
- The uncommitted scaffold needs its own review; never smuggle it into a task's
  first commit. Verify the exact remote ref/content after any authorized push.

## Honesty, privacy, and rights
- Label AI-assisted work and distinguish generated, tested, reviewed, and learned.
  Do not fabricate experience, production incidents, benchmarks, or mastery.
- Use synthetic data only: no employer logs, internal configs, PII, credentials,
  real identifiers, or sensitive test output. Ignoring a file does not redact it.
- Prefer original exercises. Cite sources and check terms before copying book or
  challenge statements, illustrations, or code. No LICENSE until the user chooses.
- Do not install tools or expand scope implicitly. Propose larger labs first.
- Pause the daily job separately before manual removal; see `docs/WORKFLOW.md`.
