# Step 2: Plan

## RULES

- **Language** — Write files in English.
- No human interaction: do not ask questions or wait for approval in this step.

## INSTRUCTIONS

1. Investigate codebase. _Read the code yourself for narrow, localized tasks. Isolate deep exploration in synchronous subagents: instruct them to give you distilled summaries only, and plan from those summaries._ Decide which findings actually matter for execution — the specific files, symbols/lines, reuse points, and read-only constraints — and carry those forward for the Code Map. This is where the investigation lands: the spec preserves it so it is never re-narrated to the implementer at dispatch time.
2. Read `/bmad-build-auto/spec-template.md` fully. Fill it out based on the intent and investigation, resolving the template's `date` field to the current system date. Drain the investigation into the `## Code Map` section — annotated paths, symbol/line anchors, reuse pointers, and read-only evidence — so the spec is the implementer's investigation map and the step-03 handoff need only point at it. Write the result to `{spec_file}`.
3. Self-review against READY FOR DEVELOPMENT standard.
4. Warning check. If step-01 carried `multiple-goals`, add it to `{spec_file}` frontmatter `warnings`. If `{spec_file}` exceeds 1600 tokens, add `oversized` to frontmatter `warnings`. Continue either way.

### READY-FOR-DEVELOPMENT GATE

Re-read `/bmad-build-auto/core-workflow.md`, then re-read `{spec_file}` from disk and verify the spec meets the READY FOR DEVELOPMENT standard.

- **If the spec meets the standard:** set `{spec_file}` frontmatter status to `ready-for-dev` and continue to step 3.
- **If the spec does not meet the standard:** repair it once, then re-read it from disk and verify again. If it now meets the standard, apply the **If the spec meets the standard** handling above. If it still does not meet the standard, set `{spec_file}` frontmatter `status: blocked`, record the blocking condition `spec failed ready-for-development standard` with the failing criteria and evidence gathered under `## Auto Run Result`, and continue to step 3 all the same.

## NEXT

Read fully and follow `/bmad-build-auto/stages/step-03-implement.md`
