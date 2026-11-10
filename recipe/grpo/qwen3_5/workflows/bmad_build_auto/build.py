"""Build ``docs/`` from the BMAD-METHOD checkout (bmad-code-org/BMAD-METHOD, skill ``bmad-build-auto``).

    python -m recipe.grpo.qwen3_5.workflows.bmad_build_auto.build --upstream /path/to/BMAD-METHOD
    python -m recipe.grpo.qwen3_5.workflows.bmad_build_auto.build --upstream ... --check   # exit 1 on drift
    python -m recipe.grpo.qwen3_5.workflows.bmad_build_auto.build --list                   # the edits, by tag

Upstream, ``bmad-build-auto`` is a skill a person types into an agent app; its first instruction runs
``uv run render_skill.py``, which copies the skill's documents into an immutable snapshot after replacing
their tokens (``{{.implementation_artifacts}}`` and the language settings from ``_bmad/config.toml``,
``{workflow.*}`` from ``customize.toml``, ``[[bmad-snapshot:file.md]]`` -> the snapshot's absolute path).
The sandbox has neither ``uv`` nor an installed ``_bmad/``, so this module does the renderer's work once,
at build time, and the result is uploaded to ``/bmad-build-auto/``:

``workflow.md``            -> ``core-workflow.md`` (the entry document: HALT protocol, subagent rule, READY
                              standard, conventions, plus **The setting of this run**, written for this port)
``step-0N-*.md``           -> ``stages/step-0N-*.md``
``spec-template.md``       -> ``spec-template.md`` (verbatim but for the project-root token)
``review-prompts/*.md``    -> ``review-prompts/*.md`` (the reviewer subagents' instructions)
``references/*.md``        -> ``references/*.md`` (the edge-case hunter's two secondary passes)
``customize.toml``         -> inlined where the renderer put it: ``implementation_handoff`` into step-03,
                              the four ``review_layers`` into step-04 (``#### Name (`id`)`` sections, as
                              ``render_skill.py:_format_review_layers`` formats them). The toml values are
                              embedded below and compared with the checkout on every build.
``compile-epic-context.md``   not shipped (epic path, G3).

Tags: ``env`` closes a gap between the skill's setting (installed ``_bmad/``, planning artifacts, several
invocation modes, git branches and commits, an agent app's subagent API) and one unattended sandbox run
without changing what is asked; ``semantic`` changes what the agent does (porting/03-decisions.md D-2:
the intent HALTs are deleted and the failure HALTs record ``status: blocked`` and continue; D-1: no
commit at the end). Every note starts with the gap or decision ID of ``porting/02-gaps.md`` /
``03-decisions.md``. An anchor that does not occur exactly once fails the build, so an upstream rewording
surfaces here. The engine is ``workflows/_port.py``.

``SUBSTITUTIONS`` are the renderer's own token replacements (snapshot references, ``{skill-root}``,
``{project-root}``, the artifacts directory); they are not edits of the upstream text and carry no tag.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

from .._port import Edit, Port, Section, list_edits
from .._port import build as _build
from .._port import convert as _convert
from .._port import drift as _drift
from .._port import git_head as _git_head

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "docs"

# What every output was built from. Another commit only warns; the anchors decide.
UPSTREAM_COMMIT = "10db8f35bba515e4fbf0388c5bd59a6cc7a3e9c8"  # v6.12.2
SKILL_DIR = "src/bmm-skills/ship/bmad-build-auto"

DOCS_ROOT = "/bmad-build-auto"
ENTRY_DOC = f"{DOCS_ROOT}/core-workflow.md"
STAGES_DIR = f"{DOCS_ROOT}/stages"
REPO_ROOT = "/testbed"
ARTIFACTS_ROOT = "/tmp/bmad"  # SPEC.output_dirs
IMPLEMENTATION_ARTIFACTS = f"{ARTIFACTS_ROOT}/implementation-artifacts"  # upstream {{.implementation_artifacts}}
DIFF_DIR = f"{ARTIFACTS_ROOT}/diff"  # upstream: a uniquely-named temp file
SPEC_FILE = f"{IMPLEMENTATION_ARTIFACTS}/spec-{{slug}}.md"
DIFF_FILE = f"{DIFF_DIR}/{{slug}}.diff"
RESULT_FILE = f"{IMPLEMENTATION_ARTIFACTS}/bmad-build-auto-result-<slug-or-timestamp>.md"

STEP_FILES = ("step-01-clarify-and-route.md", "step-02-plan.md", "step-03-implement.md", "step-04-review.md")
SOURCES: dict[str, tuple[str, str]] = {
    "workflow": (f"{SKILL_DIR}/workflow.md", "core-workflow.md"),
    **{f"step0{i}": (f"{SKILL_DIR}/{f}", f"stages/{f}") for i, f in enumerate(STEP_FILES, start=1)},
    "template": (f"{SKILL_DIR}/spec-template.md", "spec-template.md"),
    "edge": (f"{SKILL_DIR}/review-prompts/edge-case-hunter.md", "review-prompts/edge-case-hunter.md"),
    "vgap": (f"{SKILL_DIR}/review-prompts/verification-gap.md", "review-prompts/verification-gap.md"),
    "claims": (f"{SKILL_DIR}/references/claims-check.md", "references/claims-check.md"),
    "deletion": (f"{SKILL_DIR}/references/deletion-check.md", "references/deletion-check.md"),
}
STAGE_DOCS = {f"step0{i}": f"{STAGES_DIR}/{f}" for i, f in enumerate(STEP_FILES, start=1)}
CUSTOMIZE_TOML = f"{SKILL_DIR}/customize.toml"

# ----------------------------------------------------------------------------------------------------
# customize.toml, embedded (checked against the checkout by ``check_customization``)
# ----------------------------------------------------------------------------------------------------

IMPLEMENTATION_HANDOFF = """
Launch a subagent with no prior conversation context, with this prompt:

> Read {spec_file} fully and implement it — the spec is the sole source of truth. Load every file listed in its frontmatter `context:` before you start.
>
> When done, report what you changed, how you verified it, and anything left incomplete or risky.
"""

REVIEW_LAYERS: tuple[dict[str, str], ...] = (
    {
        "id": "blind-hunter",
        "name": "Blind Hunter",
        "instruction": """
Launch a context-free subagent with this prompt:

Conduct a review of CONTENT.
Look for what's missing, not only what's wrong.
Compute your finding floor N from the diff file's size: N = min(floor(sqrt(kB) + 1), 10), where kB is the file's size in kilobytes. State the arithmetic in one line, then find at least N issues to fix or improve.
Output a Markdown list of findings only — no severity, priority, or ranking.
If the content is empty, stop and say so.
If you have zero findings, re-check and keep thinking; do not stop with an empty list.

CONTENT: the unified diff at `{diff_file}`. Read that file — it is the content under review.

Do not invoke any skill, and do not spawn subagents of your own — you are the reviewer. Return your findings as text in your final message; do not route them through any findings-reporting tool the host may offer.

""",
    },
    {
        "id": "edge-case-hunter",
        "name": "Edge Case Hunter",
        "instruction": """
Launch a context-free subagent with this prompt:

Read `{skill-root}/review-prompts/edge-case-hunter.md` completely and follow it as your review instructions.

claims_file (leave unread until your instructions call for it): {claims_file}

Review content: the unified diff at `{diff_file}`. Read that file — it is the content under review.

Do not invoke any skill, and do not spawn subagents of your own — you are the reviewer. If the instruction file is unreadable, report that exact failure and stop. Return your findings as text in your final message; do not route them through any findings-reporting tool the host may offer.

""",
    },
    {
        "id": "verification-gap",
        "name": "Verification Gap Reviewer",
        "instruction": """
Launch a context-free subagent with this prompt:

Read `{skill-root}/review-prompts/verification-gap.md` completely and follow it as your review instructions.

Review content: the unified diff at `{diff_file}`. Read that file — it is the content under review.

Do not invoke any skill, and do not spawn subagents of your own — you are the reviewer. If the instruction file is unreadable, report that exact failure and stop. Return your findings as text in your final message; do not route them through any findings-reporting tool the host may offer.

""",
    },
    {
        "id": "intent-alignment",
        "name": "Intent Alignment Auditor",
        "instruction": """
Launch a subagent with this prompt:

You are an intent-alignment auditor. You have no other context about how this change was produced. Here is the verbatim intent this work started from:

{verbatim_intent}

The diff is the unified diff at `{diff_file}`. Read that file — it is the change under review.

Your task is strictly descriptive — do not prescribe additional work. Report: (1) the defensible readings of the intent, enumerated; (2) which reading this diff implements; (3) where the readings and the diff diverge — specifically, which surface the intent's expectations live at versus which surface the diff's changes and its tests exercise.

Do not invoke any skill, and do not spawn subagents of your own — you are the reviewer. Return your findings as text in your final message; do not route them through any findings-reporting tool the host may offer.

""",
    },
)
LAYER_IDS = tuple(layer["id"] for layer in REVIEW_LAYERS)


def format_review_layers(layers=REVIEW_LAYERS) -> str:
    """``render_skill.py:_format_review_layers`` for layers without ``when``: ``#### Name (`id`)`` + instruction."""
    return "\n\n".join(f"#### {layer['name']} (`{layer['id']}`)\n\n{layer['instruction'].strip()}" for layer in layers)


def check_customization(upstream: Path) -> None:
    """The embedded customize.toml values must be the checkout's (a change there is an upstream change)."""
    data = tomllib.loads((upstream / CUSTOMIZE_TOML).read_text(encoding="utf-8"))["workflow"]
    # TOML drops the newline right after an opening \"\"\"; compare stripped.
    if data["implementation_handoff"].strip() != IMPLEMENTATION_HANDOFF.strip():
        raise ValueError(f"{CUSTOMIZE_TOML}: implementation_handoff differs from the embedded text")
    theirs = [(layer["id"], layer["name"], layer["instruction"].strip()) for layer in data["review_layers"]]
    if theirs != [(layer["id"], layer["name"], layer["instruction"].strip()) for layer in REVIEW_LAYERS]:
        raise ValueError(f"{CUSTOMIZE_TOML}: review_layers differ from the embedded text")
    for key in ("activation_steps_prepend", "activation_steps_append", "persistent_facts"):
        if data[key] != []:
            raise ValueError(f"{CUSTOMIZE_TOML}: {key} is no longer empty; the dropped activation hooks need a decision")
    if data["on_complete"] != "":
        raise ValueError(f"{CUSTOMIZE_TOML}: on_complete is no longer empty; the dropped hook needs a decision")


# ----------------------------------------------------------------------------------------------------
# text written for this port (core-workflow.md)
# ----------------------------------------------------------------------------------------------------

HALT_SECTION = f"""## HALT

To HALT with a final status and optional blocking condition:

1. If `{{spec_file}}` is known and exists, update `status` in frontmatter and append missing result details under `## Auto Run Result`.
2. If `{{spec_file}}` is unknown or missing, create `{RESULT_FILE}` with:
   ```markdown
   ---
   status: <final status>
   ---

   # BMad Build Auto Result

   Status: <final status>
   Blocking condition: <blocking condition, if any>
   ```
3. Stop the workflow. Nothing follows a HALT except ending the session.
"""

SETTING_SECTION = f"""## The setting of this run

This workflow runs unattended, inside a sandbox, on one task. What that means for each step:

| Step | Document | What it produces |
|---|---|---|
| 1 | `{STAGE_DOCS["step01"]}` | the slug, `{{spec_file}}` and `{{diff_file}}` |
| 2 | `{STAGE_DOCS["step02"]}` | the spec, filled from `{DOCS_ROOT}/spec-template.md`, through the READY gate |
| 3 | `{STAGE_DOCS["step03"]}` | the implementation (by the implementation subagent), the staged diff, verification |
| 4 | `{STAGE_DOCS["step04"]}` | four review layers (subagents), the triage log, patches or a loopback to step 3, `## Auto Run Result`, HALT |

- **Intent.** The task message that opened this conversation is the invocation intent: an issue against the repository at `{REPO_ROOT}`, which is the project root. Nothing else arrives — no planning artifacts, no epic, no story list, no earlier spec — so step 1 always takes the freeform path and every run plans from scratch.
- **Nobody answers.** No person reads this conversation while it runs. A question, a request for approval or a plain text reply with no tool call ends the session with nothing graded. Settle open points yourself, inside the step that raised them, and write the choice into the spec.
- **Where files go.** Everything the workflow writes for itself lives outside the repository: the spec at `{SPEC_FILE}`, the diff at `{DIFF_FILE}`, a fallback result file under `{IMPLEMENTATION_ARTIFACTS}/`. Create `{IMPLEMENTATION_ARTIFACTS}/` and `{DIFF_DIR}/` when they are first needed. The only writes into `{REPO_ROOT}` are the implementation itself — the source and test files the spec's tasks name — and the review patches. Scratch files, notes, copies of these documents and the diff do not belong in `{REPO_ROOT}`.
- **Subagents.** "Launch a subagent" means one call of the `task` tool. Its `prompt` must carry everything the subagent needs — it starts with no memory of this conversation, so put the spec path, the diff path and the full instruction text into the prompt. Leave `subagent_type` at `general-purpose`: a subagent of that type has the terminal, the file editor and the task tracker, and works in the same `{REPO_ROOT}`; it cannot launch subagents of its own. The call blocks until the subagent finishes. Its result opens with `Task ID: task_…`, `Subagent: …` and `Status: …`, followed by the subagent's final message — that message is the "report" or "findings" the steps refer to. Several `task` calls issued in one assistant turn are all carried out before that turn resumes — the turn waits for every one of them; that is how step 4 runs its four review layers as one launch. A `task` call with `resume` set to an earlier Task ID continues that same subagent's conversation; that is how step 4 hands the implementation subagent its fixes. The subagent's name is the Task ID the tool assigns — keep the implementation subagent's Task ID from step 3 for step 4.
- **A failed check does not end the run.** Where a step says to set `status: blocked` and record a blocking condition, write both into `{{spec_file}}` — `status` in the frontmatter and a line under `## Auto Run Result` — and carry on with the next instruction. The run still reaches Finalize and HALT, with `blocked` as its final status.
- **What is graded.** The working tree of `{REPO_ROOT}` after HALT. Do not commit, stash, reset or clean the repository: a commit would take the change out of the graded diff.
- **Reading order.** This document first, then `{STAGE_DOCS["step01"]}` and the steps it chains to. Open each document when its step begins, not before. The spec template and the reviewer prompts are under `{DOCS_ROOT}/` too; the reviewer prompts are read by the review subagents, not by you.
- **End.** The run ends with HALT — `done`, or `blocked` when a blocking condition was recorded — after `## Auto Run Result` is written. Then call `finish`.
"""

# ----------------------------------------------------------------------------------------------------
# edits (anchors are upstream text, applied first), sections (applied after the edits)
# ----------------------------------------------------------------------------------------------------

LANGUAGE_RULE = "- **Language** — Speak in `{{.communication_language}}`, tailored to `{{.user_skill_level}}`. Write files in `{{.document_output_language}}`."
LANGUAGE_RULE_PORT = "- **Language** — Write files in English."

STEP01_DISPATCH = (
    "Use the invocation prompt as the intent.\n"
    "\n"
    "If the invocation prompt explicitly points to an existing spec file with recognized `status` frontmatter, set `spec_file`, then **EARLY EXIT** to the appropriate step:\n"
    "- `draft` → `[[bmad-snapshot:step-02-plan.md]]`\n"
    "- `ready-for-dev` or `in-progress` → `[[bmad-snapshot:step-03-implement.md]]`\n"
    "- `in-review` → `[[bmad-snapshot:step-04-review.md]]`\n"
    "- `blocked` → HALT with status `blocked` and blocking condition `blocked spec supplied`.\n"
    "- `done` → set `review_loop_iteration` to `0` in the frontmatter and set `followup_pass` to `true`, then **EARLY EXIT** to `[[bmad-snapshot:step-04-review.md]]` for a fresh review pass. (A `done` spec is a completed run, so this starts a follow-up review, not a resumption.)\n"
    "\n"
    "If the invocation prompt instead supplies a spec folder and a story id, with no specific spec file path, this is a **folder+id dispatch**: set `spec_folder` (a `{project-root}`-relative or absolute path) and `story_id` from the prompt. Any further prompt text (e.g. `invoke_dev_with` guidance the caller appended) is additional planning context to carry into step-02 — not a competing description of what to implement.\n"
    "\n"
    "Read `{spec_folder}/stories.yaml`. If the file does not exist or fails to parse, HALT with status `blocked` and blocking condition `no stories.yaml found`. Find the entry whose `id` equals `{story_id}`; if none matches, HALT with status `blocked` and blocking condition `story id not found in stories.yaml`. Take only that entry's `title` and `description` — never read the checkpoint fields or `invoke_dev_with`; those are the caller's orchestration fields, not build-auto's.\n"
    "\n"
    "Look for files matching `{spec_folder}/stories/{story_id}-*.md` (id-prefix match — story ids are prefix-free, so at most one should match):\n"
    "- **If more than one matches**, HALT with status `blocked` and blocking condition `ambiguous story file match`.\n"
    "- **If exactly one matches**, set `spec_file` to that path.\n"
    "  - `draft` (planning was interrupted mid-flight): accumulate cross-story context before resuming — load every other file matching `{spec_folder}/stories/*.md` (every match except `{spec_file}` itself), regardless of `status`, and carry forward each one's **Code Map**, **Design Notes**, **Spec Change Log**, **Tasks & Acceptance** checklist state, and **Auto Run Result** details, where present, as additional planning context for step-02. Then **EARLY EXIT** to `[[bmad-snapshot:step-02-plan.md]]`.\n"
    "  - Any other recognized `status`: **EARLY EXIT** using the same routing as above, including the `review_loop_iteration` reset and `followup_pass` for `done`. One difference: a `blocked` story HALTs with blocking condition `story already blocked`, not `blocked spec supplied` — the caller did not supply this file; build-auto found it by id.\n"
    "  - `status` missing or unrecognized: HALT with status `blocked` and blocking condition `unrecognized status in existing story file`.\n"
    "- **If none matches**, this is the first dispatch for `{story_id}`. The entry's `title` and `description` are the resolved intent. If `{spec_folder}/SPEC.md` does not exist, HALT with status `blocked` and blocking condition `no epic spec found`. Otherwise load it and the files listed in its `companions:` frontmatter as planning context, then accumulate cross-story context the same way as the `draft` case above — load every file matching `{spec_folder}/stories/*.md` (none yet exists for `{story_id}` at this point, so nothing is excluded), regardless of `status`, carrying forward the same fields, where present, as additional planning context for step-02. Then continue to INSTRUCTIONS item 3 below — not `step-03-implement.md`, item 3 of the numbered list in this file (items 1 and 2 do not apply — context and intent are already resolved; item 1.A.5's previous-story continuity scan in particular never runs here, since folder+id dispatch already skips items 1 and 2 entirely — the cross-story accumulation above is its replacement for this dispatch mode).\n"
    "\n"
    "One `stories.yaml` entry per invocation: never read another entry, and never advance to a different story id regardless of outcome.\n"
    "\n"
    "Otherwise, treat the invocation prompt as starting intent."
)
STEP01_DISPATCH_PORT = (
    "Use the invocation prompt as the intent. Here the invocation prompt is the task message this run started with — "
    f"the issue to resolve in the repository at `{REPO_ROOT}`. No spec file, spec folder or story list exists before the "
    "run, so there is nothing to resume: every run starts fresh from this intent.\n"
    "\n"
    "Treat the invocation prompt as starting intent."
)

STEP01_CONTEXT = (
    "1. Load context.\n"
    "   - List files in `{{.planning_artifacts}}` and `{{.implementation_artifacts}}`.\n"
    "   - If the invocation prompt points to an unformatted spec or intent file, ingest that file. Do not scan for unrelated intent files.\n"
    "   - **Determine context strategy.** Using the intent and the artifact listing, infer whether the current work is a story from an epic. Do not rely on filename patterns or regex — reason about the intent, the listing, and any epics file content together.\n"
    "\n"
    "     **A) Epic story path** — if the intent is clearly an epic story:\n"
    "\n"
    "     1. Identify the epic number `{epic_num}` and (if present) the story number `{story_num}`. If you can't identify an epic number, use path B.\n"
    "\n"
    "     2. **Check for a valid cached epic context.** Look for `{{.implementation_artifacts}}/epic-<N>-context.md` (where `<N>` is the epic number). A file is **valid** when it exists, is non-empty, starts with `# Epic <N> Context:` (with the correct epic number), and no file in `{{.planning_artifacts}}` is newer.\n"
    "        - **If valid:** load it as the primary planning context. Do not load raw planning docs (PRD, architecture, UX, etc.).\n"
    "        - **If missing, empty, or invalid:** compile it in the next bullet.\n"
    "\n"
    "     3. **Compile epic context if needed.** If no valid cached epic context was loaded, produce `{{.implementation_artifacts}}/epic-<N>-context.md` by spawning a subagent synchronously with `[[bmad-snapshot:compile-epic-context.md]]` as its prompt. Pass it the epic number, epics file path, `{{.planning_artifacts}}`, and output path `{{.implementation_artifacts}}/epic-<N>-context.md`.\n"
    "\n"
    "     4. **Verify if compiled.** If epic context was compiled, verify the output file exists, is non-empty, and starts with `# Epic <N> Context:`. If valid, load it. If verification fails, HALT with status `blocked` and blocking condition `context compilation verification failed`.\n"
    "\n"
    "     5. **Previous story continuity.** Regardless of which context source succeeded above, scan `{{.implementation_artifacts}}` for specs from the same epic with `status: done` and a lower story number. Load the most recent one (highest story number below current). Extract its **Code Map**, **Design Notes**, **Spec Change Log**, and **task list** as continuity context for step-02 planning. If no `done` spec is found but an `in-review` spec exists for the same epic with a lower story number, HALT with status `blocked` and blocking condition `missing previous-story continuity decision`.\n"
    "\n"
    "     **B) Freeform path** — if the intent is not an epic story:\n"
    "     - Planning artifacts are the output of BMAD phases 1-3. Typical files include:\n"
    "       - **PRD** (`*prd*`) — product requirements and success criteria\n"
    "       - **Architecture** (`*architecture*`) — technical design decisions and constraints\n"
    "       - **UX/Design** (`*ux*`) — user experience and interaction design\n"
    "       - **Epics** (`*epic*`) — feature breakdown into implementable stories\n"
    "       - **Product Brief** (`*brief*`) — project vision and scope\n"
    "     - Scan the listing for files matching these patterns. If any look relevant to the current intent, load them selectively — you don't need all of them, but you need the right constraints and requirements rather than guessing from code alone.\n"
)
STEP01_CONTEXT_PORT = (
    "1. Load context.\n"
    f"   - List files in `{IMPLEMENTATION_ARTIFACTS}/` (empty on a fresh run; the directory may not exist yet).\n"
    "   - If the invocation prompt points to an unformatted spec or intent file, ingest that file. Do not scan for unrelated intent files.\n"
    "   - There are no planning artifacts in this environment — no PRD, architecture, UX, epics or product brief — and "
    "no epic context to compile, so the work is never an epic story. Take the freeform path: the intent and the "
    "repository code are the context, and you need the right constraints and requirements from them rather than guessing.\n"
)

STEP01_VCS = (
    "3. Version control sanity check. If version control is unavailable, skip this check. Otherwise require a clean working tree, a branch that fits the intent, and writable repository metadata. For Git, run `git add --refresh -- .`, then confirm the tree is still clean; on failure or change, HALT with status `blocked` and blocking condition `version-control metadata not writable`. Under folder+id dispatch, judge the branch against the epic, not the story. HALT on a dirty tree or obvious branch mismatch.\n"
)
STEP01_ROUTE_DISPATCH = (
    "\n"
    "   **Folder+id dispatch:** derive a valid kebab-case slug from the entry's `title` (and `description` if needed) — the same kebab-casing convention as below, but never prefixed with `{story_id}`, since the id is already the filename's separate leading segment. Set `spec_file` = `{spec_folder}/stories/{story_id}-{slug}.md`. The id already disambiguates: no `{{.implementation_artifacts}}` fallback, no `-2`/`-3` suffixing.\n"
)
STEP01_ROUTE = (
    "   **Otherwise:** derive a valid kebab-case slug from the clarified intent. If the intent references a tracking identifier (story number, issue number, ticket ID), lead the slug with it (e.g. `3-2-digest-delivery`, `gh-47-fix-auth`). If `{{.implementation_artifacts}}/spec-{slug}.md` already exists: if its status is `draft`, treat it as the same work and resume it (set `spec_file` to that path, **EARLY EXIT** → `[[bmad-snapshot:step-02-plan.md]]`); otherwise append `-2`, `-3`, etc. Set `spec_file` = `{{.implementation_artifacts}}/spec-{slug}.md`."
)
STEP01_ROUTE_PORT = (
    "   Derive a valid kebab-case slug from the clarified intent. If the intent references a tracking identifier (story number, issue number, ticket ID), lead the slug with it (e.g. `3-2-digest-delivery`, `gh-47-fix-auth`). "
    f"Set `spec_file` = `{SPEC_FILE}` and `diff_file` = `{DIFF_FILE}` (step-03 writes the diff there; create either directory when it is first needed)."
)

STEP04_FINALIZE = (
    "If version control is unavailable, set `{spec_file}` frontmatter `status: done`, then proceed to HALT.\n"
    "\n"
    "If version control is available, write `status: done` into `{spec_file}` frontmatter, then:\n"
    "\n"
    "1. Commit any reviewed-diff files that remain uncommitted, including `{spec_file}` when it is tracked in that working copy. Keep commits already created during this run. Verify every reviewed-diff file appears in the change set after `{baseline_revision}` and none remains uncommitted. Do not push.\n"
    "2. Verify the version-controlled working copy is clean. Otherwise HALT with status `blocked` and blocking condition `finalization left repository dirty`.\n"
    "\n"
    "HALT with status `done`."
)
STEP04_FINALIZE_PORT = (
    "Set `{spec_file}` frontmatter `status: done` — unless an earlier step recorded a blocking condition, in which case "
    "`status: blocked` stays — then proceed to HALT with that status. Do not commit, stash or clean anything: the change "
    f"stays in the working tree of `{REPO_ROOT}`, which is what gets graded."
)

HANDOFF_PORT = (
    IMPLEMENTATION_HANDOFF.strip()
    + "\n\n"
    + "Here \"launch a subagent\" is one `task` call: `prompt` = the quoted text above with `{spec_file}` substituted, "
    "`subagent_type` = `general-purpose`. The call blocks until the subagent finishes; its result opens with the "
    "subagent's `Task ID:` — keep that id, step-04 re-engages the same subagent with it."
)

EDITS: tuple[Edit, ...] = (
    # ---- workflow.md -> core-workflow.md
    Edit(
        "workflow",
        "**CRITICAL:** If a step directs you to another snapshot file, read it fully and follow it. No exceptions.",
        "**CRITICAL:** If a step directs you to another workflow document, read it fully and follow it. No exceptions.",
        "env",
        "G5: no rendered snapshot; the documents are the uploaded files",
    ),
    Edit(
        "workflow",
        "Using subagents when instructed is mandatory. If you cannot, HALT with status `blocked` and blocking condition `no subagents`.",
        "Using subagents when instructed is mandatory. A subagent is launched with the `task` tool (see **The setting of this run** below): one `task` call runs one subagent to completion and returns its final message.",
        "env",
        "D-7/G7: the sandbox has the task tool, so the `no subagents` HALT has no trigger; the tool named once",
    ),
    Edit(
        "workflow",
        "- Every operational cross-file reference in this workflow is an absolute snapshot path. Open it directly; do not resolve it relative to a skill directory.",
        f"- Every operational cross-file reference in this workflow is an absolute path under `{DOCS_ROOT}/`. Open it directly.",
        "env",
        "G5: snapshot paths -> the uploaded documents' paths",
    ),
    Edit(
        "workflow",
        "- `{project-root}`-prefixed paths resolve from the project working directory.",
        f"- The project root is the repository `{REPO_ROOT}`; repository paths resolve from there.",
        "env",
        "G5: {project-root} is the task repository",
    ),
    Edit(
        "workflow",
        "- Speak in `{{.communication_language}}`, tailor communication to `{{.user_skill_level}}`, and write documents in `{{.document_output_language}}`.",
        "- Write documents in English.",
        "env",
        "G2/G10: language tokens -> English (B1, B2); the skill-level setting has no reader here",
    ),
    # ---- step-01
    Edit(
        "step01",
        "---\n"
        "spec_file: '' # set at runtime once a route resolves it; some HALT branches exit before it is set\n"
        "spec_folder: '' # set at runtime under folder+id dispatch only\n"
        "story_id: '' # set at runtime under folder+id dispatch only\n"
        "followup_pass: '' # set at runtime when a `done` spec is re-dispatched for a follow-up review pass; empty on a first pass\n"
        "---\n"
        "\n",
        "",
        "env",
        "G1: the runtime variables of the dispatch modes (spec_folder, story_id, followup_pass) have no source here; spec_file is set in Route",
    ),
    Edit("step01", LANGUAGE_RULE, LANGUAGE_RULE_PORT, "env", "G2/G10: language tokens -> English"),
    Edit(
        "step01",
        "- **EARLY EXIT** means: stop this step immediately, then read and follow the target file. Return here only if a later step explicitly says to loop back.\n",
        "",
        "env",
        "G1: EARLY EXIT is used only by the dropped resume and dispatch branches",
    ),
    Edit(
        "step01",
        STEP01_DISPATCH,
        STEP01_DISPATCH_PORT,
        "env",
        "G1: existing-spec resume and folder+id dispatch dropped (no spec, spec folder or stories.yaml exists before the run); the intent is the task message",
    ),
    Edit(
        "step01",
        "\nIf the invocation prompt does not contain enough intent to identify what to implement, HALT with status `blocked` and blocking condition `unclear intent`.\n",
        "\n",
        "semantic",
        "D-2: the `unclear intent` HALT deleted (SWE-bench Verified issues are human-screened as well specified); no replacement",
    ),
    Edit(
        "step01",
        STEP01_CONTEXT,
        STEP01_CONTEXT_PORT,
        "env",
        "G1/G3: no planning artifacts, epics or epic-context compilation in the sandbox -> freeform path only; the implementation-artifacts listing kept",
    ),
    Edit(
        "step01",
        "2. Resolve intent from the invocation prompt and loaded artifacts. Do not fantasize or leave open questions. If the intent cannot be resolved, HALT with status `blocked` and the unresolved questions as blocking condition.\n",
        "2. Resolve intent from the invocation prompt and loaded artifacts. Do not fantasize or leave open questions.\n",
        "semantic",
        "D-2: the unresolved-intent HALT deleted; 'do not fantasize or leave open questions' kept",
    ),
    Edit("step01", STEP01_VCS, "", "env", "D-1 (C24a/b): no VCS sanity check -- the sandbox tree is clean and the branch is the task's"),
    Edit("step01", "4. Multi-goal warning.", "3. Multi-goal warning.", "env", "D-1: renumbered after the VCS item"),
    Edit("step01", "5. Route:\n", "4. Route:\n", "env", "D-1: renumbered after the VCS item"),
    Edit("step01", STEP01_ROUTE_DISPATCH, "", "env", "G1: folder+id dispatch route dropped"),
    Edit(
        "step01",
        STEP01_ROUTE,
        STEP01_ROUTE_PORT,
        "env",
        "G5/D-5: spec_file under /tmp/bmad/implementation-artifacts, diff_file fixed at /tmp/bmad/diff/<slug>.diff; the draft-resume and `-2` suffix branches (G1, C28) dropped -- no earlier spec exists",
    ),
    # ---- step-02
    Edit("step02", LANGUAGE_RULE, LANGUAGE_RULE_PORT, "env", "G2/G10: language tokens -> English"),
    Edit(
        "step02",
        "1. Draft resume check. If `{spec_file}` exists with `status: draft`, read it and capture the verbatim `<intent-contract>...</intent-contract>` block as `preserved_intent_contract`. Otherwise `preserved_intent_contract` is empty.\n"
        "2. Investigate codebase.",
        "1. Investigate codebase.",
        "env",
        "G1: draft resume dropped (no earlier spec); items renumbered",
    ),
    Edit("step02", "3. Read `[[bmad-snapshot:spec-template.md]]` fully.", "2. Read `[[bmad-snapshot:spec-template.md]]` fully.", "env", "G1: renumbered"),
    Edit(
        "step02",
        " If `{preserved_intent_contract}` is non-empty, substitute it for the `<intent-contract>` block in your filled spec before writing.",
        "",
        "env",
        "G1: draft resume dropped",
    ),
    Edit("step02", "4. Self-review against READY FOR DEVELOPMENT standard.", "3. Self-review against READY FOR DEVELOPMENT standard.", "env", "G1: renumbered"),
    Edit(
        "step02",
        "5. If intent gaps exist, do not fantasize and do not leave open questions. Multiple defensible readings of the intent that lead to observably different outcomes, with nothing in the intent to select between them, are an intent gap — do not resolve one by picking a reading. HALT with status `blocked`, blocking condition `intent gap`, and include the unanswered questions and evidence gathered.\n"
        "6. Warning check.",
        "4. Warning check.",
        "semantic",
        "D-2: the intent-gap item deleted whole (no replacement, no `## Assumptions`); the warning check renumbered",
    ),
    Edit(
        "step02",
        "- **If the file is missing:** HALT with status `blocked` and blocking condition `planned spec file disappeared before implementation`.\n",
        "",
        "semantic",
        "G12 (D25, 2026-11-10 user): the spec-vanished HALT deleted -- the agent wrote the file in this very trajectory; upstream's guard protects a variable handed between step files, which this run has not",
    ),
    Edit(
        "step02",
        "- **If the spec meets the standard:** set `{spec_file}` frontmatter status to `ready-for-dev`. If the invocation prompt directs a halt after planning (standard phrasing: `Halt after planning.` — accept any clear equivalent), HALT with status `ready-for-dev`; otherwise continue to step 3.",
        "- **If the spec meets the standard:** set `{spec_file}` frontmatter status to `ready-for-dev` and continue to step 3.",
        "env",
        "G1: `Halt after planning.` is a caller's orchestration phrase; the task message never carries it",
    ),
    Edit(
        "step02",
        "If it now meets the standard, apply the **If the spec meets the standard** handling above, including the halt-after-planning check. If it still does not meet the standard, HALT with status `blocked`, blocking condition `spec failed ready-for-development standard`, and include the failing criteria and evidence gathered.",
        "If it now meets the standard, apply the **If the spec meets the standard** handling above. If it still does not meet the standard, set `{spec_file}` frontmatter `status: blocked`, record the blocking condition `spec failed ready-for-development standard` with the failing criteria and evidence gathered under `## Auto Run Result`, and continue to step 3 all the same.",
        "semantic",
        "D-2/G8 (D28): READY failure recorded as `status: blocked` + reason, the run continues to step 3; the one repair-and-re-read kept",
    ),
    # ---- step-03
    Edit("step03", "---\n---\n\n# Step 3: Implement", "# Step 3: Implement", "env", "G5: empty frontmatter of the source file dropped"),
    Edit("step03", LANGUAGE_RULE, LANGUAGE_RULE_PORT, "env", "G2/G10: language tokens -> English"),
    Edit(
        "step03",
        "## PRECONDITION\n\nVerify `{spec_file}` resolves to a non-empty path and the file exists on disk. If empty or missing, HALT with status `blocked` and blocking condition `missing spec_file before implementation`.\n\n",
        "",
        "semantic",
        "G12 (C30, 2026-11-10 user): the spec-exists precondition deleted -- same reason as the step-02 bullet; step 3 starts at INSTRUCTIONS",
    ),
    Edit(
        "step03",
        " If the handoff conflicts with the spec, HALT with status `blocked` and blocking condition `handoff conflicts with spec`, and include both conflicting passages.",
        "",
        "env",
        "D-1 (E5): the handoff is the fixed text below, it cannot conflict with the spec",
    ),
    Edit(
        "step03",
        "{workflow.implementation_handoff}",
        HANDOFF_PORT,
        "env",
        "G7/D-7: the renderer's token replaced by customize.toml's implementation_handoff, followed by how the task tool performs it",
    ),
    Edit(
        "step03",
        "Invoke the subagent **synchronously** and wait for it to return in this same turn — do not background/detach it (`run_in_background`) or end your turn to await a notification (see workflow.md → Subagents). Resume at \"Verify\" only after it returns. If the platform allows, keep the subagent available for re-engagement after it returns — step-04 may send it review fixes.",
        "Invoke the subagent **synchronously** and wait for it to return in this same turn — do not background/detach it or end your turn to await a notification (see core-workflow.md → Subagents). Resume at \"Verify\" only after it returns. The subagent stays available for re-engagement after it returns — step-04 may send it review fixes through `task` with `resume` set to its Task ID.",
        "env",
        "G5/D-7: workflow.md -> core-workflow.md; the task tool has no background option; re-engagement = `resume`",
    ),
    Edit(
        "step03",
        " — untracked files included — to a uniquely-named file in the system temp directory, set `{diff_file}` to its absolute path, and read that file into your own context.",
        f" — untracked files included — to `{{diff_file}}` (`{DIFF_FILE}`, set in step-01; create the directory if needed) and read that file into your own context.",
        "env",
        "D-5: the diff file at a fixed path the rubric can read",
    ),
    Edit(
        "step03",
        "If verification fails and the failure cannot be fixed, HALT with status `blocked`, blocking condition `implementation verification failed`, and include the failing command or check and reason.",
        "If verification fails and the failure cannot be fixed, set `{spec_file}` frontmatter `status: blocked`, record the blocking condition `implementation verification failed` with the failing command or check and reason under `## Auto Run Result`, and continue.",
        "semantic",
        "D-2/G8 (F2): verification failure recorded, the run continues",
    ),
    Edit(
        "step03",
        "fix the code, or if the matrix row itself is ambiguous, HALT with status `blocked` and blocking condition `matrix ambiguity`. If the audit cannot otherwise be satisfied, HALT with status `blocked` and blocking condition `matrix test audit failed`.",
        "fix the code. If the audit cannot otherwise be satisfied, set `{spec_file}` frontmatter `status: blocked`, record the blocking condition `matrix test audit failed` with the uncovered rows under `## Auto Run Result`, and continue.",
        "semantic",
        "D-2 (F7): the `matrix ambiguity` HALT deleted; D-2/G8 (F8): audit failure recorded, the run continues",
    ),
    # ---- step-04
    Edit("step04", LANGUAGE_RULE, LANGUAGE_RULE_PORT, "env", "G2/G10: language tokens -> English"),
    Edit(
        "step04",
        "Otherwise use the repository's version-control tooling to rewrite `{diff_file}` — the temp file staged in step-03, or a uniquely-named file in the system temp directory when this run has none — with a unified diff",
        f"Otherwise use the repository's version-control tooling to rewrite `{{diff_file}}` (`{DIFF_FILE}`, staged in step-03) with a unified diff",
        "env",
        "D-5: the diff file at its fixed path; a run always has one (no resumed review)",
    ),
    Edit(
        "step04",
        " `{verbatim_intent}` is the invocation intent exactly as this run received it at step-01; if the run started from an existing spec file rather than a fresh intent, it is the spec's `<intent-contract>` block instead. Before launching a layer, expand its skill-root placeholder to this skill's absolute installed directory; never leave that placeholder unresolved in a child prompt.",
        " `{verbatim_intent}` is the invocation intent exactly as this run received it at step-01.",
        "env",
        "G1/G5: no existing-spec start; the skill-root placeholder is already the absolute document path",
    ),
    Edit(
        "step04",
        "Announce skipped layers first, then launch every active layer before handling any layer's result. Try running all active layers simultaneously: substitute the runtime placeholders (e.g. `{diff_file}`) into each layer's instruction. When an instruction launches a reviewer subagent, launch that child with the prompt text after placeholder substitution; do not load the reviewer instruction file yourself. For any other customized instruction, execute it as written. Parallel means several blocking calls awaited together in this turn — never backgrounded or detached, never ending the turn to await results (see workflow.md → Subagents). Spawn every reviewer subagent before reading or reacting to any of their output; begin collection and triage only once all are launched.",
        "Launch every active layer before handling any layer's result. Try running all active layers simultaneously: substitute the runtime placeholders (e.g. `{diff_file}`) into each layer's instruction. When an instruction launches a reviewer subagent, launch that child with the prompt text after placeholder substitution; do not load the reviewer instruction file yourself. Parallel means several blocking calls awaited together in this turn — never backgrounded or detached, never ending the turn to await results (see core-workflow.md → Subagents): four `task` calls in one assistant turn, one per layer, each with `prompt` = that layer's substituted text. Spawn every reviewer subagent before reading or reacting to any of their output; begin collection and triage only once all are launched.",
        "env",
        "G7/D-7: no layer is skipped or customized (the four defaults are the layers); the launch mapped to four task calls in one turn",
    ),
    Edit(
        "step04",
        "{workflow.review_layers}",
        format_review_layers(),
        "env",
        "G7: the renderer's token replaced by customize.toml's four review layers, formatted as render_skill.py does",
    ),
    Edit(
        "step04",
        "If `## Review Triage Log` already has rows — a loopback, a resumed review, or a follow-up pass on a `done` spec — check each finding against them first.",
        "If `## Review Triage Log` already has rows — a loopback — check each finding against them first.",
        "env",
        "G1: a resumed review or a follow-up pass needs an earlier spec, which never exists here",
    ),
    Edit(
        "step04",
        "so it routes to intent_gap or bad_spec, never to patch or defer.",
        "so it routes to bad_spec, never to patch or defer.",
        "semantic",
        "D-2 (G68): the intent_gap route no longer exists",
    ),
    Edit(
        "step04",
        "The first three are **this story's problem** — caused or exposed by the current change. The last is **not this story's problem**.\n"
        "   - **intent_gap** — caused by the change; cannot be resolved from the spec because the captured intent is incomplete. Do not infer intent unless there is exactly one possible reading.\n",
        "The first two are **this story's problem** — caused or exposed by the current change. The last is **not this story's problem**.\n",
        "semantic",
        "D-2 (G72): the intent_gap category deleted",
    ),
    Edit(
        "step04",
        "A finding whose smallest fix fails any of those conditions routes to intent_gap when the spec does not settle that fix, otherwise to bad_spec.",
        "A finding whose smallest fix fails any of those conditions routes to bad_spec.",
        "semantic",
        "D-2 (G74): the intent_gap branch of the patch definition deleted",
    ),
    Edit(
        "step04",
        "`[intent_gap|bad_spec|patch|defer|reject]`",
        "`[bad_spec|patch|defer|reject]`",
        "semantic",
        "D-2 (G77): the route label removed from the triage-log row format",
    ),
    Edit(
        "step04",
        "5. Process entries in cascading order. If intent_gap exists, lower entries are moot; follow the intent_gap branch below. If bad_spec exists, lower entries are moot since code will be re-derived. If neither exists, process patch and defer normally.",
        "5. Process entries in cascading order. If bad_spec exists, lower entries are moot since code will be re-derived. Otherwise process patch and defer normally.",
        "semantic",
        "D-2 (G81): the intent_gap stage of the cascade removed",
    ),
    Edit(
        "step04",
        "If it exceeds 5, append the triage-log entry for this pass, then HALT with status `blocked` and blocking condition `review repair loop exceeded 5 iterations (non-convergence)`.",
        "If it exceeds 5, append the triage-log entry for this pass, set `{spec_file}` frontmatter `status: blocked`, record the blocking condition `review repair loop exceeded 5 iterations (non-convergence)` under `## Auto Run Result`, and go to Finalize without another loopback.",
        "semantic",
        "D-2/G8 (G83): the loop cap (D-4: 5, kept) ends the loop and is recorded; the run goes on to Finalize",
    ),
    Edit(
        "step04",
        "   - **intent_gap** — Root cause is inside `<intent-contract>`. Save the attempted change as a patch file in `{{.implementation_artifacts}}` and reference it from the triage-log entry, then revert code changes. Append the triage-log entry for this pass, then HALT with status `blocked`, blocking condition `intent gap`, and include the unresolved questions and the saved patch path.\n",
        "",
        "semantic",
        "D-2 (G84a-c): the intent_gap route (patch file, revert, HALT) deleted",
    ),
    Edit(
        "step04",
        "Re-engage the step-03 implementation subagent — the same one, addressed by the name or id its launch returned; a fresh launch is not re-engagement. Send it one message, exactly this, with the findings filled in:",
        "Re-engage the step-03 implementation subagent — the same one, addressed by the name or id its launch returned (a `task` call with `resume` = that subagent's Task ID and `prompt` = the message below); a fresh launch is not re-engagement. Send it one message, exactly this, with the findings filled in:",
        "env",
        "D-7 (G86a): re-engagement = the task tool's `resume`",
    ),
    Edit(
        "step04",
        "if verification fails and the failure cannot be fixed, HALT with status `blocked` and blocking condition `patch verification failed`.",
        "if verification fails and the failure cannot be fixed, set `{spec_file}` frontmatter `status: blocked` and record the blocking condition `patch verification failed` with the failing command or check under `## Auto Run Result`.",
        "semantic",
        "D-2/G8 (F10): patch verification failure recorded, the pass is finished as written",
    ),
    Edit(
        "step04",
        " On a first pass, `true` if any patched entry was `high`, or if two or more `medium` entries were patched. On a follow-up pass (`{followup_pass}` = `true`), `true` only if this pass patched a `high` — otherwise the work has converged; patch volume is never grounds.",
        " `true` if any patched entry was `high`, or if two or more `medium` entries were patched.",
        "env",
        "G1: every run is a first pass (a follow-up pass re-dispatches a `done` spec, which never exists here)",
    ),
    Edit(
        "step04",
        STEP04_FINALIZE,
        STEP04_FINALIZE_PORT,
        "semantic",
        "D-1 (H7, H8, H10): no commit and no clean-tree check -- the working tree is what the grader reads; D-2: a recorded `blocked` status is the final status",
    ),
    # ---- review-prompts/edge-case-hunter.md
    Edit(
        "edge",
        "load `references/deletion-check.md` and follow it.",
        f"load `{DOCS_ROOT}/references/deletion-check.md` and follow it.",
        "env",
        "G5: the reference is read from the uploaded documents (the subagent has no skill directory)",
    ),
    Edit(
        "edge",
        "Load `references/claims-check.md` and follow it.",
        f"Load `{DOCS_ROOT}/references/claims-check.md` and follow it.",
        "env",
        "G5: same",
    ),
    Edit(
        "edge",
        "with the extra fields defined in `references/deletion-check.md` and `references/claims-check.md`.",
        f"with the extra fields defined in `{DOCS_ROOT}/references/deletion-check.md` and `{DOCS_ROOT}/references/claims-check.md`.",
        "env",
        "G5: same",
    ),
)

SECTIONS: tuple[Section, ...] = (
    Section(
        "workflow",
        "## HALT",
        HALT_SECTION,
        "env",
        "G1/G7: the folder+id write-back and the on_complete hook (empty upstream) dropped; the plain branch kept with the result file under /tmp/bmad/implementation-artifacts",
    ),
    Section(
        "workflow",
        "## On Activation",
        SETTING_SECTION,
        "semantic",
        "G7: the activation hooks (all `_None._`) dropped; in their place the run's setting -- G1/G3 (the intent, no planning artifacts), G5 (paths outside the repo), D-7 (the task tool), D-2 (record-and-continue), D-1 (no commit; the working tree is graded), G2 (reading order, end)",
    ),
)

SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    ("[[bmad-snapshot:workflow.md]]", ENTRY_DOC),
    ("[[bmad-snapshot:spec-template.md]]", f"{DOCS_ROOT}/spec-template.md"),
    *((f"[[bmad-snapshot:{f}]]", f"{STAGES_DIR}/{f}") for f in STEP_FILES),
    ("{skill-root}", DOCS_ROOT),
    ("{{.implementation_artifacts}}", IMPLEMENTATION_ARTIFACTS),
    ("{project-root}", REPO_ROOT),
)

# Left in an output, these mean an edit missed a case.
FORBIDDEN: tuple[str, ...] = (
    "uv run",
    "render_skill",
    "{project-root}",
    "{skill-root}",
    "{{.",
    "{workflow.",
    "bmad-snapshot",
    "_None._",
    "activation_steps",
    "persistent_facts",
    "on_complete",
    "compile-epic-context",
    "{epic_num}",
    "epic-",
    "Epic ",
    "stories.yaml",
    "{spec_folder}",
    "{story_id}",
    "{followup_pass}",
    "follow-up pass",
    "folder+id",
    "EARLY EXIT",
    "preserved_intent_contract",
    "Halt after planning",
    "unclear intent",
    "intent gap",
    "intent_gap",
    "matrix ambiguity",
    "no subagents",
    "git add --refresh",
    "Commit any",
    "finalization left repository dirty",
    "system temp directory",
    "Announce skipped layers",
    "customized instruction",
    "skill-root placeholder",
    "handoff conflicts with spec",
    "user_skill_level",
    "snapshot path",
    "snapshot file",
    "## Assumptions",
    "delegate",
    "spawn with",
)

PORT = Port(
    sources=SOURCES,
    out_dir=OUT_DIR,
    upstream_commit=UPSTREAM_COMMIT,
    sections=SECTIONS,
    edits=EDITS,
    substitutions=SUBSTITUTIONS,
    forbidden=FORBIDDEN,
    frontmatter=False,  # workflow.md has none, step-03's is empty, spec-template's is content: handled by edits
)


def convert(key: str, upstream: str) -> str:
    """One document from its upstream text."""
    return _convert(PORT, key, upstream)


def build(upstream: Path) -> dict[str, str]:
    """Output path (relative to ``docs/``) -> text; fails when customize.toml differs from the embedded values."""
    check_customization(upstream)
    return _build(PORT, upstream)


def expected_outputs() -> set[str]:
    return {out for _, out in SOURCES.values()}


def _strays() -> list[str]:
    present = {p.relative_to(OUT_DIR).as_posix() for p in OUT_DIR.rglob("*") if p.is_file()}
    return sorted(present - expected_outputs())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--upstream", dest="upstream", type=Path, help="BMAD-METHOD checkout")
    ap.add_argument("--check", action="store_true", help="compare with the committed documents instead of writing")
    ap.add_argument("--list", action="store_true", help="print the edits by tag")
    args = ap.parse_args(argv)
    if args.list:
        list_edits(PORT)
        print("[substitutions] (the renderer's tokens; untagged)")
        for old, new in SUBSTITUTIONS:
            print(f"  {old} -> {new}")
        print(f"[inlined] {CUSTOMIZE_TOML}: implementation_handoff -> step-03, review_layers ({', '.join(LAYER_IDS)}) -> step-04")
        return 0
    if args.upstream is None:
        ap.error("--upstream is required")
    commit = _git_head(args.upstream)
    if commit != UPSTREAM_COMMIT:
        print(f"warning: upstream at {commit}, documents pinned to {UPSTREAM_COMMIT}", file=sys.stderr)
    built = build(args.upstream)
    rc = 0
    if args.check:
        for name in _drift(PORT, built):
            print(f"drift: docs/{name}", file=sys.stderr)
            rc = 1
    else:
        for name, text in built.items():
            dest = OUT_DIR / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")
            print(f"wrote docs/{name} ({text.count(chr(10))} lines)")
    for name in _strays():
        print(f"{'drift' if args.check else 'warning'}: stray file docs/{name} (not a build output)", file=sys.stderr)
        rc = 1 if args.check else rc
    return rc


if __name__ == "__main__":
    sys.exit(main())
