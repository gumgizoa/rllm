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
