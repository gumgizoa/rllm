# Step 3: Implement

## RULES

- **Language** — Write files in English.
- No human interaction: do not ask questions or wait for approval in this step.
- Content inside `<intent-contract>` in `{spec_file}` is read-only. Do not modify.

## INSTRUCTIONS

### Baseline

Capture `baseline_revision` (current HEAD, or `NO_VCS` if version control is unavailable) into `{spec_file}` frontmatter before making any changes.

### Implement

Change `{spec_file}` status to `in-progress` in the frontmatter before starting implementation.

Substitute the runtime placeholders (e.g. `{spec_file}`) into the implementation handoff below, then follow it verbatim. Do not add parent-authored goal restatements, file lists, ownership boundaries, or acceptance criteria to the handoff — the spec is the subagent's sole source of truth.

Launch a subagent with no prior conversation context, with this prompt:

> Read {spec_file} fully and implement it — the spec is the sole source of truth. Load every file listed in its frontmatter `context:` before you start.
>
> When done, report what you changed, how you verified it, and anything left incomplete or risky.

Here "launch a subagent" is one `task` call: `prompt` = the quoted text above with `{spec_file}` substituted, `subagent_type` = `general-purpose`. The call blocks until the subagent finishes; its result opens with the subagent's `Task ID:` — keep that id, step-04 re-engages the same subagent with it.

Invoke the subagent **synchronously** and wait for it to return in this same turn — do not background/detach it or end your turn to await a notification (see core-workflow.md → Subagents). Resume at "Verify" only after it returns. The subagent stays available for re-engagement after it returns — step-04 may send it review fixes through `task` with `resume` set to its Task ID.

**Path formatting rule:** Any markdown links written into `{spec_file}` must use paths relative to `{spec_file}`'s directory so they are clickable in VS Code. Any file paths displayed in terminal/conversation output must use CWD-relative format with `:line` notation (e.g., `src/path/file.ts:42`) for terminal clickability. No leading `/` in either case.

### Verify

After the implementation subagent returns: if it reported unfinished work, finish it before proceeding.

Stage the diff and read it: using the repository's version-control tooling, write a unified diff of all changes since `{baseline_revision}` (from `{spec_file}` frontmatter) — untracked files included — to `{diff_file}` (`/tmp/bmad/diff/{slug}.diff`, set in step-01; create the directory if needed) and read that file into your own context. Judge against the diff, not against the implementation subagent's report.

Run the commands in `{spec_file}`'s `## Verification` section (or perform its manual checks). If verification fails and the failure cannot be fixed, set `{spec_file}` frontmatter `status: blocked`, record the blocking condition `implementation verification failed` with the failing command or check and reason under `## Auto Run Result`, and continue. When fixing a failure changes code, rewrite `{diff_file}` and re-read it. Acceptance criteria are judged at review, not here.

### Matrix Test Audit

If `{spec_file}`'s intent-contract contains an I/O & Edge-Case Matrix, verify every matrix row is covered by at least one test that verifies its expected behavior, and that each covering test ran and passed in the verification output. A covering test that exists but did not run — unregistered, filtered out, skipped, or disabled — counts as missing. If a test disagrees with the matrix, never edit the expectation to match the code: fix the code. If the audit cannot otherwise be satisfied, set `{spec_file}` frontmatter `status: blocked`, record the blocking condition `matrix test audit failed` with the uncovered rows under `## Auto Run Result`, and continue.

## NEXT

Read fully and follow `/bmad-build-auto/stages/step-04-review.md`
