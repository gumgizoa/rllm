# Later: openspec_ff

Ideas the user agreed to keep for later. Not decisions: nothing here is implemented. Each entry is added
only after the user said yes to recording it.

## Brownfield variant with pre-generated main specs (2026-10-14)

- **What**: a separate variant workflow (e.g. `openspec_ff_brownfield`) in which `/openspec/specs/` already
  holds main specs for each task instance, generated offline (e.g. by an LLM from the base repository), so
  the agent writes `## MODIFIED` / `REMOVED` / `RENAMED` deltas against existing requirements.
- **Why**: `openspec_ff` starts every sandbox with empty main specs (decision G7-5, upstream's own
  first-change-in-an-existing-project path), so the MODIFIED path of OpenSpec is never exercised in
  training or evaluation.
- **Open points when picked up**: the spec generator must not see the issue or the fix (leak); requirement
  names must be stable enough for MODIFIED to match; the harness has no per-task `sandbox_files` yet (only
  per workflow); upstream advises against back-filling specs (`docs/existing-projects.md:123`), so this is a
  deliberate departure and stays a separate variant, not a change to `openspec_ff`.
- **Origin**: `03-decisions.md` G7-5 (option 1 of three, not chosen for the base port).

## Explore scaffolds the change itself (2026-10-15)

- **What**: core-workflow acts as the person's request to capture the exploration as a change; explore runs
  `openspec new change "issue"` itself (scaffold only, upstream's capture path `explore:150-162`), and ff
  continues from the existing change.
- **Why**: keeps upstream's capture path instead of dropping it, and hands explore's findings to the
  proposal more directly than a summary message.
- **Open points when picked up**: ff step 2's `openspec new change "issue"` then exits 1 "already exists"
  (`cli-probe/03`), so D-7 and ff step 2 change; G4-17 (capture / "When a change exists" dropped) must be
  revisited; what explore may write after scaffolding (change artifacts only, per `explore:345`).
  Restore explore's "Don't manually scaffold changes" guardrail (`explore:350`, dropped by G7-10), since
  explore then scaffolds the change itself.
- **Origin**: `03-decisions.md` G4-13 option (b); the user will judge after the last explore smoke.
