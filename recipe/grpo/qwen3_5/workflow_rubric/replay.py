"""Replay every file write in a run: what each path held after each step.

Checks ask two questions the sandbox alone cannot answer: what an artifact looked like when its
stage ended (``stage_end`` state), and whether the final file is the one the trace wrote
(``final_mismatch``, i.e. something the trace does not show wrote it too). Offline (harbor trials
keep no files at all) the replay is also the only source of artifact content. So every action is
replayed in order -- editor creates and edits, and every shell write :func:`trace.shell.write_ops`
recognises -- into one event list per absolute path.

Content is tracked only as far as it is known: ``None`` means unknown, never guessed. ``unparsed``
lists the writes that *made* content unknown -- a body built by a command substitution or an
unknown program, an unresolvable target, an edit we cannot apply to content we knew, ``git stash``
and the like. An edit that is fully specified but lands on content the trace never showed (a file
of the base repository) leaves ``None`` without being listed: that gap predates the write. A write the tool says failed
(editor reply; a shell failure marker on a line naming the path; a message the op names in ``WriteOp.nothing``; the
exit code of the command's last segment, for a lone write that is not a redirect or a script; a python script printing
what it prints only where it does not write, :func:`shell.branch_not_taken`) is an event with ``ok=False`` that
leaves the content unchanged; so is a write that changed nothing (an edit whose replayed result equals the known
content, a git restore of a file the run never changed). A segment the shell skipped (``a || b`` after ``a`` wrote,
``a && b`` after ``a`` failed) writes nothing. The observation of the final call is empty in training (it was
never sent back), so its writes are never seen to fail -- offline replays blank it the same way.

Event ops: ``create`` (the path did not exist as far as the replay knows) / ``overwrite`` /
``append`` / ``edit`` / ``delete`` / ``move_out`` + ``move_in`` (also for every known file under a
moved directory, e.g. OpenSpec's archive ``mv``) / ``restore`` (``git checkout -- P``, ``git restore P``) /
``unknown`` (``git stash``, ``checkout .`` ...; a plain stash leaves the run's own untracked files alone). A copy
lands as create/overwrite.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from .context import WriteEvent
from .trace import shell
from .trace.model import Action, Run

# Paths assumed not to exist before the run unless a write says otherwise: appending to one that the
# trace never wrote starts from empty. Elsewhere (a repo file, a shipped template) the prior content
# is unknown, so the result of such an append is unknown too.
FRESH_PREFIXES = ("/tmp/",)


@dataclass
class Replay:
    """writes      absolute path -> its events in order (``context.WriteEvent``)
    unparsed    (step, action_index, command) of writes that made content unknown (see module doc)
    moves       (step, src, dst) of every move, directories included
    final       path -> content at the end, for every path that exists then (None: unknown)
    dirs        directories known to exist at the end (made, or parents of written files)
    dir_steps   directory -> the step it first appeared at (``mkdir``, or a parent of a written file); directories
                that held a file known before the run have none
    """

    writes: dict[str, list[WriteEvent]] = field(default_factory=dict)
    unparsed: list[tuple[int, int, str]] = field(default_factory=list)
    moves: list[tuple[int, str, str]] = field(default_factory=list)
    final: dict[str, str | None] = field(default_factory=dict)
    dirs: set[str] = field(default_factory=set)
    dir_steps: dict[str, int] = field(default_factory=dict)


def content_at(events: list[WriteEvent], step: int) -> str | None:
    """Content after the last event at or before ``step`` (None if unknown, deleted, or never written)."""
    cur: WriteEvent | None = None
    for e in events:
        if e.step <= step:
            cur = e
        else:
            break
    return None if cur is None else cur.content


def apply_edit(content: str, a: Action) -> str | None:
    """An editor ``replace``/``insert`` applied to ``content``; None when the editor would refuse it.

    Ported from the AI-DLC rubric (``facts._apply_edit``): a replace needs a unique match unless
    ``replace_all``; an insert goes after 1-indexed line ``line`` (clamped).
    """
    if a.kind == "replace":
        if not a.old:
            return None
        n = content.count(a.old)
        if n == 1 or (a.replace_all and n >= 1):
            return content.replace(a.old, a.text or "")
        return None
    if a.kind == "insert":
        lines = content.split("\n")
        k = max(0, min(len(lines), a.line or 0))
        lines[k:k] = (a.text or "").split("\n")
        return "\n".join(lines)
    return None


class _Replayer:
    def __init__(self, cwd: str | None, initial: Mapping[str, str] | None, fresh: tuple[str, ...]):
        self.cwd = cwd
        self.fresh = fresh
        self.state: dict[str, str | None] = dict(initial or {})
        self.dirs: set[str] = set()
        self.step: int | None = None  # the step being replayed (None while the initial files are laid out)
        self.dir_steps: dict[str, int] = {}
        for p in self.state:
            self._add_parents(p)
        self.history: dict[str, list[str | None]] = {}  # editor undo stack per path
        self.own_lines: dict[str, set[str]] = {}  # path -> non-blank lines this run's own writes put into the file
        self.new_paths: set[str] = set()  # paths whose first write made them (the run's own, untracked files)
        self.base: dict[str, str] = {}  # path -> its content before the run's first write, when known
        self.out = Replay()

    # -- bookkeeping -----------------------------------------------------------------------
    def _add_parents(self, p: str) -> None:
        d = posixpath.dirname(p)
        while d and d != "/" and d not in self.dirs:
            self._add_dir(d)
            d = posixpath.dirname(d)

    def _add_dir(self, d: str) -> None:
        self.dirs.add(d)
        if self.step is not None:
            self.dir_steps.setdefault(d, self.step)

    def _under(self, d: str) -> list[str]:
        pre = d.rstrip("/") + "/"
        return sorted(p for p in self.state if p.startswith(pre))

    def _is_dir(self, p: str) -> bool:
        return p in self.dirs or bool(self._under(p))

    def _event(self, path: str, step: int, idx: int, op: str, ok: bool | None, content: str | None, source: str, prior: str | None = None, prior_known: bool = False,
               unseen: bool | None = None) -> None:
        """``unseen``: whether the write dropped an existing line when the replay has not seen the file before (None:
        unknown) -- an editor replace answers it from its old and new text, an append or an insert adds only."""
        own = self.own_lines.setdefault(path, set())
        first = path not in self.out.writes
        if op == "restore":
            removed = False  # git puts the file's own lines back
        elif not prior_known and op not in ("delete", "move_out"):
            evs = self.out.writes.get(path)
            gone = bool(evs) and evs[-1].op in ("delete", "move_out") and evs[-1].ok is not False  # the run removed it: nothing to lose
            removed = False if (ok is False or gone) else unseen
        else:
            removed = _removed_existing(op, ok, prior, content, prior_known, own, made=path in self.new_paths)
            if removed is None and unseen is not None:  # content unknown, but the edit's own text tells
                removed = unseen
        if ok is not False and op == "restore":
            own.clear()
        elif ok is not False and content is not None:
            own |= _lines(content) - (_lines(prior) if prior_known and prior is not None else set())
        if first and ok is not False:
            if op in ("create", "move_in") and not prior_known:
                self.new_paths.add(path)
            elif prior_known and prior is not None:
                self.base.setdefault(path, prior)
        self.out.writes.setdefault(path, []).append(WriteEvent(path=path, step=step, op=op, ok=ok, content=content, source=source, action_index=idx,
                                                              removed_existing=removed))

    def _gap(self, step: int, idx: int, command: str) -> None:
        entry = (step, idx, command)
        if not self.out.unparsed or self.out.unparsed[-1] != entry:
            self.out.unparsed.append(entry)

    def _set(self, path: str, content: str | None) -> None:
        self.state[path] = content
        self._add_parents(path)

    def _drop(self, path: str) -> None:
        self.state.pop(path, None)

    # -- editor ----------------------------------------------------------------------------
    def editor(self, step: int, idx: int, a: Action) -> None:
        if not a.path:
            return
        path = shell.resolve(a.path, self.cwd)
        ok = True if a.status == "ok" else False if a.status == "fail" else None
        exists = path in self.state
        prior = self.state.get(path)
        if a.kind == "create":
            op = "overwrite" if exists else "create"
            if ok is False:
                self._event(path, step, idx, op, False, prior, "file_editor")
                return
            self.history.setdefault(path, []).append(prior)
            self._set(path, a.text or "")
            # the editor's create refuses a path that exists: a file it made had no lines to lose
            self._event(path, step, idx, op, ok, a.text or "", "file_editor", prior=prior, prior_known=exists, unseen=False)
            return
        if a.kind in ("replace", "insert"):
            if ok is False:
                self._event(path, step, idx, "edit", False, prior, "file_editor")
                return
            new = apply_edit(prior, a) if prior is not None else None
            if new is None:
                # Known content the edit cannot apply to: a silent reply means the editor refused it
                # too; an explicit success means our content was stale -- unknown from here on.
                content = prior if (prior is not None and ok is None) else None
            else:
                content = new
            if content is None and prior is not None:
                self._gap(step, idx, f"{a.kind} {path}")
            if content != prior or new is not None:
                self.history.setdefault(path, []).append(prior)
            self._set(path, content)
            if a.kind == "insert":
                unseen: bool | None = False
            else:  # the replaced text was in the file; the lines of it the new text drops are gone
                unseen = bool(_lines(a.old) - _lines(a.text) - self.own_lines.get(path, set())) if a.old else None
            self._event(path, step, idx, "edit", ok, content, "file_editor", prior=prior, prior_known=exists, unseen=unseen)
            return
        if a.kind == "undo":
            if ok is False:
                self._event(path, step, idx, "edit", False, prior, "file_editor")
                return
            stack = self.history.get(path)
            content = stack.pop() if (ok and stack) else None
            if content is None and prior is not None:
                self._gap(step, idx, f"undo {path}")
            self._set(path, content)
            self._event(path, step, idx, "edit", ok, content, "file_editor", prior=prior, prior_known=exists)

    # -- shell -----------------------------------------------------------------------------
    def shell(self, step: int, idx: int, a: Action) -> None:
        """The command's writes, segment by segment. A segment the shell did not run is skipped: the right side of
        ``a || b`` once ``a`` is taken to have written (the replay counts its write), of ``a && b`` once ``a``'s write
        failed. Only the last segment's exit code is its own (:func:`_exit_code`)."""
        command = a.command or ""
        observation = a.observation or ""
        segs, cwd_after = shell.split(command, self.cwd)
        by_seg: dict[int, list[shell.WriteOp]] = {}
        for op in shell.write_ops(command, self.cwd, self.state):
            by_seg.setdefault(op.seg, []).append(op)
        code = _exit_code(observation)
        for op in by_seg.pop(-1, []):  # not placed in a segment
            self.apply(step, idx, op, command, observation)
        status: bool | None = None  # did the and-or list up to here succeed (None: unknown)
        for k, seg in enumerate(segs):
            if (seg.op_before == "||" and status is True) or (seg.op_before == "&&" and status is False):
                continue  # the shell skipped it; the list keeps its status
            ops = by_seg.get(k, [])
            own_code = code if (k == len(segs) - 1 and len(ops) == 1) else None
            oks = [self.apply(step, idx, op, command, observation, own_code) for op in ops]
            status = (not all(ok is False for ok in oks)) if oks else None
        self.cwd = cwd_after

    def _failed(self, op: shell.WriteOp, observation: str, code: int | None = None) -> bool:
        if not observation:
            return False
        if op.source == "python" and (shell.python_failed(observation) or shell.branch_not_taken(op, observation)):
            return True
        if op.nothing and any(re.search(op.nothing, ln) for ln in _lines_of(observation)):
            return True
        if code and op.source not in _WRITES_ANYWAY:
            return True
        needles = [n for n in (op.target, op.path, op.src) if n and len(n) > 1]
        return shell.failure_markers(observation, needles, op.verb)

    def apply(self, step: int, idx: int, op: shell.WriteOp, command: str, observation: str, code: int | None = None) -> bool | None:
        """Replay one write; returns its ``ok`` (False: it failed or changed nothing)."""
        if not op.path:
            if op.op != "mkdir":
                self._gap(step, idx, command)
            return None
        ok = False if self._failed(op, observation, code) else None
        path = op.path
        if op.op == "mkdir":
            if ok is not False:
                self._add_dir(path)
                self._add_parents(path + "/x")
            return ok
        if op.op == "delete":
            targets = ([path] if path in self.state else []) + self._under(path)
            for p in targets or [path]:
                self._event(p, step, idx, "delete", ok, self.state.get(p) if ok is False else None, op.source,
                            prior=self.state.get(p), prior_known=p in self.state)
                if ok is not False:
                    self._drop(p)
            if ok is not False:
                self.dirs = {d for d in self.dirs if d != path and not d.startswith(path.rstrip("/") + "/")}
            return ok
        if op.op in ("copy", "move"):
            self._transfer(step, idx, op, ok, command)
            return ok
        if op.op == "restore":
            return self._restore(step, idx, op, ok)
        if op.op == "unknown":
            targets = ([path] if path in self.state else []) + self._under(path)
            if op.tracked_only:  # a plain `git stash` / `stash pop` leaves the run's own untracked files alone
                targets = [p for p in targets if p not in self.new_paths]
            for p in targets:
                if ok is False:
                    self._event(p, step, idx, "unknown", False, self.state.get(p), op.source)
                    continue
                self._set(p, None)
                self._event(p, step, idx, "unknown", ok, None, op.source)
            if ok is not False:
                self._gap(step, idx, command)
            return ok
        exists = path in self.state
        prior = self.state.get(path)
        name = op.op if op.op != "overwrite" else ("overwrite" if exists else "create")
        if ok is False:
            self._event(path, step, idx, name, False, prior, op.source)
            return ok
        if op.op == "edit" and op.source == "sed" and op.body is not None and prior is not None and op.body == prior:
            # a `sed -i` substitution that matched nothing: the file is as it was
            self._event(path, step, idx, name, False, prior, op.source)
            return None  # the command ran; it just changed nothing
        knew = prior is not None or (not exists and path.startswith(self.fresh))  # the result was knowable
        if op.op == "overwrite":
            content = op.body
            lost = content is None
        elif op.op == "edit":
            content = op.body
            lost = content is None and prior is not None
        else:  # append
            if op.body is not None:  # the appended lines are the run's own even when the file's prior content is unknown
                self.own_lines.setdefault(path, set()).update(_lines(op.body))
            if exists:
                content = None if (prior is None or op.body is None) else prior + op.body
            else:
                content = op.body if path.startswith(self.fresh) else None
            lost = content is None and knew
        if lost:
            self._gap(step, idx, command)
        self._set(path, content)
        self._event(path, step, idx, name, ok, content, op.source, prior=prior, prior_known=exists, unseen=False if op.op == "append" else None)
        return ok

    def _restore(self, step: int, idx: int, op: shell.WriteOp, ok: bool | None) -> bool | None:
        """``git checkout [-- ] P`` / ``git restore P``: each file under P the run has written goes back to its committed
        content. A file the run never changed gets nothing (``ok`` False: no change), unless the restore names another
        revision; for a directory, the run's own untracked files stay. The content after it is the file's content before
        the run when the replay knew it."""
        path = op.path
        named = [path] if (path in self.state or path in self.out.writes) else []
        under = [p for p in self._under(path) if p not in self.new_paths]
        under += [p for p in self.out.writes if p.startswith(path.rstrip("/") + "/") and p not in self.state and p not in self.new_paths]
        targets = list(dict.fromkeys(named + sorted(under)))
        if not targets and op.rev and ok is not False:  # another revision's content: a change even of an untouched file
            self._set(path, None)
            self._event(path, step, idx, "restore", ok, None, op.source, prior_known=True)
            return ok
        if not targets:
            self._event(path, step, idx, "restore", False, self.state.get(path), op.source)
            return False if ok is False else None
        for p in targets:
            changed = bool(op.rev) or any(e.ok is not False and e.op != "restore" for e in self._since_restore(p))
            if ok is False or not changed:
                self._event(p, step, idx, "restore", False, self.state.get(p), op.source)
                continue
            content, prior = self.base.get(p), self.state.get(p)
            self._set(p, content)
            self._event(p, step, idx, "restore", ok, content, op.source, prior=prior, prior_known=True)
        return False if ok is False else None  # git ran; restoring an unchanged file is no failure of the command

    def _since_restore(self, p: str) -> list[WriteEvent]:
        evs = self.out.writes.get(p, [])
        last = max((k for k, e in enumerate(evs) if e.op == "restore" and e.ok is not False), default=-1)
        return evs[last + 1 :]

    def _transfer(self, step: int, idx: int, op: shell.WriteOp, ok: bool | None, command: str) -> None:
        move = op.op == "move"
        dst = op.path
        src = op.src
        if src is None:
            self._gap(step, idx, command)
            self._set(dst, None)
            self._event(dst, step, idx, "move_in" if move else "overwrite", ok, None, op.source)
            return
        # a path that holds a file record is no directory, whatever a past move registered (H-8)
        into = op.dir_target if op.dir_target is not None else (self._is_dir(dst) and dst not in self.state)
        if into:
            dst = posixpath.join(dst, posixpath.basename(src))
        pairs = [(src, dst)] if src in self.state else []
        if move or op.recursive:
            pairs += [(p, dst + p[len(src) :]) for p in self._under(src)]
        if ok is False:
            self._event(dst, step, idx, "move_in" if move else ("overwrite" if dst in self.state else "create"), False, self.state.get(dst), op.source)
            return
        if not pairs:
            if self._is_dir(src) and not (move or op.recursive):
                return  # `cp dir x` without -r copies nothing
            if src.startswith(self.fresh):
                self._gap(step, idx, command)  # a scratch file the trace never showed being written
            prior, known = self.state.get(dst), dst in self.state
            self._set(dst, None)
            self._event(dst, step, idx, "move_in" if move else "create", ok, None, op.source, prior=prior, prior_known=known)
        for old, new in pairs:
            content = self.state.get(old)
            if move:
                self._event(old, step, idx, "move_out", ok, None, op.source, prior=content, prior_known=True)
                self._drop(old)
            name = "move_in" if move else ("overwrite" if new in self.state else "create")
            prior, known = self.state.get(new), new in self.state  # what the move or copy lands on
            self._set(new, content)
            self._event(new, step, idx, name, ok, content, op.source, prior=prior, prior_known=known)
        if move:
            pre = src.rstrip("/") + "/"
            moved_dirs = {d for d in self.dirs if d == src or d.startswith(pre)}
            self.dirs = (self.dirs - moved_dirs) | {dst + d[len(src) :] for d in moved_dirs}
            # the destination becomes a directory only when a directory was moved; a moved file is a file
            if moved_dirs or any(old != src for old, _ in pairs):
                self._add_parents(dst + "/x")
            else:
                self._add_parents(dst)
            self.out.moves.append((step, src, dst))


def _lines(text: str | None) -> set[str]:
    return {ln.strip() for ln in (text or "").splitlines() if ln.strip()}


def _removed_existing(op: str, ok: bool | None, prior: str | None, content: str | None, prior_known: bool, own: set[str] = frozenset(), made: bool = False) -> bool | None:
    """Did this write drop or change a non-blank line the file had before it? None when unknowable.

    A failed write changes nothing: False. A file the replay has not seen before (``prior_known`` False) is judged by
    the caller (an editor replace by its own text, an append adds only; else unknown); a delete of one is unknown. A
    delete / move-out of a known file: whether it held a line that is not the run's own (``own``; a file the run made
    itself, ``made``, has none; unknown content of another file counts as existing lines). Otherwise -- a move or copy
    landing on a known file included -- both the prior and the new content must be known; the answer is whether any
    prior non-blank line is absent from the new content (so a pure addition -- a new test function appended or
    inserted -- is False). Lines this run's own earlier writes put into the file (``own``) are not the file's: changing
    a test function the run itself added to an existing module is no change of the module's existing lines."""
    if ok is False:
        return False
    if not prior_known:
        return None
    if op in ("delete", "move_out"):
        if made:
            return bool(_lines(prior) - own) if prior is not None else False
        return True if prior is None else bool(_lines(prior) - own)
    if prior is None or content is None:
        return None
    return bool(_lines(prior) - _lines(content) - own)


def _lines_of(observation: str) -> list[str]:
    return shell._strip_ansi(observation or "").splitlines()


_EXIT = re.compile(r"\[(?:The command completed with exit code|Command finished with exit code)\s+(-?\d+)\.?\]")
# writes that land whatever the command's exit status: a redirect or heredoc opens its file before the command
# runs; a python script is read by what it printed (``shell.branch_not_taken``), not by its exit code
_WRITES_ANYWAY = frozenset({"heredoc", "redirect", "echo", "printf", "tee", "python"})


def _exit_code(observation: str) -> int | None:
    """The call's exit code, as the terminal reports it at the end of the observation (None: not reported)."""
    m = _EXIT.findall((observation or "")[-2000:])
    try:
        return int(m[-1]) if m else None
    except ValueError:
        return None


def replay(run: Run, start_cwd: str | None, initial: Mapping[str, str] | None = None, fresh: tuple[str, ...] = FRESH_PREFIXES) -> Replay:
    """Replay every write in ``run`` (cwd starts at ``start_cwd``; ``initial``: files known to exist before the run)."""
    r = _Replayer(start_cwd, initial, fresh)
    for step in run.steps:
        r.step = step.n
        for idx, a in enumerate(step.actions):
            if a.kind == "shell":
                r.shell(step.n, idx, a)
            elif a.kind in ("create", "replace", "insert", "undo"):
                r.editor(step.n, idx, a)
    r.out.final = dict(r.state)
    r.out.dirs = set(r.dirs)
    r.out.dir_steps = dict(r.dir_steps)
    return r.out
