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
(editor reply, or a shell failure marker on a line naming the path) is an event with ``ok=False``
that leaves the content unchanged. The observation of the final call is empty in training (it was
never sent back), so its writes are never seen to fail -- offline replays blank it the same way.

Event ops: ``create`` (the path did not exist as far as the replay knows) / ``overwrite`` /
``append`` / ``edit`` / ``delete`` / ``move_out`` + ``move_in`` (also for every known file under a
moved directory, e.g. OpenSpec's archive ``mv``) / ``unknown``. A copy lands as create/overwrite.
"""

from __future__ import annotations

import posixpath
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
    """

    writes: dict[str, list[WriteEvent]] = field(default_factory=dict)
    unparsed: list[tuple[int, int, str]] = field(default_factory=list)
    moves: list[tuple[int, str, str]] = field(default_factory=list)
    final: dict[str, str | None] = field(default_factory=dict)
    dirs: set[str] = field(default_factory=set)


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
        for p in self.state:
            self._add_parents(p)
        self.history: dict[str, list[str | None]] = {}  # editor undo stack per path
        self.out = Replay()

    # -- bookkeeping -----------------------------------------------------------------------
    def _add_parents(self, p: str) -> None:
        d = posixpath.dirname(p)
        while d and d != "/" and d not in self.dirs:
            self.dirs.add(d)
            d = posixpath.dirname(d)

    def _under(self, d: str) -> list[str]:
        pre = d.rstrip("/") + "/"
        return sorted(p for p in self.state if p.startswith(pre))

    def _is_dir(self, p: str) -> bool:
        return p in self.dirs or bool(self._under(p))

    def _event(self, path: str, step: int, idx: int, op: str, ok: bool | None, content: str | None, source: str) -> None:
        self.out.writes.setdefault(path, []).append(WriteEvent(path=path, step=step, op=op, ok=ok, content=content, source=source, action_index=idx))

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
            self._event(path, step, idx, op, ok, a.text or "", "file_editor")
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
            self._event(path, step, idx, "edit", ok, content, "file_editor")
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
            self._event(path, step, idx, "edit", ok, content, "file_editor")

    # -- shell -----------------------------------------------------------------------------
    def shell(self, step: int, idx: int, a: Action) -> None:
        command = a.command or ""
        _, cwd_after = shell.split(command, self.cwd)
        for op in shell.write_ops(command, self.cwd, self.state):
            self.apply(step, idx, op, command, a.observation or "")
        self.cwd = cwd_after

    def _failed(self, op: shell.WriteOp, observation: str) -> bool:
        if not observation:
            return False
        if op.source == "python" and shell.python_failed(observation):
            return True
        needles = [n for n in (op.target, op.path, op.src) if n and len(n) > 1]
        return shell.failure_markers(observation, needles, op.verb)

    def apply(self, step: int, idx: int, op: shell.WriteOp, command: str, observation: str) -> None:
        if not op.path:
            if op.op != "mkdir":
                self._gap(step, idx, command)
            return
        ok = False if self._failed(op, observation) else None
        path = op.path
        if op.op == "mkdir":
            if ok is not False:
                self.dirs.add(path)
                self._add_parents(path + "/x")
            return
        if op.op == "delete":
            targets = ([path] if path in self.state else []) + self._under(path)
            for p in targets or [path]:
                self._event(p, step, idx, "delete", ok, self.state.get(p) if ok is False else None, op.source)
                if ok is not False:
                    self._drop(p)
            if ok is not False:
                self.dirs = {d for d in self.dirs if d != path and not d.startswith(path.rstrip("/") + "/")}
            return
        if op.op in ("copy", "move"):
            self._transfer(step, idx, op, ok, command)
            return
        if op.op == "unknown":
            targets = ([path] if path in self.state else []) + self._under(path)
            for p in targets:
                self._set(p, None)
                self._event(p, step, idx, "unknown", ok, None, op.source)
            self._gap(step, idx, command)
            return
        exists = path in self.state
        prior = self.state.get(path)
        name = op.op if op.op != "overwrite" else ("overwrite" if exists else "create")
        if ok is False:
            self._event(path, step, idx, name, False, prior, op.source)
            return
        knew = prior is not None or (not exists and path.startswith(self.fresh))  # the result was knowable
        if op.op == "overwrite":
            content = op.body
            lost = content is None
        elif op.op == "edit":
            content = op.body
            lost = content is None and prior is not None
        else:  # append
            if exists:
                content = None if (prior is None or op.body is None) else prior + op.body
            else:
                content = op.body if path.startswith(self.fresh) else None
            lost = content is None and knew
        if lost:
            self._gap(step, idx, command)
        self._set(path, content)
        self._event(path, step, idx, name, ok, content, op.source)

    def _transfer(self, step: int, idx: int, op: shell.WriteOp, ok: bool | None, command: str) -> None:
        move = op.op == "move"
        dst = op.path
        src = op.src
        if src is None:
            self._gap(step, idx, command)
            self._set(dst, None)
            self._event(dst, step, idx, "move_in" if move else "overwrite", ok, None, op.source)
            return
        into = op.dir_target if op.dir_target is not None else self._is_dir(dst)
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
            self._set(dst, None)
            self._event(dst, step, idx, "move_in" if move else "create", ok, None, op.source)
        for old, new in pairs:
            content = self.state.get(old)
            if move:
                self._event(old, step, idx, "move_out", ok, None, op.source)
                self._drop(old)
            name = "move_in" if move else ("overwrite" if new in self.state else "create")
            self._set(new, content)
            self._event(new, step, idx, name, ok, content, op.source)
        if move:
            pre = src.rstrip("/") + "/"
            moved_dirs = {d for d in self.dirs if d == src or d.startswith(pre)}
            self.dirs = (self.dirs - moved_dirs) | {dst + d[len(src) :] for d in moved_dirs}
            self._add_parents(dst + "/x")
            self.out.moves.append((step, src, dst))


def replay(run: Run, start_cwd: str | None, initial: Mapping[str, str] | None = None, fresh: tuple[str, ...] = FRESH_PREFIXES) -> Replay:
    """Replay every write in ``run`` (cwd starts at ``start_cwd``; ``initial``: files known to exist before the run)."""
    r = _Replayer(start_cwd, initial, fresh)
    for step in run.steps:
        for idx, a in enumerate(step.actions):
            if a.kind == "shell":
                r.shell(step.n, idx, a)
            elif a.kind in ("create", "replace", "insert", "undo"):
                r.editor(step.n, idx, a)
    r.out.final = dict(r.state)
    r.out.dirs = set(r.dirs)
    return r.out
