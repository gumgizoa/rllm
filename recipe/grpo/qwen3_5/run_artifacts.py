"""What a rollout leaves in its sandbox, kept in ``episode.artifacts`` for compliance scored later.

The sandbox is gone once the verifier has run, and with it everything a workflow scorer reads
besides the trajectory: the agent's change to the repository and the reports the workflow had it
write. :class:`workflow_harness.WorkflowMixin` reads them at the end of ``run()`` -- after the agent,
before the verifier touches the repository -- and returns them on the Episode, which the engine
keeps through enrichment into the episode JSON:

    patch               ``git diff`` of the workdir against the commit the agent started from,
                        untracked files included (``.gitignore`` respected), ``--binary`` so it
                        applies back onto the task image; what the verifier graded
    patch_base          that commit (the stand-in commit when git history is hidden)
    patch_bytes         full size; ``patch_truncated`` when it is over ``MAX_PATCH_BYTES``
    workflow_outputs    container path -> text of every file under the spec's ``output_dirs``,
                        the shape a scorer's ``collect`` returns, so ``score(task, episode,
                        workflow_outputs)`` runs on a saved episode as it did in the sandbox
    workflow_outputs_skipped  path -> size of files past ``MAX_OUTPUT_BYTES`` in total
    stray_files         path -> size of files created or changed while the agent ran under
                        ``/tmp`` and the workflow's ``container_dir``, outside the output dirs
                        (a report written to the wrong place, an edited workflow document);
                        names only, at most ``MAX_STRAY_FILES`` (``stray_files_truncated``)
    patch_error         why the patch is missing, when it is

``start_command`` runs just before the agent and records the base commit in a marker file whose
mtime is the agent's start; ``collect_command`` reads everything back in one exec. The marker lives
in the sandbox, not on the harness, because one harness instance serves every concurrent rollout.
Files travel base64-encoded behind ``@@RLLM`` lines, as ``aidlc_v4/reward/evaluator.py`` does, so
exec's text channel cannot mangle them.
"""

from __future__ import annotations

import base64
import shlex

MARKER = "/opt/rllm-collect-start"
MAX_PATCH_BYTES = 1_000_000
MAX_OUTPUT_BYTES = 1_000_000
MAX_STRAY_FILES = 500
# Created by tools the agent runs, not by the agent: pytest's tmp_path, bytecode, openhands-sdk's
# file_editor undo history.
STRAY_IGNORED = ("/tmp/pytest-of-*", "*/__pycache__", "/tmp/oh_editor_history_*")

_M = "@@RLLM"


def start_command(workdir: str | None) -> str:
    """Write the base commit (empty when the workdir is not a git repo) to the marker."""
    head = f"cd {shlex.quote(workdir)} && git -c 'safe.directory=*' rev-parse HEAD 2>/dev/null" if workdir else "true"
    return f"mkdir -p {shlex.quote(MARKER.rsplit('/', 1)[0])} && ({head}) > {MARKER}; true"


def collect_command(workdir: str | None, output_dirs: tuple[str, ...], stray_roots: tuple[str, ...], stray_skip: tuple[str, ...]) -> str:
    """One bash script printing the patch, the output files and the stray file list."""
    q = shlex.quote
    scratch = MARKER.rsplit("/", 1)[0]
    prune = " -o ".join(f"-path {q(p)}" for p in (*output_dirs, *stray_skip, *STRAY_IGNORED))
    lines = [
        "g() { git -c 'safe.directory=*' \"$@\"; }",
        f"base=$(cat {MARKER} 2>/dev/null)",
        f'echo "{_M} base $base"',
    ]
    if workdir:
        lines += [
            f'if [ -z "$base" ]; then echo "{_M} patch_error no git repository at {workdir} when the agent started";',
            f"elif cd {q(workdir)} 2>/dev/null; then",
            f"  idx=$(mktemp {scratch}/rllm-index.XXXXXX); out=$(mktemp {scratch}/rllm-patch.XXXXXX)",
            # A copy of the real index only saves re-hashing; the repository's own index is untouched
            # (an empty GIT_INDEX_FILE would mean the real one, hence the -n checks).
            # mktemp leaves an empty file, which git rejects as an index: copy over it or remove it.
            '  src=$(g rev-parse --git-path index 2>/dev/null); if [ -n "$idx" ]; then if [ -f "$src" ]; then cp "$src" "$idx"; else rm -f "$idx"; fi; fi',
            '  export GIT_INDEX_FILE="$idx"',
            '  if [ -n "$idx" ] && [ -n "$out" ] && g add -A . >/dev/null 2>&1 \\',
            '      && g diff --cached --binary --no-color --no-ext-diff --no-renames "$base" > "$out" 2>/dev/null; then',
            f'    echo "{_M} patch_bytes $(wc -c < "$out")"; echo "{_M} patch"; head -c {MAX_PATCH_BYTES} "$out" | base64 -w0; echo',
            f'  else echo "{_M} patch_error git diff failed"; fi',
            '  unset GIT_INDEX_FILE; rm -f "$idx" "$out"',
            f'else echo "{_M} patch_error workdir {workdir} is gone"; fi',
        ]
    else:
        lines.append(f'echo "{_M} patch_error the task declares no workdir"')
    if output_dirs:
        lines += [
            "total=0",
            f"for d in {' '.join(q(d) for d in output_dirs)}; do",
            '  [ -e "$d" ] || continue',
            "  while IFS= read -r f; do",
            '    sz=$(wc -c < "$f")',
            f'    if [ $((total + sz)) -gt {MAX_OUTPUT_BYTES} ]; then echo "{_M} skipped $sz $f"; continue; fi',
            f'    total=$((total + sz)); echo "{_M} file $f"; base64 -w0 "$f"; echo',
            '  done < <(find "$d" -type f 2>/dev/null | LC_ALL=C sort)',
            "done",
        ]
    if stray_roots:
        lines.append(f"find {' '.join(q(r) for r in stray_roots)} \\( {prune} \\) -prune -o -type f -newer {MARKER} -printf '{_M} stray %s %p\\n' 2>/dev/null | head -n {MAX_STRAY_FILES + 1}")
    lines.append("true")
    return "bash -c " + q("\n".join(lines))


def _b64(line: str) -> str:
    return base64.b64decode(line.strip() or b"").decode("utf-8", errors="replace")


def parse(output: str) -> dict:
    """``collect_command``'s output -> the ``episode.artifacts`` entries."""
    art: dict = {}
    outputs: dict[str, str] = {}
    skipped: dict[str, int] = {}
    stray: dict[str, int] = {}
    pending: str | None = None  # "patch" or a file path: the next line is its base64
    for line in (output or "").splitlines():
        if pending is not None:
            if pending == "patch":
                art["patch"] = _b64(line)
            else:
                outputs[pending] = _b64(line)
            pending = None
            continue
        if not line.startswith(_M + " "):
            continue
        kind, _, rest = line[len(_M) + 1 :].partition(" ")
        if kind == "base":
            art["patch_base"] = rest.strip() or None
        elif kind == "patch_bytes":
            art["patch_bytes"] = int(rest)
        elif kind == "patch":
            pending = "patch"
        elif kind == "patch_error":
            art["patch_error"] = rest.strip()
        elif kind == "file":
            pending = rest
        elif kind == "skipped":
            size, _, path = rest.partition(" ")
            skipped[path] = int(size)
        elif kind == "stray":
            size, _, path = rest.partition(" ")
            stray[path] = int(size)
    if "patch" in art:
        art["patch_truncated"] = art.get("patch_bytes", 0) > MAX_PATCH_BYTES
    if outputs or skipped:
        art["workflow_outputs"] = outputs
    if skipped:
        art["workflow_outputs_skipped"] = skipped
    if len(stray) > MAX_STRAY_FILES:
        stray = dict(list(stray.items())[:MAX_STRAY_FILES])
        art["stray_files_truncated"] = True
    art["stray_files"] = stray
    return art
