# Step 1: Clarify and Route

## RULES

- **Language** — Write files in English.
- Treat the invocation intent as workflow input, not as a substitute for step-02 investigation and spec generation.

## Intent check (do this first)

Use the invocation prompt as the intent. Here the invocation prompt is the task message this run started with — the issue to resolve in the repository at `/testbed`. No spec file, spec folder or story list exists before the run, so there is nothing to resume: every run starts fresh from this intent.

Treat the invocation prompt as starting intent. This may be a story ID, ticket ID, file path, short description, or longer free-form intent. Do not infer workflow state from non-spec files.

## INSTRUCTIONS

1. Load context.
   - List files in `/tmp/bmad/implementation-artifacts/` (empty on a fresh run; the directory may not exist yet).
   - If the invocation prompt points to an unformatted spec or intent file, ingest that file. Do not scan for unrelated intent files.
   - There are no planning artifacts in this environment — no PRD, architecture, UX, epics or product brief — and no epic context to compile, so the work is never an epic story. Take the freeform path: the intent and the repository code are the context, and you need the right constraints and requirements from them rather than guessing.
2. Resolve intent from the invocation prompt and loaded artifacts. Do not fantasize or leave open questions.
3. Multi-goal warning. If the intent appears to contain multiple independently shippable goals, carry `multiple-goals` forward so step-02 can add it to `{spec_file}` frontmatter `warnings`. Do not split or block.
4. Route:

   Derive a valid kebab-case slug from the clarified intent. If the intent references a tracking identifier (story number, issue number, ticket ID), lead the slug with it (e.g. `3-2-digest-delivery`, `gh-47-fix-auth`). Set `spec_file` = `/tmp/bmad/implementation-artifacts/spec-{slug}.md` and `diff_file` = `/tmp/bmad/diff/{slug}.diff` (step-03 writes the diff there; create either directory when it is first needed).

## NEXT

Read fully and follow `/bmad-build-auto/stages/step-02-plan.md`
