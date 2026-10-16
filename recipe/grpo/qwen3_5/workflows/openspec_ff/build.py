"""Build ``docs/stages/`` and the forked schema from an OpenSpec checkout (Fission-AI/OpenSpec).

    python -m recipe.grpo.qwen3_5.workflows.openspec_ff.build --upstream /path/to/OpenSpec
    python -m recipe.grpo.qwen3_5.workflows.openspec_ff.build --upstream ... --check   # exit 1 on drift
    python -m recipe.grpo.qwen3_5.workflows.openspec_ff.build --list                   # the edits, by tag

Two outputs, one ``_port.Port`` each:

``STAGES``  the four OPSX skills the chain explore -> ff -> apply -> verify uses
            (``skills/openspec-explore/SKILL.md`` and ``skills/openspec-<x>-change/SKILL.md``, the committed
            renders) -> ``docs/stages/00-explore.md`` (G5-4) and ``0N-<x>.md``, uploaded to ``/opsx/stages/``.
            Archive is the CLI's ``openspec archive issue --yes``, so the archive and sync skills are not
            shipped (porting/03-decisions.md D-5). explore keeps one sentence with "ask the user" verbatim
            (G4-14): ``FORBIDDEN_ALLOWED`` exempts that one occurrence in that one source only.
``FORK``    ``schemas/spec-driven/`` (``schema.yaml`` + four templates) -> ``sandbox/schemas/spec-driven-sandbox/``,
            what ``openspec schema fork spec-driven spec-driven-sandbox`` writes (the ``name:`` set and the
            yaml library's ``[ tasks ]`` spacing; checked against the CLI 1.14.1 output) plus the decided
            edits. The setup step copies it to ``/openspec/schemas/`` and selects it in ``config.yaml``
            (D-4): the CLI serves the per-artifact instructions from it, so the text the agent gets from
            ``openspec instructions`` is changed here and nowhere else.

The other text the agent meets -- status, paths, validation, apply state, archive -- comes from the
real CLI as upstream ships it (D-1). ``docs/core-workflow.md`` (hand-written) strings the stages together.

Tags: ``env`` closes a gap between OpenSpec's setting (a person typing ``/opsx:*`` commands in an agent
app) and one unattended session without changing what is asked; ``semantic`` changes what is asked.
Every note starts with the gap ID of ``porting/02-gaps.md`` / ``03-decisions.md``. An anchor that does not occur exactly once fails the
build, so an upstream rewording surfaces here. The engine is ``workflows/_port.py``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .._port import Edit, Port, Section, list_edits
from .._port import build as _build
from .._port import convert as _convert
from .._port import drift as _drift
from .._port import git_head as _git_head

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "docs" / "stages"
FORK_NAME = "spec-driven-sandbox"
FORK_DIR = HERE / "sandbox" / "schemas" / FORK_NAME

# What both outputs were built from (npm @fission-ai/openspec 1.14.1). Another commit only warns.
UPSTREAM_COMMIT = "9111a7654d7800391459431fff4eaf66e33a3d2e"

CHANGE_DIR = "/openspec/changes/issue/"
STAGE_DOCS = {
    "explore": "/opsx/stages/00-explore.md",  # G5-4: added in front, 01-03 not renumbered
    "ff": "/opsx/stages/01-ff.md",
    "apply": "/opsx/stages/02-apply.md",
    "verify": "/opsx/stages/03-verify.md",
}
ENTRY_DOC = "/opsx/core-workflow.md"

SOURCES: dict[str, tuple[str, str]] = {
    "explore": ("skills/openspec-explore/SKILL.md", "00-explore.md"),
    "ff": ("skills/openspec-ff-change/SKILL.md", "01-ff.md"),
    "apply": ("skills/openspec-apply-change/SKILL.md", "02-apply.md"),
    "verify": ("skills/openspec-verify-change/SKILL.md", "03-verify.md"),
}

FORK_SOURCES: dict[str, tuple[str, str]] = {
    "schema": ("schemas/spec-driven/schema.yaml", "schema.yaml"),
    **{f"tpl-{t}": (f"schemas/spec-driven/templates/{t}.md", f"templates/{t}.md") for t in ("proposal", "spec", "design", "tasks")},
}

# Left in a stage document, these mean an edit missed a case.
FORBIDDEN = (
    "ask the user",
    "Ask the user",
    "ask what they want",
    "ask for clarification",
    "ask for a valid name",
    "ask me to",
    "pause and ask",
    "wait for guidance",
    "What would you like to do?",
    "STOP and wait",
    "/openspec-",
    "**Store selection:**",
    "openspec store list",
    "suggest continuing that change",
    "Output On Pause",
    "MUST prompt",
    "When prompting",
    "verify-2.md",
    # explore (G4-13, G4-17, G4-18, G7-10, G2-12)
    "Want me to",
    "yes/no question",
    "Where's your head at?",
    "Which one's burning?",
    "What's the context?",
    "capture the exploration",
    "Don't manually scaffold",
    "this summary is optional",
)

# Sentences a source keeps verbatim although they contain a FORBIDDEN string. Each must occur exactly once
# in that source's output; only that occurrence is exempt, and every other source is checked in full.
FORBIDDEN_ALLOWED: dict[str, tuple[str, ...]] = {
    # G4-14: explore:48's prohibition is kept as upstream wrote it.
    "explore": ("Do not ask the user to repeat facts you can verify.",),
}

# Left in the forked schema, these mean an edit missed a case.
FORK_FORBIDDEN = (
    "ask the user",
    "resolve them with the user",
    "Pause if you hit blockers",
    "land the tests",
    "package.json",
    "docs/export.md",
    "verify unit tests cover",
    "name: spec-driven\n",
)

_STORE = (
    "**Store selection:** If the user names a store (a store is a standalone OpenSpec repo registered on this machine) "
    "or the work lives in one, run `openspec store list --json` to discover registered store ids, then pass "
    "`--store <id>` on the commands that read or write specs and changes (`new change`, `status`, `instructions`, "
    "`list`, `show`, `validate`, `archive`, `doctor`, `context`, `schemas`, `view`). Once selected, treat "
    "`--store <id>` as sticky for the rest of the workflow. Every unscoped example of those commands below is "
    'shorthand: before running it, append the flag. For example, run `openspec status --change "<name>" --json '
    '--store "<id>"`, not the unscoped form shown below. Other commands do not take the flag. Hints printed by '
    "commands already carry the flag; keep it on follow-ups. Without a store, commands act on the nearest local "
    "`openspec/` root.\n\n"
)

_ASK_INPUT = (
    "1. **If no clear input provided, ask what they want to build**\n\n"
    "   Ask the user (open-ended, no preset options):\n"
    '   > "What change do you want to work on? Describe what you want to build or fix."\n\n'
    "   From their description, derive a kebab-case name (e.g., \"add user authentication\" → `add-user-auth`).\n\n"
    "   **IMPORTANT**: Do NOT proceed without understanding what the user wants to build."
)

_INPUT_UPSTREAM = (
    "**Input**: The user's request should include a change name (kebab-case) OR a description of what they want to build."
)
_INPUT_ISSUE = (
    "**Input**: The issue in the task message, between `<issue_description>` and `</issue_description>`: what to "
    "build or fix. The change name is fixed: `issue`."
)

_SELECT_ASK = "   - If ambiguous, run `openspec list --json` to get available changes and ask the user to select one\n"

# explore (skills/openspec-explore/SKILL.md -> 00-explore.md): porting/03-decisions.md "Explore extension".
# The capture transition and "When a change exists" go as sections (EXPLORE_SECTIONS, G4-17).
EXPLORE_EDITS: tuple[Edit, ...] = (
    Edit(
        "explore",
        "Enter explore mode. Think deeply. Visualize freely. Follow the conversation wherever it goes.\n",
        "Enter explore mode. Think deeply. Visualize freely. Follow the conversation wherever it goes.\n\n"
        "**Input**: The issue in the task message, between `<issue_description>` and `</issue_description>`: "
        "the problem to understand. It is the source material for this exploration; nobody will add to it.\n",
        "env",
        "G1-4: input = the issue (upstream's \"User brings a specific problem\")",
    ),
    Edit(
        "explore",
        "but you must NEVER write code or implement features. ",
        "but you must NEVER write code or implement features. Here a read-only command is one that runs only "
        "what already exists and writes no file: reading, searching, running existing code and existing tests, "
        "and running the issue's own example exactly as given. Code you compose yourself is writing code, a "
        "one-line `python -c` or a snippet piped to stdin included, and so is any file write (in the "
        f"repository, in `/tmp`, under `{CHANGE_DIR}checks/`, by shell redirection or heredoc). Files a run "
        "leaves behind by itself, such as `__pycache__` or `.pytest_cache`, are not your writes. Varying the "
        "issue's example is left to ff and apply, which keep their scripts under `checks/`. ",
        "semantic",
        "G9-5: the read-only boundary, \"NEVER write code\" taken literally (composed snippets included)",
    ),
    Edit(
        "explore",
        "If the user asks you to implement something, do not start it here: say that explore mode does not "
        "implement, and point them at `/openspec-propose`, which turns the discussion into a change. The work "
        "happens from that change, never from explore mode.",
        "The task asks you to implement a fix; that request is carried out later in this session by the ff and "
        "apply actions, not here: do not start it in explore mode. The work happens from the change ff creates, "
        "never from explore mode.",
        "env",
        "G4-16/G2-10: the task's own request to implement goes to ff -> apply, no refusal in words",
    ),
    Edit(
        "explore",
        "You MAY create or update OpenSpec change artifacts (proposals, designs, specs) within a confirmed "
        "scope—that's capturing thinking, not implementing. Answering design or clarifying questions is never "
        "consent to write. Before the first write-capable action, name the artifacts or files you would change "
        "and what you would do, ask a direct yes/no question, and wait for the user's confirmation in a "
        "separate message. Confirmation covers only the scope you described; ask again before expanding it. An "
        "explicit request from the user to capture the exploration as a new change is itself that "
        "confirmation, covering the change and the change artifacts the request names; scaffold it first as "
        "described below.",
        "In this session explore writes nothing, change artifacts included: the ff action creates the change "
        "and writes its artifacts from what you found here.",
        "semantic",
        "G4-13: explore writes nothing; the yes/no write question and the capture request dropped",
    ),
    Edit(
        "explore",
        "There are no fixed steps, no required sequence, no mandatory outputs.",
        "There are no fixed steps and no required sequence. The one required output is the summary under "
        "**Ending Discovery**, written when exploration is done.",
        "semantic",
        "G2-12/G8-6: the summary is the one mandatory output",
    ),
    Edit(
        "explore",
        "When the user is planning a change, guide them toward shared understanding with focused discovery "
        "questions. For open-ended discussion, follow the conversation without imposing an interview or a "
        "required output.",
        "Here the issue is the planned change, and nobody answers questions: work toward shared understanding "
        "by putting focused discovery questions to the issue, the code and the tests. A question only the "
        "person could answer (intent, priorities, scope the issue leaves open) gets no reply: take the most "
        "plausible reading of the issue, mark it as an **assumption** (not as confirmed intent) in your "
        "summary, and continue; ff writes it into the proposal.",
        "semantic",
        "G4-14: discovery questions go to the evidence; person-only questions become assumptions",
    ),
    Edit(
        "explore",
        "- **Keep questions focused** - Ask one focused question at a time, and briefly explain why it matters "
        "and which decision it unlocks. Batch questions only if the user asks for a batch; keep them small and "
        "group related decisions.",
        "- **Keep questions focused** - Take one focused question at a time, and note why it matters and which "
        "decision it unlocks; settle it from the evidence or record it as an assumption.",
        "semantic",
        "G4-14: one question at a time, settled or assumed instead of asked",
    ),
    Edit(
        "explore",
        "Do not invent intent, priorities, or external constraints: ask the user when only they can answer.",
        "Do not invent intent, priorities, or external constraints: when only the person could answer, record "
        "the most plausible reading of the issue as an assumption, not as confirmed intent.",
        "semantic",
        "G4-14: person-only question -> assumption",
    ),
    Edit(
        "explore",
        "Separate confirmed decisions from proposed defaults and unresolved questions. Silence is not "
        "acceptance. Accepting an answer or a batch of recommendations is not permission to write. Keep "
        "file-write confirmation separate from discovery questions and follow the guardrails below.",
        "Separate what the issue and the code confirm from assumptions, proposed defaults and unresolved "
        "questions; the summary under **Ending Discovery** carries them to ff. Write no file (see the "
        "guardrails below).",
        "semantic",
        "G2-12/G4-13/G4-14: the record goes into the summary; the write-confirmation sentences dropped",
    ),
    Edit(
        "explore",
        "Stop asking when the user has enough clarity. Let them pause, pivot, or defer a decision; do not "
        "exhaust every branch or force a proposal.",
        "Stop once the problem and where the change goes can be stated with evidence (see **Ending "
        "Discovery**); a decision the evidence cannot settle stays an open question for ff. Do not exhaust "
        "every branch.",
        "semantic",
        "G8-6/G4-15: the end condition in place of the person's clarity; deferring is an open question",
    ),
    Edit(
        "explore",
        "The CLI already uses SQLite and has no remote service. Is sharing state\n"
        "across devices in scope? That determines whether local storage is enough.\n"
        "If this stays a single-device tool, I recommend keeping SQLite to avoid\n"
        "adding a service to operate; shared state would need a separate sync design.\n",
        "The CLI already uses SQLite and has no remote service. Nothing in the issue\n"
        "or the code needs state shared across devices, so I assume a single-device\n"
        "tool (assumption, with that evidence). On that reading I recommend keeping\n"
        "SQLite; if the assumption is wrong, shared state needs a separate sync design.\n",
        "semantic",
        "G4-19: the example's scope question becomes an assumption from evidence (decided wording)",
    ),
    Edit(
        "explore",
        "- Ask clarifying questions that emerge from what they said\n",
        "- Raise the clarifying questions the issue leaves open, and settle each from the code or record it as "
        "an assumption\n",
        "semantic",
        "G4-14: clarifying questions settled or assumed",
    ),
    Edit(
        "explore",
        "- Recommend a path (if asked)\n",
        "- Recommend a path, with the alternatives and why\n",
        "semantic",
        "G4-15: the agent states its preferred option with alternatives (nobody asks)",
    ),
    Edit(
        "explore",
        "- Suggest spikes or investigations\n",
        "- Turn a spike or investigation you would suggest into a specific open question for ff's discovery "
        "to settle\n",
        "semantic",
        "G4-15: a suggested spike -> a specific open question for ff (ff:78)",
    ),
    Edit(
        "explore",
        "- Reach a conclusion\n",
        "- Settle every open question (the problem and where the change goes do need evidence; see **Ending "
        "Discovery**)\n",
        "semantic",
        "G8-6: open questions may stay open, the end condition does not",
    ),
    Edit(
        "explore",
        "**User brings a vague idea:**\n"
        "```\n"
        "User: I'm thinking about adding real-time collaboration\n"
        "\n"
        "You: Real-time collab is a big space. Let me think about this...\n"
        "\n"
        "      COLLABORATION SPECTRUM\n"
        "      ============================================\n"
        "\n"
        "      Awareness          Coordination         Sync\n"
        "          |                   |                 |\n"
        "          v                   v                 v\n"
        "      +--------+         +--------+        +--------+\n"
        "      |Presence|         |Cursors |        |  CRDT  |\n"
        '      |  "3    |         | Multi  |        |Conflict|\n'
        '      |online" |         | select |        |  free  |\n'
        "      +--------+         +--------+        +--------+\n"
        "          |                   |                 |\n"
        "       trivial            moderate           complex\n"
        "\n"
        "      Where's your head at?\n"
        "```\n\n",
        "",
        "semantic",
        "G4-18: vague-idea example dropped (ends on a question to the person)",
    ),
    Edit(
        "explore",
        "     I see three tangles. Which one's burning?\n",
        "     I see three tangles. [traces each against the issue until the problem and\n"
        "     where the change goes are clear, then writes the summary from Ending\n"
        f"     Discovery and opens {STAGE_DOCS['ff']} in the same turn]\n",
        "semantic",
        "G4-18/G2-12: the kept example's closing question becomes the summary and the hand-off to ff",
    ),
    Edit(
        "explore",
        "**User is stuck mid-implementation:**\n"
        "```\n"
        "User: /openspec-explore add-auth-system\n"
        "      The OAuth integration is more complex than expected\n"
        "\n"
        "You: [reads change artifacts]\n"
        "\n"
        '     You\'re on task 4: "Implement OAuth flow"\n'
        "\n"
        "     Let me trace what's involved...\n"
        "\n"
        "     [draws diagram, explores options, suggests paths]\n"
        "\n"
        "     Want to update the design to reflect this?\n"
        "     Or add a spike task to investigate?\n"
        "```\n\n",
        "",
        "env",
        "G4-17: mid-implementation example dropped (no change exists before ff)",
    ),
    Edit(
        "explore",
        "**User wants to compare options:**\n"
        "```\n"
        "User: Should we use Postgres or SQLite?\n"
        "\n"
        "You: Generic answer is boring. What's the context?\n"
        "\n"
        "User: A CLI tool that tracks local dev environments\n"
        "\n"
        "You: That changes everything.\n"
        "\n"
        "     +-------------------------------------------------+\n"
        "     |          CLI TOOL DATA STORAGE                  |\n"
        "     +-------------------------------------------------+\n"
        "\n"
        "     Key constraints:\n"
        "     - No daemon running\n"
        "     - Must work offline\n"
        "     - Single user\n"
        "\n"
        "                  SQLite          Postgres\n"
        "     Deployment   embedded        needs server\n"
        "     Offline      yes             no\n"
        "     Single file  yes             no\n"
        "\n"
        "     SQLite. Not even close.\n"
        "\n"
        "     Unless... is there a sync component?\n"
        "```\n",
        "",
        "semantic",
        "G4-18: compare-options example dropped (a dialog of questions to the person)",
    ),
    Edit(
        "explore",
        "There's no required ending. Discovery might:\n"
        "\n"
        '- **Flow into a proposal**: "Ready to start? Run `/openspec-propose` and this becomes a change."\n'
        '- **Result in artifact updates**: "Updated design.md with these decisions"\n'
        "- **Just provide clarity**: User has what they need, moves on\n"
        '- **Continue later**: "We can pick this up anytime"\n',
        "Here discovery has one ending: it flows into the ff action. Exploration is done once the summary "
        "below can state **The problem** and **Where the change goes**, each with its evidence; **Open "
        f"questions** may stay open. Then open `{STAGE_DOCS['ff']}` and continue: ff turns what you found "
        "into a change.\n",
        "semantic",
        "G8-6/G2-10: one ending (into ff) and its condition; the other three endings need a person",
    ),
    Edit(
        "explore",
        "When it feels like things are crystallizing, you might summarize:\n",
        f"When exploration is done, write this summary inside a tool call (the `think` tool, for example) "
        f"before the tool call that opens `{STAGE_DOCS['ff']}`; a message without a tool call ends the "
        "session. Back every entry with its evidence: the `file:line` you read, the command you ran and what "
        "it printed.\n",
        "semantic",
        "G2-12/G2-11/G2-14: the summary always, with evidence, in a tool call before ff is opened",
    ),
    Edit(
        "explore",
        "**The problem**: [crystallized understanding]\n"
        "\n"
        "**The approach**: [if one emerged]\n"
        "\n"
        "**Open questions**: [if any remain]\n"
        "\n"
        "**Next steps** (if ready):\n"
        "- Turn this into a change: `/openspec-propose`\n"
        "- Keep exploring: just keep talking\n",
        "**The problem**: [crystallized understanding, with evidence]\n"
        "\n"
        "**How the area works**: [the code path involved, with evidence]\n"
        "\n"
        "**Where the change goes**: [preferred option and why; alternatives and their tradeoffs]\n"
        "\n"
        "**Assumptions**: [readings of the issue only the person could have confirmed]\n"
        "\n"
        "**Open questions**: [if any remain, each specific enough for ff's discovery to settle]\n"
        "\n"
        f"**Next step**: open {STAGE_DOCS['ff']} - ff turns this into a change\n",
        "semantic",
        "G2-12/G2-10/G4-15: the summary's fields (docs/existing-projects.md:51-57) and the hand-off to ff",
    ),
    Edit(
        "explore",
        "But this summary is optional. Sometimes the thinking IS the value.",
        "Here the summary is required: ff builds the proposal's Why and the design's Context and Decisions "
        "(choice, rationale, alternatives) on it, and writes your assumptions into the proposal.",
        "semantic",
        "G2-12/G4-15: the summary is what ff grounds the proposal and design in",
    ),
    Edit(
        "explore",
        "Creating or updating OpenSpec change artifacts within the confirmed scope is fine, writing anything "
        "else is not.",
        "In this session explore writes no change artifact either; ff creates them. Running code you composed "
        "is writing code too, whether as `python -c \"...\"` or as a heredoc piped to `python3`: when you want "
        "to try a variant of the issue's example, record it as an open question for ff instead.",
        "semantic",
        "G4-13/G9-6: explore writes nothing; composed code named as writing code in the guardrail",
    ),
    Edit(
        "explore",
        "When the user is ready to build, name the handoff rather than starting: `/openspec-propose` turns "
        "the discussion into a change, and the work happens there.",
        f"When exploration is done, open `{STAGE_DOCS['ff']}` rather than starting to build: ff turns what you "
        "found into a change, and the work happens there.",
        "env",
        "G4-16/G2-10: hand-off to ff in place of naming propose (decided wording)",
    ),
    Edit(
        "explore",
        "- **Don't auto-capture** - Offer to save insights, don't just do it. Read-only commands and tools need "
        "no confirmation. Before the first write-capable action—including `openspec new change` or another "
        "command that writes files—name the artifacts or files and proposed changes, ask a direct yes/no "
        "question, and wait for explicit confirmation in a separate user message. That confirmation covers "
        "only the described scope; ask again before expanding it. Answers to design or clarifying questions "
        "are never consent to write. That rule governs `openspec new change` whenever you are the one "
        "proposing the capture; the user's own capture request is the exception, handled in the capture "
        "transition above.",
        "- **Don't auto-capture** - Do not save insights to files: nothing is captured during explore, and "
        "`openspec new change` is ff's first command. Read-only commands and tools, as bounded at the top, "
        "need no confirmation; a command that writes files is not one of them.",
        "semantic",
        "G4-13/G9-5: no offer, no yes/no write question; the change is ff's",
    ),
    Edit(
        "explore",
        '- **Don\'t manually scaffold changes** - Never create a new change directory under `openspec/changes/` '
        'by hand. Always use `openspec new change "<name>"` (with `--store <id>` when applicable) so required '
        "metadata such as `.openspec.yaml` is created before writing artifacts.\n",
        "",
        "env",
        "G7-10: scaffolding guardrail dropped with the capture text (explore never scaffolds)",
    ),
)

EXPLORE_SECTIONS: tuple[Section, ...] = (
    Section("explore", "### When no change exists", None, "env", "G4-17/G4-13: capture transition and its offer dropped", level=3),
    Section("explore", "### When a change exists", "---\n", "env", "G4-17: no change exists before ff; the section separator kept", level=3),
)

EDITS: tuple[Edit, ...] = (
    # ------------------------------------------------------------------ all four
    *(Edit(s, _STORE, "", "env", "G7-3/Q7/G7-7: store-selection paragraph dropped (no store is ever registered here)") for s in SOURCES),
    # ------------------------------------------------------------------ explore
    *EXPLORE_EDITS,
    # ------------------------------------------------------------------ ff
    Edit("ff", _INPUT_UPSTREAM, _INPUT_ISSUE, "env", "G1-1/G5-1: input = the issue; change name fixed `issue`"),
    Edit(
        "ff",
        _ASK_INPUT,
        "1. **Read the issue**\n\n"
        "   Read the issue in full: every artifact below plans what it asks for. Nobody will describe it further.",
        "env",
        "G1-1: ask-what-to-build branch dropped; the name is not derived (G5-1)",
    ),
    Edit(
        "ff",
        "        - Identify the target project from the request and project context; the planning home may be separate "
        "from the code. If the target is unclear, ask. For greenfield or non-code changes, inspect the available "
        "structure and relevant documents. If source is unavailable, state the limitation and ask when it materially "
        "affects the plan.",
        "        - The target project is the repository at `/testbed`; the planning home (`/openspec`) is separate from "
        "the code. For greenfield or non-code changes, inspect the available structure and relevant documents. If "
        "source is unavailable, state the limitation.",
        "env",
        "G4-1: target fixed to /testbed; ask dropped, \"state the limitation\" kept",
    ),
    Edit(
        "ff",
        "   c. **If an artifact requires user input** (critically unclear context):\n"
        "      - Ask the user to clarify\n"
        "      - Then continue with creation",
        "   c. **If an artifact meets critically unclear context**:\n"
        "      - Take the most plausible reading and record it as an assumption in the artifact being written\n"
        "      - Then continue with creation",
        "semantic",
        "G4-2: most plausible reading, recorded as an assumption, in place of asking",
    ),
    Edit(
        "ff",
        '- Prompt: "Run `/openspec-apply-change` or ask me to implement to start working on the tasks."',
        f"\nAfter the last artifact, open the apply stage document (`{STAGE_DOCS['apply']}`) and continue: "
        "implementation starts in this same session.",
        "env",
        "G2-2: hand-off to apply in place of the closing prompt",
    ),
    Edit(
        "ff",
        "- If context is critically unclear, ask the user - but prefer making reasonable decisions to keep momentum",
        "- If context is critically unclear, take the most plausible reading, record it as an assumption in the "
        "artifact, and keep momentum",
        "semantic",
        "G4-2: the guardrail's own preference made absolute",
    ),
    Edit(
        "ff",
        "- If a change with that name already exists, suggest continuing that change instead\n",
        "",
        "env",
        "D-7: \"already exists → suggest continuing\" hands back to a person; cannot fire in a fresh sandbox",
    ),
    # ------------------------------------------------------------------ apply
    Edit(
        "apply",
        "**Input**: Optionally specify a change name (e.g., `/openspec-apply-change add-auth`). If omitted, check if it "
        "can be inferred from conversation context. If vague or ambiguous you MUST prompt for available changes.",
        "**Input**: Optionally specify a change name (here: `issue`). If omitted, check if it can be inferred from "
        "conversation context.",
        "env",
        "G1-2/G5-1: slash-command example and the prompt-for-changes branch dropped",
    ),
    Edit("apply", _SELECT_ASK, "", "env", "G1-2: ask-to-select branch dropped (auto-select kept)"),
    Edit(
        "apply",
        '   Always announce: "Using change: <name>" and how to override (e.g., `/openspec-apply-change <other>`).',
        '   Always announce: "Using change: issue".',
        "env",
        "G1-2: override hint dropped",
    ),
    Edit(
        "apply",
        "     - If `missingArtifacts` is non-empty: suggest using `/openspec-continue-change` to create them.",
        f"     - If `missingArtifacts` is non-empty: go back to the ff stage document (`{STAGE_DOCS['ff']}`), create "
        "the missing artifacts, then resume this stage.",
        "env",
        "G2-3: blocked -> back to ff, then resume apply",
    ),
    Edit(
        "apply",
        '   - If `state: "all_done"`: report that all tracked tasks are complete and suggest review or verification '
        "as appropriate before archiving",
        '   - If `state: "all_done"`: all tracked tasks are complete; open the verify stage document '
        f"(`{STAGE_DOCS['verify']}`) and continue",
        "env",
        "G2-4: all_done -> verify",
    ),
    Edit(
        "apply",
        "   **Pause if:**\n   - Task is unclear → ask for clarification",
        "   **When a task does not go as planned** (nobody will answer; decide, record, continue):\n"
        "   - Task is unclear → implement the most plausible reading against the specs and design, and note that "
        "reading under the task in `tasks.md` as a plain line (not a checkbox)",
        "semantic",
        "G4-4: unclear task -> most plausible reading, noted under the task",
    ),
    Edit(
        "apply",
        "   - Implementation reveals a design issue → suggest updating artifacts",
        "   - Implementation reveals a design issue → update the affected artifact (design, specs or tasks) yourself, "
        "record what changed and why, and continue",
        "semantic",
        "G4-5: update the artifact yourself in place of suggesting it",
    ),
    Edit(
        "apply",
        "   - A task needs work beyond what the spec and tasks describe, or you are tempted to drop, narrow, defer, or "
        "accept exceptions to specified behavior to make it fit → surface the added scope and ask; do not absorb it "
        "silently",
        "   - A task needs work beyond what the spec and tasks describe → add that work as tasks in `tasks.md` (and to "
        "the delta spec when it is observable behavior), then do it; never drop, narrow, defer, or accept exceptions "
        "to specified behavior to make it fit",
        "semantic",
        "G4-6: extra work becomes tasks; specified behavior is never narrowed",
    ),
    Edit(
        "apply",
        "   - Error or blocker encountered → report and wait for guidance\n   - User interrupts",
        "   - Error or blocker encountered → try to resolve it; if a task stays impossible, leave it unchecked with a "
        "one-line reason under it and continue with the rest",
        "semantic",
        "G4-7: resolve or leave unchecked with a reason; interrupts dropped",
    ),
    Edit(
        "apply",
        "7. **On completion or pause, show status**\n\n"
        "   Display:\n"
        "   - Tasks completed this session\n"
        '   - Overall progress: "N/M tasks complete"\n'
        "   - If all done: report that tracked tasks are complete and suggest review or verification as appropriate "
        "before archiving\n"
        "   - If paused: explain why and wait for guidance",
        "7. **On completion, show status**\n\n"
        "   Completion: every task is checked, or the only unchecked ones carry their one-line reason.\n\n"
        "   Display:\n"
        "   - Tasks completed this session\n"
        '   - Overall progress: "N/M tasks complete"\n'
        f"   - Then open the verify stage document (`{STAGE_DOCS['verify']}`) and continue",
        "env",
        "G2-4/G4-7: completion -> verify; the pause branch dropped",
    ),
    Edit(
        "apply",
        "All tracked tasks are complete. Review or verify the change as appropriate\n"
        "before archiving. You can archive this change with `/openspec-archive-change`.",
        "All tracked tasks are complete. Next: the verify stage.",
        "env",
        "G2-4: completion output names verify, not the archive command",
    ),
    Edit(
        "apply",
        "**Output On Pause (Issue Encountered)**\n\n"
        "```\n"
        "## Implementation Paused\n\n"
        "**Change:** <change-name>\n"
        "**Schema:** <schema-name>\n"
        "**Progress:** 4/7 tasks complete\n\n"
        "### Issue Encountered\n"
        "<description of the issue>\n\n"
        "**Options:**\n"
        "1. <option 1>\n"
        "2. <option 2>\n"
        "3. Other approach\n\n"
        "What would you like to do?\n"
        "```\n",
        "",
        "semantic",
        "G4-7: pause output dropped",
    ),
    Edit(
        "apply",
        "- If task is ambiguous, pause and ask before implementing",
        "- If task is ambiguous, implement the most plausible reading and note it under the task in `tasks.md`",
        "semantic",
        "G4-4: guardrail follows the unclear-task rule",
    ),
    Edit(
        "apply",
        "- If implementation reveals issues, pause and suggest artifact updates",
        "- If implementation reveals issues, update the affected artifacts yourself and record what changed and why",
        "semantic",
        "G4-5: guardrail follows the design-issue rule",
    ),
    Edit(
        "apply",
        "- Pause on errors, blockers, or unclear requirements - don't guess",
        "- On errors or blockers, try to resolve them; a task that stays impossible is left unchecked with a one-line "
        "reason. On unclear requirements, take the most plausible reading and record it",
        "semantic",
        "G4-4/G4-7: guardrail follows the unclear-task and blocker rules",
    ),
    Edit(
        "apply",
        "- When a task needs work beyond what the spec describes, surface the added scope and pause - never silently "
        "narrow, defer, or simplify away specified behavior",
        "- When a task needs work beyond what the spec describes, add it as tasks in `tasks.md` (and to the delta spec "
        "when observable) and do it - never silently narrow, defer, or simplify away specified behavior",
        "semantic",
        "G4-6: guardrail follows the extra-work rule",
    ),
    Edit(
        "apply",
        "- **Allows artifact updates**: If implementation reveals design issues, suggest updating artifacts - not "
        "phase-locked, work fluidly",
        "- **Allows artifact updates**: If implementation reveals design issues, update the artifacts yourself - not "
        "phase-locked, work fluidly",
        "semantic",
        "G4-5: update in place of suggest",
    ),
    # ------------------------------------------------------------------ verify
    Edit(
        "verify",
        "**Input**: Optionally specify a change name. If omitted, check if it can be inferred from conversation "
        "context. If vague or ambiguous you MUST prompt for available changes.",
        "**Input**: Optionally specify a change name (here: `issue`). If omitted, check if it can be inferred from "
        "conversation context.",
        "env",
        "G1-2/G5-1: the prompt-for-changes branch dropped",
    ),
    Edit(
        "verify",
        _SELECT_ASK + "\n"
        '   When prompting, show all active changes returned by the list, including changes with `status: "no-tasks"`.\n'
        "   Include the schema used for each change if available.\n"
        '   Mark changes with incomplete tasks as "(In Progress)".\n',
        "",
        "env",
        "G1-2: ask-to-select branch and its prompt format dropped (auto-select kept)",
    ),
    Edit(
        "verify",
        '   Always announce: "Using change: <name>" and how to override (e.g., `/openspec-verify-change <other>`).',
        '   Always announce: "Using change: issue".',
        "env",
        "G1-2: override hint dropped",
    ),
    Edit(
        "verify",
        "     - Check if tests exist covering the scenario",
        f"     - Check if the scenario is verified by an existing repository test or by a check script under `{CHANGE_DIR}checks/`",
        "semantic",
        "G9-3: coverage = an existing test or a checks/ script",
    ),
    Edit(
        "verify",
        '       - Recommendation: "Add test or implementation for scenario: <description>"',
        '       - Recommendation: "Add a check under `checks/` or fix the code for scenario: <description>"',
        "semantic",
        "G9-3: no repository test to add",
    ),
    Edit(
        "verify",
        "8. **Generate Verification Report**\n",
        "8. **Generate Verification Report**\n\n"
        f"   Write the report to a file in the change directory: `{CHANGE_DIR}verify.md`.\n",
        "env",
        "G5-3: the report is a file in the change dir",
    ),
    Edit(
        "verify",
        "   - Include the suggestion count when nonzero in every final assessment.\n",
        "   - Include the suggestion count when nonzero in every final assessment.\n\n"
        f"   **Next step**: go to the archive step in `{ENTRY_DOC}`. What is left stays recorded in this report.\n",
        "env",
        "G2-5: hand-off to archive; G8-1's verify -> apply round dropped (never triggered in the val ablation)",
    ),
)

SUBSTITUTIONS: tuple[tuple[str, str], ...] = (
    ('"<name>"', '"issue"'),  # G5-1: the change name is fixed
    ("<change-name>", "issue"),
)

# The engine checks every FORBIDDEN string that no allowed sentence contains; the rest are checked per
# source by ``forbidden_left`` (G4-14), which ``convert`` / ``build`` / ``main`` run on every stage document.
_PER_SOURCE = tuple(w for w in FORBIDDEN if any(w in s for kept in FORBIDDEN_ALLOWED.values() for s in kept))

STAGES = Port(
    sources=SOURCES,
    out_dir=OUT_DIR,
    upstream_commit=UPSTREAM_COMMIT,
    sections=EXPLORE_SECTIONS,
    edits=EDITS,
    substitutions=SUBSTITUTIONS,
    forbidden=tuple(w for w in FORBIDDEN if w not in _PER_SOURCE),
)


def forbidden_left(key: str, text: str) -> list[str]:
    """FORBIDDEN strings left in one stage document, after removing that source's allowed sentences.

    An allowed sentence must occur exactly once, so a second occurrence (or a missing one) fails too."""
    for sentence in FORBIDDEN_ALLOWED.get(key, ()):
        n = text.count(sentence)
        if n != 1:
            raise ValueError(f"{key}: allowed sentence occurs {n} times (want 1): {sentence!r}")
        text = text.replace(sentence, "")
    return [w for w in FORBIDDEN if w in text]

# ---------------------------------------------------------------------- the forked schema

# porting/03-decisions.md "Agreed text for the forked schema", verbatim (indented into the YAML block).
AGREED_TASKS_ITEM = """\
- Each task group MUST verify its own work as it lands: run the existing repository
  tests that cover it, or write a check script under /openspec/changes/issue/checks/
  and run it. Do NOT add or edit test files in the repository - the task's tests are
  already in place. Change repository documentation (README, docs/, changelogs) only
  when the issue asks for it; comments and docstrings in the code you change are part
  of that code. Do NOT collect verification into a final group - when a late group
  first exercises work from an early one, the failures cascade back through every
  group in between and force rework. A group whose work calls for no verification,
  such as scaffolding, carries none. A final group is for integration checks only.
"""
AGREED_EXAMPLE = {
    "1.2": "- [ ] 1.2 Write a check script at /openspec/changes/issue/checks/export_check.py that calls the export entry "
    "point and verify it fails against the current code (it should pass once the change is in)",
    "2.2": "- [ ] 2.2 Add CSV formatting utilities and verify the existing CSV tests and export_check.py pass with quoting and delimiters",
    "2.3": "- [ ] 2.3 Run the test module covering the export code and verify no existing test regresses",
}


def _indent(text: str, n: int) -> str:
    return "".join(" " * n + line if line.strip() else line for line in text.splitlines(keepends=True))


FORK_EDITS: tuple[Edit, ...] = (
    Edit("schema", "name: spec-driven\n", f"name: {FORK_NAME}\n", "env", "D-4/Q1: the fork's name, as `openspec schema fork` sets it"),
    Edit("schema", "  requires: [tasks]\n", "  requires: [ tasks ]\n", "env", "D-4: flow-list spacing as `openspec schema fork` re-serializes it (yaml Document API)"),
    Edit(
        "schema",
        "      the task breakdown, resolve it now - ask the user instead of guessing.\n",
        "      the task breakdown, resolve it now yourself - take the most plausible\n"
        "      option and write the choice and its rationale under **Decisions**.\n",
        "semantic",
        "G4-3: design Open Questions that change the plan are resolved and recorded under Decisions",
    ),
    Edit(
        "schema",
        "      Before writing tasks, check design.md for Open Questions. If any of them\n"
        "      would change what gets built, resolve them with the user first - do not\n"
        "      bake an unstated assumption into the task list.\n",
        "      Before writing tasks, check design.md for Open Questions. If any of them\n"
        "      would change what gets built, resolve them yourself first - write the\n"
        "      choice and its rationale under **Decisions** in design.md; do not\n"
        "      bake an unstated assumption into the task list.\n",
        "semantic",
        "G4-3: tasks resolve plan-changing questions themselves, recorded under Decisions",
    ),
    Edit(
        "schema",
        "      - Each task group MUST land the tests and documentation its own work\n"
        "        calls for. Do NOT collect testing or documentation into a final group -\n"
        "        when a late group first exercises work from an early one, the failures\n"
        "        cascade back through every group in between and force rework. A group\n"
        "        whose work calls for neither, such as scaffolding or dependency setup,\n"
        "        carries neither. A final group is for integration checks only, not for\n"
        "        the tests and docs an earlier group owed.\n",
        _indent(AGREED_TASKS_ITEM, 6),
        "semantic",
        "G9-1/G9-2: verification by repo tests or checks/ scripts, no test files, docs only when asked (agreed text)",
    ),
    Edit(
        "schema",
        "      - [ ] 1.2 Add dependencies to package.json and verify package installation succeeds\n",
        _indent(AGREED_EXAMPLE["1.2"] + "\n", 6),
        "semantic",
        "G9-4/G9-1: example 1.2 is a check script, not a dependency install (agreed text)",
    ),
    Edit(
        "schema",
        "      - [ ] 2.2 Add CSV formatting utilities and verify unit tests cover quoting and delimiters\n",
        _indent(AGREED_EXAMPLE["2.2"] + "\n", 6),
        "semantic",
        "G9-1: example 2.2 runs existing tests and the check (agreed text)",
    ),
    Edit(
        "schema",
        "      - [ ] 2.3 Document the export API in docs/export.md and verify the documented command runs as written\n",
        _indent(AGREED_EXAMPLE["2.3"] + "\n", 6),
        "semantic",
        "G9-2: example 2.3 runs the covering tests, no documentation task (agreed text)",
    ),
    Edit(
        "schema",
        "    Pause if you hit blockers or need clarification.",
        "    When a task is unclear, implement the most plausible reading against the\n"
        "    specs and design and note it under the task in tasks.md (a plain line,\n"
        "    not a checkbox). When a blocker stays unresolved, leave that task\n"
        "    unchecked with a one-line reason and continue with the rest.",
        "semantic",
        "G4-4/G4-7: the apply instruction the CLI serves decides and records instead of pausing",
    ),
)

FORK = Port(
    sources=FORK_SOURCES,
    out_dir=FORK_DIR,
    upstream_commit=UPSTREAM_COMMIT,
    edits=FORK_EDITS,
    forbidden=FORK_FORBIDDEN,
    frontmatter=False,
)

PORTS: dict[str, Port] = {"stages": STAGES, "fork": FORK}


def convert(key: str, upstream: str) -> str:
    """One stage document from its upstream text."""
    text = _convert(STAGES, key, upstream)
    left = forbidden_left(key, text)
    if left:
        raise ValueError(f"{key}: upstream wording left after conversion: {left}")
    return text


def convert_fork(key: str, upstream: str) -> str:
    """One file of the forked schema from its upstream text."""
    return _convert(FORK, key, upstream)


def build(upstream: Path) -> dict[str, str]:
    return {out: convert(key, (upstream / src).read_text(encoding="utf-8")) for key, (src, out) in SOURCES.items()}


def build_fork(upstream: Path) -> dict[str, str]:
    return _build(FORK, upstream)


BUILDERS = {"stages": build, "fork": build_fork}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--upstream", type=Path, help="OpenSpec checkout")
    ap.add_argument("--check", action="store_true", help="compare with the committed outputs instead of writing")
    ap.add_argument("--list", action="store_true", help="print the edits by tag")
    args = ap.parse_args(argv)
    if args.list:
        for label, port in PORTS.items():
            print(f"== {label} -> {port.out_dir.relative_to(HERE)}/")
            list_edits(port)
        return 0
    if args.upstream is None:
        ap.error("--upstream is required")
    commit = _git_head(args.upstream)
    if commit != UPSTREAM_COMMIT:
        print(f"warning: upstream at {commit}, outputs pinned to {UPSTREAM_COMMIT}", file=sys.stderr)
    rc = 0
    for label, port in PORTS.items():
        built = BUILDERS[label](args.upstream)
        if args.check:
            for name in _drift(port, built):
                print(f"drift: {port.out_dir.relative_to(HERE)}/{name}", file=sys.stderr)
                rc = 1
            continue
        for name, text in built.items():
            dest = port.out_dir / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(text, encoding="utf-8")
            print(f"wrote {dest.relative_to(HERE)} ({text.count(chr(10))} lines)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
