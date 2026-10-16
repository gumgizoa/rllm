"""Shell command lines -> which segments ran (and where), what they read, and what they wrote.

The agent's terminal is a persistent bash session, and most of what it does to files goes through
it: heredocs, redirects, ``tee``, ``sed -i``, python one-liners, ``cp``/``mv``/``rm``. The engine
needs three answers from a command line without running it -- the segments that execute and the
directory each runs in, the files a reading verb consumed, and the files that changed into what --
and it must never raise on whatever the model typed. So this is a small bash lexer (quotes,
escapes, ``$(...)``, heredocs, comments, line continuations), a segment model on top of it (cwd,
simple variables, ``for`` loops, subshells, ``bash -c``, xargs) and two consumers,
:func:`read_targets` and :func:`write_ops`.

It replaces the regexes of the AI-DLC rubric (``workflows/aidlc_v4/reward/rubric/facts.py``
``write_targets`` and ``artifacts.py`` ``heredocs``/``shell_written_body``/``_printf_body``) and
closes the gaps evalv1 measured against them: ``tee P <<EOF`` without a pipe, relative paths after
``cd``, variable paths, ``rm P && cat > P`` in one command, ``>>`` appends (they concatenate),
``sed -i`` (simple scripts are applied to the known content instead of dropping it), ``cp``/``mv``
into a path (the source's content follows), ``<<-`` with tab-indented terminators, and path
mentions inside another heredoc's body (bodies are data, never parsed as commands).

Nothing is executed. A body that depends on a command substitution or a variable we cannot see is
reported as unknown (``body=None``), never guessed; a write whose *target* is such an expansion has
``path=""`` and ``variable=True``. Python sources are read with :mod:`ast` (literals, simple names,
``str.replace`` chains), never evaluated. ``sed`` scripts are applied only when they are plain
substitutions/deletions whose regexes cannot backtrack badly.
"""

from __future__ import annotations

import ast
import functools
import logging
import posixpath
import re
import shlex
import textwrap
import time
import warnings
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

HOME = "/root"
MAX_DEPTH = 3  # nested `bash -c` / executed scripts followed
MAX_BRACE = 256  # brace-expansion alternatives kept per word
MAX_SOURCE = 1 << 20  # python / sed inputs larger than this are not analysed
MAX_LINE = 1_000  # sed is not applied to content with longer lines
SED_BUDGET = 0.25  # seconds one sed application may take before it is abandoned

_META = frozenset(" \t\r\n;&|<>()")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(\+?)=")
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][A-Za-z0-9]|\r")
_DEV = re.compile(r"^/dev/(?:null|zero|stdout|stderr|stdin|tty|fd/\d+)$|^/proc/self/fd/\d+$")
_KEYWORDS = frozenset({"!", "if", "then", "else", "elif", "fi", "while", "until", "do", "done", "{", "}", "function", "esac"})
_SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh"})
_PYTHON = re.compile(r"^(?:python|pypy)[0-9.]*$")
_SETUP = frozenset({"cd", "pushd", "popd", "export", "set", "source", ".", "unset", "true", ":", "shopt", "ulimit", "umask", "alias"})

# Wrappers that run another command: name -> (required subcommand, options taking a value, operands before the command).
_WRAPPERS: dict[str, tuple[str | None, frozenset[str], int]] = {
    "env": (None, frozenset({"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}), 0),
    "sudo": (None, frozenset({"-u", "--user", "-g", "--group", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-T"}), 0),
    "doas": (None, frozenset({"-u", "-C"}), 0),
    "timeout": (None, frozenset({"-s", "--signal", "-k", "--kill-after"}), 1),
    "nice": (None, frozenset({"-n", "--adjustment"}), 0),
    "ionice": (None, frozenset({"-c", "-n", "-p", "--class", "--classdata"}), 0),
    "time": (None, frozenset({"-f", "-o", "--format", "--output"}), 0),
    "stdbuf": (None, frozenset({"-i", "-o", "-e"}), 0),
    "nohup": (None, frozenset(), 0),
    "xargs": (None, frozenset({"-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a", "--max-args", "--max-procs", "--delimiter", "--arg-file", "--max-lines"}), 0),
    "command": (None, frozenset(), 0),
    "exec": (None, frozenset({"-a"}), 0),
    "builtin": (None, frozenset(), 0),
    "unbuffer": (None, frozenset(), 0),
    "chronic": (None, frozenset(), 0),
    "taskset": (None, frozenset(), 1),
    "npx": (None, frozenset({"-p", "--package"}), 0),
    "uv": ("run", frozenset({"--with", "-p", "--python", "--project", "--directory", "--extra", "--group", "--env-file", "--package"}), 0),
    "poetry": ("run", frozenset({"-C", "--directory", "-P", "--project"}), 0),
    "pipenv": ("run", frozenset(), 0),
    "pdm": ("run", frozenset({"-p", "--project"}), 0),
    "hatch": ("run", frozenset(), 0),
    "conda": ("run", frozenset({"-n", "--name", "-p", "--prefix", "--cwd"}), 0),
    "mamba": ("run", frozenset({"-n", "--name", "-p", "--prefix", "--cwd"}), 0),
    "micromamba": ("run", frozenset({"-n", "--name", "-p", "--prefix", "--cwd"}), 0),
}


# ============================================================================================
# Data
# ============================================================================================
@dataclass
class Word:
    """One shell word: ``text`` with quotes removed and known variables substituted, ``raw`` as typed.

    An unresolved simple variable stays in ``text`` as ``${NAME}`` and is listed in ``vars``
    (a ``for`` loop variable is resolved later, per item); ``opaque`` marks expansions nothing can
    resolve (``$(...)``, backticks, ``$1``, ``${x/a/b}``).
    """

    text: str
    raw: str = ""
    glob: bool = False  # an unquoted * ? [ the shell would expand
    quoted: bool = False
    vars: list[str] = field(default_factory=list)
    opaque: bool = False
    subs: list[str] = field(default_factory=list)  # bodies of $(...) / `...`

    @property
    def dynamic(self) -> bool:
        return self.opaque or bool(self.vars)


@dataclass
class Segment:
    """One simple command of a command line (split on ``&& || ; |`` and newlines outside quotes/heredocs).

    ``cmd`` is ``argv`` from the executed command on (keywords, ``NAME=v`` prefixes and wrappers
    dropped). For ``bash -c STR`` the verb is the inner command's and ``inner`` holds STR split one
    level down; ``xargs`` marks a command run by xargs (its operands come from ``prev``, the
    previous pipeline stage). ``loops`` maps the ``for`` variables in scope to their item words.
    ``stdin_text`` is what the command reads on stdin from its own heredoc / here-string, after
    expansion (None when unknown or absent).
    """

    text: str
    verb: str | None
    argv: list[str]
    redirects: list[tuple[str, str]]
    heredoc: str | None
    cwd: str | None
    op_before: str
    cmd: list[str] = field(default_factory=list)
    loops: dict[str, list[str]] = field(default_factory=dict)
    inner: list[Segment] = field(default_factory=list)
    xargs: bool = False
    stdin_text: str | None = None
    prev: Segment | None = field(default=None, repr=False, compare=False)
    words: list[Word] = field(default_factory=list, repr=False, compare=False)
    cmd_start: int = field(default=0, repr=False)
    redirect_words: list[Word | None] = field(default_factory=list, repr=False, compare=False)
    heredoc_quoted: bool = field(default=True, repr=False)

    @property
    def cmd_words(self) -> list[Word]:
        return self.words[self.cmd_start :]


@dataclass
class WriteOp:
    """One change a command makes to the file system, as far as its text shows.

    ``body`` is the full new content (overwrite / edit) or the appended text (append) when it can be
    recovered; ``target`` is the path as written. For copy/move ``dir_target`` says whether ``path``
    is a directory to move *into* (True), the destination itself (False), or unknown (None: the
    replay decides from what it knows exists).
    """

    path: str
    op: str
    body: str | None
    source: str
    src: str | None = None
    variable: bool = False
    target: str = ""
    dir_target: bool | None = None
    recursive: bool = False
    verb: str | None = None
    applied: bool = field(default=False, repr=False, compare=False)


# ============================================================================================
# Paths and globs
# ============================================================================================
def resolve(path: str, cwd: str | None) -> str:
    """Absolute normalised path: ``~`` -> /root, relative -> against ``cwd`` (``/`` when unknown)."""
    p = path or ""
    if p == "~" or p.startswith("~/"):
        p = HOME + p[1:]
    if not p.startswith("/"):
        p = posixpath.join(cwd or "/", p)
    p = posixpath.normpath(p)
    if p.startswith("//"):
        p = "/" + p.lstrip("/")
    return p


def _has_glob(text: str) -> bool:
    i = 0
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c in "*?":
            return True
        if c == "[" and "]" in text[i + 2 :]:
            return True
        i += 1
    return False


def _braces(text: str, limit: int = MAX_BRACE) -> list[str]:
    """Bash brace expansion: ``a{b,c}d`` -> abd acd, ``{1..3}`` -> 1 2 3 (nested; at most ``limit`` results).

    Left to right, as a capped cross product: a word with thousands of groups costs linear time.
    """
    if "{" not in text:
        return [text]
    if text.count("{") > 64:
        return [text]
    outs = [""]
    i, n, lit = 0, len(text), 0
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c != "{" or (i > 0 and text[i - 1] == "$"):
            i += 1
            continue
        depth, j = 0, i
        while j < n:
            if text[j] == "\\":
                j += 2
                continue
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j >= n:
            break
        alts = _brace_alternatives(text[i + 1 : j])
        if alts is None:
            i += 1
            continue
        expanded = [x for a in alts for x in _braces(a, limit)][:limit]
        head = text[lit:i]
        outs = [o + head + e for o in outs for e in expanded][:limit]
        i = lit = j + 1
    return [o + text[lit:] for o in outs]


def _brace_alternatives(inner: str) -> list[str] | None:
    m = re.fullmatch(r"(-?\d+)\.\.(-?\d+)", inner)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if abs(b - a) > MAX_BRACE:
            return None
        step = 1 if b >= a else -1
        return [str(x) for x in range(a, b + step, step)]
    parts, depth, cur = [], 0, []
    i = 0
    while i < len(inner):
        c = inner[i]
        if c == "\\" and i + 1 < len(inner):
            cur.append(inner[i : i + 2])
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        if c == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    parts.append("".join(cur))
    return parts if len(parts) > 1 else None


_POSIX_PRED: dict[str, Callable[[str], bool]] = {
    "alpha": str.isalpha, "digit": str.isdigit, "alnum": str.isalnum, "upper": str.isupper, "lower": str.islower,
    "space": str.isspace, "punct": lambda c: c.isprintable() and not c.isalnum() and not c.isspace(), "xdigit": lambda c: c in "0123456789abcdefABCDEF",
}  # fmt: skip


@functools.lru_cache(maxsize=1024)
def _wild_tokens(pat: str) -> tuple:
    toks: list[tuple] = []
    i, n = 0, len(pat)
    while i < n:
        c = pat[i]
        if c == "\\" and i + 1 < n:
            toks.append(("c", pat[i + 1]))
            i += 2
        elif c == "*":
            if not toks or toks[-1] != ("*",):
                toks.append(("*",))
            i += 1
        elif c == "?":
            toks.append(("?",))
            i += 1
        elif c == "[":
            j = i + 1
            neg = j < n and pat[j] in "!^"
            j += neg
            k = j + 1 if j < n and pat[j] == "]" else j
            while k < n and pat[k] != "]":
                end = pat.find(":]", k + 2) if pat.startswith("[:", k) else -1
                k = end + 2 if end >= 0 else k + 1
            if k >= n:
                toks.append(("c", "["))
                i += 1
                continue
            toks.append(("[", neg, pat[j:k]))
            i = k + 1
        else:
            toks.append(("c", c))
            i += 1
    return tuple(toks)


def _in_class(neg: bool, body: str, ch: str) -> bool:
    ok, i = False, 0
    while i < len(body):
        m = re.match(r"\[:(\w+):\]", body[i:])
        if m:
            ok = ok or _POSIX_PRED.get(m.group(1), lambda _c: False)(ch)
            i += m.end()
        elif i + 2 < len(body) and body[i + 1] == "-":
            ok = ok or body[i] <= ch <= body[i + 2]
            i += 3
        else:
            ok = ok or body[i] == ch
            i += 1
    return ok != neg


def _wild(toks: tuple, s: str, fold: bool = False) -> bool:
    """Wildcard match in O(len(toks) * len(s)): greedy, retrying only the last ``*`` (no regex backtracking)."""
    p = i = 0
    star, mark, n = -1, 0, len(toks)
    while i < len(s):
        t = toks[p] if p < n else None
        if t is not None and t[0] == "*":
            star, mark, p = p, i, p + 1
        elif t is not None and (t[0] == "?" or (t[0] == "c" and (t[1] == s[i] or (fold and t[1].lower() == s[i].lower()))) or (t[0] == "[" and _in_class(t[1], t[2], s[i]))):
            p, i = p + 1, i + 1
        elif star >= 0:
            mark += 1
            p, i = star + 1, mark
        else:
            return False
    while p < n and toks[p][0] == "*":
        p += 1
    return p == n


def glob_match(pattern: str, path: str) -> bool:
    """Bash pathname matching of an absolute ``pattern`` against ``path``: ``*``/``?``/``[..]`` stay within a
    component, and a leading dot must be matched literally."""
    ps, ss = pattern.split("/"), path.split("/")
    if len(ps) != len(ss):
        return False
    for a, b in zip(ps, ss, strict=True):
        if a == b:
            continue
        if b.startswith(".") and a[:1] in ("*", "?", "["):
            return False
        if not _wild(_wild_tokens(a), b):
            return False
    return True


def expand(pattern: str, known: Iterable[str]) -> list[str]:
    """Brace-expand ``pattern`` and match each glob alternative against ``known`` absolute paths.

    A literal alternative (no ``* ? [``) comes back as itself whether or not it is known: it names
    the path whatever exists. A glob that matches nothing yields nothing (the shell would pass the
    pattern through and the command would fail on it).
    """
    out: list[str] = []
    pool: list[str] | None = None
    for alt in _braces(pattern):
        if _has_glob(alt):
            if pool is None:
                pool = sorted(set(known))
            out.extend(k for k in pool if glob_match(alt, k))
        else:
            out.append(alt)
    return list(dict.fromkeys(out))


# ============================================================================================
# Lexer
# ============================================================================================
class _Heredoc:
    __slots__ = ("delim", "strip_tabs", "quoted", "fd", "body")

    def __init__(self, delim: str, strip_tabs: bool, quoted: bool, fd: str):
        self.delim, self.strip_tabs, self.quoted, self.fd = delim, strip_tabs, quoted, fd
        self.body = ""


class _State:
    def __init__(self, cwd: str | None, env: dict[str, str | None]):
        self.cwd = cwd
        self.env = env


_MISSING = object()


def _skip_dq(s: str, j: int) -> int:
    n = len(s)
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == '"':
            return j + 1
        j += 1
    return n


def _match_paren(s: str, i: int) -> tuple[str, int]:
    """``s[i] == "("``: the text up to the matching ``)`` and the index after it."""
    depth, j, n = 0, i, len(s)
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "'":
            k = s.find("'", j + 1)
            j = n if k < 0 else k + 1
            continue
        if c == '"':
            j = _skip_dq(s, j + 1)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return s[i + 1 : j], j + 1
        j += 1
    return s[i + 1 :], n


def _match_brace(s: str, i: int) -> tuple[str, int]:
    depth, j, n = 0, i, len(s)
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "'":
            k = s.find("'", j + 1)
            j = n if k < 0 else k + 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1 : j], j + 1
        j += 1
    return s[i + 1 :], n


_C_ESC = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?"}


def _c_escapes(s: str, echo: bool = False) -> tuple[str, bool]:
    """Backslash escapes as printf / ``echo -e`` / ``$'...'`` decode them; (text, stopped at ``\\c``)."""
    out, i, n = [], 0, len(s)
    while i < n:
        c = s[i]
        if c != "\\" or i + 1 >= n:
            out.append(c)
            i += 1
            continue
        d = s[i + 1]
        if d in _C_ESC:
            out.append(_C_ESC[d])
            i += 2
        elif d == "c":
            return "".join(out), True
        elif d == "x":
            m = re.match(r"[0-9a-fA-F]{1,2}", s[i + 2 :])
            if m:
                out.append(chr(int(m.group(0), 16)))
                i += 2 + m.end()
            else:
                out.append("\\x")
                i += 2
        elif d in "uU":
            m = re.match(r"[0-9a-fA-F]{1,4}" if d == "u" else r"[0-9a-fA-F]{1,8}", s[i + 2 :])
            if m:
                try:
                    out.append(chr(int(m.group(0), 16)))
                except (ValueError, OverflowError):
                    out.append("?")
                i += 2 + m.end()
            else:
                out.append("\\" + d)
                i += 2
        elif d in "01234567":
            m = re.match(r"0?[0-7]{1,3}" if echo else r"[0-7]{1,3}", s[i + 1 :])
            digits = m.group(0) if m else d
            out.append(chr(int(digits, 8) & 0xFF))
            i += 1 + len(digits)
        else:
            out.append("\\" + d)
            i += 2
    return "".join(out), False


class _Lexer:
    """Tokens of one command line: words, separators, redirects (with their target word), parens.

    Heredoc bodies are consumed at the end of the line that opened them and never tokenised.
    """

    def __init__(self, src: str, state: _State):
        self.s, self.n, self.i = src, len(src), 0
        self.st = state
        self.pending: list[_Heredoc] = []

    # -- variables -------------------------------------------------------------------------
    def _lookup(self, name: str) -> str | None:
        v = self.st.env.get(name, _MISSING)
        if v is _MISSING:
            if name == "HOME":
                return HOME
            if name == "PWD":
                return self.st.cwd
            return None
        return v  # type: ignore[return-value]

    def _dollar(self, w: Word, quoted: bool) -> str:
        s, n, i = self.s, self.n, self.i
        nxt = s[i + 1] if i + 1 < n else ""
        if nxt == "(":
            inner, end = _match_paren(s, i + 1)
            self.i = end
            w.opaque = True
            if not inner.startswith("("):
                w.subs.append(inner)
            return s[i:end]
        if nxt == "{":
            inner, end = _match_brace(s, i + 1)
            self.i = end
            m = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)(?:(:?[-=])(.*))?", inner, re.S)
            if m:
                val = self._lookup(m.group(1))
                if val is not None and (m.group(2) is None or val != "" or ":" not in m.group(2)):
                    return val
                if m.group(2) is None:
                    w.vars.append(m.group(1))
                    return "${" + m.group(1) + "}"
            w.opaque = True
            return "${" + inner + "}"
        if nxt == "'" and not quoted:
            j, buf = i + 2, []
            while j < n and s[j] != "'":
                if s[j] == "\\" and j + 1 < n:
                    buf.append(s[j : j + 2])
                    j += 2
                    continue
                buf.append(s[j])
                j += 1
            self.i = min(j + 1, n)
            w.quoted = True
            return _c_escapes("".join(buf))[0]
        if nxt == '"' and not quoted:
            self.i += 2
            w.quoted = True
            return self._dquoted(w)
        m = _NAME.match(s, i + 1)
        if m:
            self.i = m.end()
            val = self._lookup(m.group(0))
            if val is not None:
                return val
            w.vars.append(m.group(0))
            return "${" + m.group(0) + "}"
        if nxt and (nxt.isdigit() or nxt in "@*#?$!-"):
            self.i += 2
            w.opaque = True
            return "$" + nxt
        self.i += 1
        return "$"

    def _backtick(self, w: Word) -> str:
        s, n = self.s, self.n
        j = self.i + 1
        while j < n and s[j] != "`":
            j += 2 if s[j] == "\\" else 1
        inner = s[self.i + 1 : min(j, n)]
        self.i = min(j + 1, n)
        w.opaque = True
        w.subs.append(inner)
        return "`" + inner + "`"

    def _dquoted(self, w: Word, expand: bool = True) -> str:
        s, n = self.s, self.n
        out: list[str] = []
        while self.i < n:
            c = s[self.i]
            if c == '"':
                self.i += 1
                break
            if c == "\\" and self.i + 1 < n:
                nxt = s[self.i + 1]
                if nxt in '$`"\\':
                    out.append(nxt)
                    self.i += 2
                    continue
                if nxt == "\n":
                    self.i += 2
                    continue
                out.append("\\")
                self.i += 1
                continue
            if c == "$" and expand:
                out.append(self._dollar(w, quoted=True))
                continue
            if c == "`" and expand:
                out.append(self._backtick(w))
                continue
            out.append(c)
            self.i += 1
        return "".join(out)

    # -- words -----------------------------------------------------------------------------
    def word(self, expand: bool = True) -> Word:
        s, n = self.s, self.n
        start = self.i
        w = Word("")
        buf: list[str] = []
        while self.i < n:
            c = s[self.i]
            if c in _META:
                break
            if c == "\\":
                if self.i + 1 < n:
                    nxt = s[self.i + 1]
                    self.i += 2
                    if nxt != "\n":
                        buf.append(nxt)
                        w.quoted = True
                    continue
                self.i += 1
                continue
            if c == "'":
                j = s.find("'", self.i + 1)
                j = n if j < 0 else j
                buf.append(s[self.i + 1 : j])
                self.i = j + 1
                w.quoted = True
                continue
            if c == '"':
                self.i += 1
                buf.append(self._dquoted(w, expand))
                w.quoted = True
                continue
            if c == "$" and expand:
                buf.append(self._dollar(w, quoted=False))
                continue
            if c == "`" and expand:
                buf.append(self._backtick(w))
                continue
            if c in "*?[":
                w.glob = True
            buf.append(c)
            self.i += 1
        w.text = "".join(buf)
        w.raw = s[start : self.i]
        return w

    # -- heredocs --------------------------------------------------------------------------
    def _read_heredocs(self) -> None:
        s, n = self.s, self.n
        for h in self.pending:
            lines: list[str] = []
            while self.i < n:
                j = s.find("\n", self.i)
                line = s[self.i : n if j < 0 else j]
                self.i = n if j < 0 else j + 1
                cand = line.lstrip("\t") if h.strip_tabs else line
                if cand.rstrip(" \t\r") == h.delim:
                    break
                lines.append(cand)
            h.body = "".join(line + "\n" for line in lines)
        self.pending = []

    # -- tokens ----------------------------------------------------------------------------
    _REDIR_OPS = ("<<<", "<<-", "<<", "&>>", "&>", ">>", ">|", ">&", "<&", "<>", ">", "<")

    def _redirect(self, fd: str, start: int):
        s = self.s
        op = next(o for o in self._REDIR_OPS if s.startswith(o, self.i))
        self.i += len(op)
        while self.i < self.n and s[self.i] in " \t":
            self.i += 1
        target = None
        if self.i < self.n and (s[self.i] not in _META or (s[self.i] in "<>" and s.startswith("(", self.i + 1))):
            if s[self.i] in "<>":
                inner, end = _match_paren(s, self.i + 1)
                target = Word(s[self.i : end], s[self.i : end], opaque=True, subs=[inner])
                self.i = end
            else:
                target = self.word(expand=op not in ("<<", "<<-"))
        holder = None
        if op in ("<<", "<<-"):
            holder = _Heredoc(target.text if target else "", op == "<<-", bool(target and target.quoted), fd or "0")
            self.pending.append(holder)
        if op == ">|":
            op = ">"
        if op == ">&" and target is not None and not target.text.isdigit() and target.text != "-" and fd in ("", "1"):
            op = "&>"
        if fd and not ((fd == "1" and op.startswith(">")) or (fd == "0" and op.startswith("<"))):
            op = fd + op
        return ("redir", (op, target, holder), start, self.i)

    def tokens(self):
        s, n = self.s, self.n
        while self.i < n:
            c = s[self.i]
            start = self.i
            if c in " \t\r":
                self.i += 1
                continue
            if c == "\\" and s.startswith("\n", self.i + 1):
                self.i += 2
                continue
            if c == "\n":
                self.i += 1
                if self.pending:
                    self._read_heredocs()
                yield ("op", "\n", start, start + 1)
                continue
            if c == "#":
                j = s.find("\n", self.i)
                self.i = n if j < 0 else j
                continue
            if c == "&" and s.startswith(">", self.i + 1):
                yield self._redirect("", start)
                continue
            if c in "<>":
                if s.startswith("(", self.i + 1):
                    inner, end = _match_paren(s, self.i + 1)
                    self.i = end
                    yield ("word", Word(s[start:end], s[start:end], opaque=True, subs=[inner]), start, end)
                    continue
                yield self._redirect("", start)
                continue
            if c in ";&|":
                two = s[self.i : self.i + 2]
                if two in ("&&", "||"):
                    op, self.i = two, self.i + 2
                elif two == "|&" or c == "|":
                    op, self.i = "|", self.i + len(two if two == "|&" else c)
                else:
                    op = ";"
                    self.i += 1
                    while self.i < n and s[self.i] in ";&":
                        self.i += 1
                yield ("op", op, start, self.i)
                continue
            if c == "(":
                self.i += 1
                yield ("lparen", None, start, self.i)
                continue
            if c == ")":
                self.i += 1
                yield ("rparen", None, start, self.i)
                continue
            w = self.word()
            if self.i == start:  # defensive: never loop without progress
                self.i += 1
                continue
            if w.raw.isdigit() and self.i < n and s[self.i] in "<>" and not s.startswith("(", self.i + 1):
                yield self._redirect(w.raw, start)
                continue
            yield ("word", w, start, self.i)


def _expand_heredoc(body: str, env: Mapping[str, str | None], cwd: str | None) -> str | None:
    """An unquoted heredoc body as bash feeds it: escapes and known variables; None if anything else expands."""
    out, i, n = [], 0, len(body)
    while i < n:
        c = body[i]
        if c == "\\" and i + 1 < n:
            d = body[i + 1]
            if d in "$`\\":
                out.append(d)
                i += 2
                continue
            if d == "\n":
                i += 2
                continue
            out.append(c)
            i += 1
            continue
        if c == "`":
            return None
        if c == "$":
            nxt = body[i + 1] if i + 1 < n else ""
            if nxt in ("(",) or nxt.isdigit() or (nxt and nxt in "@*#?$!-"):
                return None
            if nxt == "{":
                inner, end = _match_brace(body, i + 1)
                name = inner if _NAME.fullmatch(inner) else None
                val = _env_value(name, env, cwd) if name else None
                if val is None:
                    return None
                out.append(val)
                i = end
                continue
            m = _NAME.match(body, i + 1)
            if m:
                val = _env_value(m.group(0), env, cwd)
                if val is None:
                    return None
                out.append(val)
                i = m.end()
                continue
        out.append(c)
        i += 1
    return "".join(out)


def _env_value(name: str, env: Mapping[str, str | None], cwd: str | None) -> str | None:
    if name in env:
        return env[name]
    return HOME if name == "HOME" else cwd if name == "PWD" else None


# ============================================================================================
# Segments
# ============================================================================================
def _wrapper_end(name: str, words: list[Word], i: int) -> int:
    """Index of the first word after wrapper ``words[i]`` and its options/operands (len(words) if none)."""
    sub, with_arg, n_pos = _WRAPPERS[name]
    j = i + 1
    if sub is not None:
        if j >= len(words) or words[j].text != sub:
            return i
        j += 1
    while j < len(words):
        t = words[j].text
        if t == "--":
            j += 1
            break
        if name == "env" and _ASSIGN.match(t):
            j += 1
            continue
        if t.startswith("-") and len(t) > 1:
            j += 2 if t in with_arg else 1
            continue
        break
    return min(j + n_pos, len(words))


def _command(words: list[Word]) -> tuple[int, str | None, Word | None, bool]:
    """(index of the executed command word, its verb, the ``-c`` script word of a shell, run by xargs)."""
    i, xargs = 0, False
    while i < len(words):
        w = words[i]
        if not w.quoted and w.raw in _KEYWORDS:
            i += 1
            continue
        if _ASSIGN.match(w.raw):  # NAME= is unquoted when raw starts with it
            i += 1
            continue
        name = posixpath.basename(w.text)
        if name not in _WRAPPERS or w.quoted:
            break
        if name == "command" and i + 1 < len(words) and words[i + 1].text in ("-v", "-V"):
            break
        j = _wrapper_end(name, words, i)
        if j <= i or j >= len(words):
            break
        xargs = xargs or name == "xargs"
        i = j
    if i >= len(words):
        return len(words), None, None, xargs
    verb = posixpath.basename(words[i].text) or None
    script = None
    if verb in _SHELLS:
        k = i + 1
        while k < len(words):
            t = words[k].text
            if t.startswith("-") and not t.startswith("--") and "c" in t[1:] and t[1:].isalpha():
                script = words[k + 1] if k + 1 < len(words) else None
                break
            if t in ("-o", "+o", "-O", "+O"):
                k += 2
                continue
            if t.startswith(("-", "+")):
                k += 1
                continue
            break
    return i, verb, script, xargs


class _Build:
    __slots__ = ("words", "redirs", "start", "end")

    def __init__(self):
        self.words: list[Word] = []
        self.redirs: list[tuple[str, Word | None, _Heredoc | None]] = []
        self.start = -1
        self.end = -1

    def empty(self) -> bool:
        return not self.words and not self.redirs

    def touch(self, start: int, end: int) -> None:
        if self.start < 0:
            self.start = start
        self.end = end


def _parse(command: str, cwd: str | None, env: dict[str, str | None], depth: int) -> tuple[list[Segment], str | None]:
    st = _State(cwd, env)
    lx = _Lexer(command, st)
    segs: list[Segment] = []
    fixups: list[tuple[Segment, _Heredoc, dict[str, str | None], str | None]] = []
    cur = _Build()
    pending_op = ""
    cwd_stack: list[str | None] = []
    dir_stack: list[str | None] = []
    loops: list[tuple[str | None, list[str] | None]] = []

    def finish(b: _Build, op_before: str) -> None:
        words = b.words
        start, verb, script, via_xargs = _command(words)
        stdin_doc = None
        stdin_text = None
        for op, w, h in b.redirs:
            if h is not None and h.fd == "0":
                stdin_doc = h
            elif op == "<<<":
                stdin_doc = None
                stdin_text = None if w is None or w.dynamic else w.text + "\n"
        seg = Segment(
            text=command[b.start : b.end].strip(),
            verb=verb,
            argv=[w.text for w in words],
            redirects=[(op, w.text if w is not None else "") for op, w, _ in b.redirs],
            heredoc=None,
            cwd=st.cwd,
            op_before=op_before,
            cmd=[w.text for w in words[start:]],
            loops={k: list(v) for k, v in loops if k and v is not None},
            xargs=via_xargs,
            stdin_text=stdin_text,
            prev=segs[-1] if op_before == "|" and segs else None,
            words=words,
            cmd_start=start,
            redirect_words=[w for _, w, _ in b.redirs],
        )
        if stdin_doc is not None:
            fixups.append((seg, stdin_doc, dict(st.env), st.cwd))
        if script is not None and depth < MAX_DEPTH:
            seg.inner, _ = _parse(script.text, st.cwd, dict(st.env), depth + 1)
            first = next((s for s in seg.inner if s.verb and s.verb not in _SETUP), None) or next((s for s in seg.inner if s.verb), None)
            seg.verb = first.verb if first else None
            seg.cmd = first.cmd if first else []
        _effects(seg, st, loops, dir_stack)
        segs.append(seg)

    for kind, val, start, end in lx.tokens():
        if kind == "word":
            cur.words.append(val)
            cur.touch(start, end)
        elif kind == "redir":
            cur.redirs.append(val)
            cur.touch(start, end)
        else:
            if not cur.empty():
                finish(cur, pending_op)
                cur = _Build()
                if kind == "op":
                    pending_op = val
            elif kind == "op":
                if not segs:
                    pass
                elif not (pending_op in ("&&", "||", "|") and val == "\n"):
                    pending_op = val
            if kind == "lparen":
                cwd_stack.append(st.cwd)
            elif kind == "rparen" and cwd_stack:
                st.cwd = cwd_stack.pop()
    if not cur.empty():
        finish(cur, pending_op)
    for seg, h, env_at, cwd_at in fixups:
        seg.heredoc = h.body
        seg.heredoc_quoted = h.quoted
        seg.stdin_text = h.body if h.quoted else _expand_heredoc(h.body, env_at, cwd_at)
    return segs, st.cwd


def _effects(seg: Segment, st: _State, loops: list, dir_stack: list) -> None:
    """What a segment changes for the ones after it: variables, cwd, loop scope."""
    words = seg.words
    if words and not words[0].quoted and words[0].raw in ("while", "until"):
        loops.append((None, None))
    if words and not words[0].quoted and words[0].raw == "done" and loops:
        loops.pop()
    cmd = seg.cmd_words
    if not cmd and seg.inner == []:
        for w in words:
            m = _ASSIGN.match(w.raw)
            if m:
                st.env[m.group(1)] = None if (m.group(2) or w.dynamic) else w.text[len(m.group(1)) + 1 :]
        return
    if seg.inner:
        return
    name = cmd[0].text
    if name in ("export", "declare", "typeset", "local", "readonly"):
        for w in cmd[1:]:
            m = _ASSIGN.match(w.text)
            if m:
                st.env[m.group(1)] = None if (m.group(2) or w.dynamic) else w.text[len(m.group(1)) + 1 :]
    elif name == "unset":
        for w in cmd[1:]:
            if _NAME.fullmatch(w.text):
                st.env[w.text] = None
    elif name in ("read", "mapfile", "readarray"):
        for w in cmd[1:]:
            if _NAME.fullmatch(w.text):
                st.env[w.text] = None
    elif name in ("cd", "pushd"):
        args = [w for w in cmd[1:] if not (w.text.startswith("-") and len(w.text) > 1)]
        if name == "pushd":
            dir_stack.append(st.cwd)
        if not args:
            if name == "cd":
                st.cwd = HOME
            return
        target = args[0]
        if target.text == "-":
            return
        if target.dynamic:
            st.cwd = None
        elif st.cwd is None and not target.text.startswith(("/", "~")):
            st.cwd = None
        else:
            st.cwd = resolve(target.text, st.cwd)
    elif name == "popd":
        if dir_stack:
            st.cwd = dir_stack.pop()
    elif name in ("for", "select") and len(cmd) >= 2 and _NAME.fullmatch(cmd[1].text):
        var = cmd[1].text
        items = [w.text for w in cmd[3:]] if len(cmd) > 2 and cmd[2].text == "in" and not any(w.dynamic for w in cmd[3:]) else None
        loops.append((var, items))
        st.env[var] = None
    elif name == "for":
        loops.append((None, None))


def flat(segments: Iterable[Segment]) -> list[Segment]:
    """Segments with every ``bash -c`` wrapper replaced by its inner segments (recursively)."""
    out: list[Segment] = []
    for s in segments:
        out.extend(flat(s.inner) if s.inner else [s])
    return out


def split(command: str, cwd: str | None = None) -> tuple[list[Segment], str | None]:
    """Segments of ``command`` and the cwd after it (persisting it across steps is the caller's job)."""
    if not isinstance(command, str) or not command.strip():
        return [], cwd
    try:
        return _parse(command, cwd, {}, 0)
    except Exception as e:  # never raise on agent-controlled text
        logger.debug("shell.split failed: %r", e)
        return [], cwd


def _strip_ansi(text: str) -> str:
    return _ANSI.sub("", text or "")


# ============================================================================================
# Operand helpers
# ============================================================================================
def _operands(words: list[Word], with_arg: Iterable[str] = ()) -> tuple[list[Word], dict[str, list[str]]]:
    """(operands, options) of a command's arguments; ``with_arg`` options consume the next word."""
    with_arg = frozenset(with_arg)
    ops: list[Word] = []
    opts: dict[str, list[str]] = {}
    i, end = 0, False
    while i < len(words):
        w = words[i]
        t = w.text
        if not end and t == "--":
            end = True
        elif not end and t.startswith("-") and t != "-":
            if t.startswith("--") and "=" in t:
                k, v = t.split("=", 1)
                opts.setdefault(k, []).append(v)
            elif t in with_arg:
                opts.setdefault(t, []).append(words[i + 1].text if i + 1 < len(words) else "")
                i += 1
            elif not t.startswith("--") and len(t) > 2 and t[:2] in with_arg:
                opts.setdefault(t[:2], []).append(t[2:])
            else:
                opts.setdefault(t, []).append("")
        else:
            ops.append(w)
        i += 1
    return ops, opts


def _flag(opts: Mapping[str, list[str]], short: str = "", long: Iterable[str] = ()) -> bool:
    if any(k in opts for k in long):
        return True
    return bool(short) and any(k.startswith("-") and not k.startswith("--") and k[1:].isalpha() and any(c in k[1:] for c in short) for k in opts)


def _loop_texts(w: Word, seg: Segment) -> list[str] | None:
    """``w.text`` with ``for`` variables replaced by each item; None if it still holds an unknown expansion."""
    if w.opaque:
        return None
    if not w.vars:
        return [w.text]
    texts = [w.text]
    for name in dict.fromkeys(w.vars):
        items = seg.loops.get(name)
        if items is None:
            return None
        texts = [t.replace("${" + name + "}", item) for t in texts for item in items][:MAX_BRACE]
    return texts


def _known_dirs(paths: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for p in paths:
        d = posixpath.dirname(p)
        while d and d not in out and d != "/":
            out.add(d)
            d = posixpath.dirname(d)
    return out


def _paths(w: Word, seg: Segment, known: list[str], literal: bool = True) -> list[str]:
    """Absolute paths an operand word names: loop items, braces, globs against ``known``, ``$(ls|find ...)``."""
    texts = _loop_texts(w, seg)
    if texts is None:
        sub = w.subs[0] if len(w.subs) == 1 else ""
        if sub and len(sub) < 2000 and "$(" not in sub and "`" not in sub and w.raw.strip("\"'") in (f"$({sub})", f"`{sub}`"):
            inner, _ = split(w.subs[0], seg.cwd)
            if inner:
                return _listed(inner[-1], known) or []
        return []
    out: list[str] = []
    for t in texts:
        if seg.cwd is None and not t.startswith(("/", "~")):
            continue
        for alt in _braces(t):
            p = resolve(alt, seg.cwd)
            if (w.glob or w.vars) and _has_glob(alt):
                out.extend(k for k in known if glob_match(p, k))
            elif literal:
                out.append(p)
    return list(dict.fromkeys(out))


def _target(w: Word | None, seg: Segment) -> tuple[str, bool]:
    """(absolute path, unresolvable) of a write target word."""
    if w is None:
        return "", True
    texts = _loop_texts(w, seg)
    if texts is None or len(texts) != 1:
        return "", True
    t = texts[0]
    if not t:
        return "", True
    if seg.cwd is None and not t.startswith(("/", "~")):
        return "", True
    return resolve(t, seg.cwd), False


def _derive(seg: Segment, words: list[Word]) -> Segment:
    """A segment for a command built from another's words (xargs, find -exec)."""
    start, verb, _, _ = _command(words)
    return Segment(
        text=" ".join(w.text for w in words),
        verb=verb,
        argv=[w.text for w in words],
        redirects=[],
        heredoc=None,
        cwd=seg.cwd,
        op_before=seg.op_before,
        cmd=[w.text for w in words[start:]],
        loops=seg.loops,
        words=words,
        cmd_start=start,
    )


def _xargs_replace(seg: Segment) -> str | None:
    pre = seg.words[: seg.cmd_start]
    for k, w in enumerate(pre):
        t = w.text
        if t == "-I" and k + 1 < len(pre):
            return pre[k + 1].text
        if t.startswith("-I") and len(t) > 2:
            return t[2:]
        if t in ("-i", "--replace"):
            return "{}"
        if t.startswith("--replace="):
            return t.split("=", 1)[1]
    return None


def _with_input(seg: Segment, listed: list[str]) -> Segment:
    """``seg`` (run by xargs) with the piped paths as operands."""
    rep = _xargs_replace(seg)
    words = list(seg.cmd_words)
    extra = [Word(p, p) for p in listed]
    if rep and any(rep in w.text for w in words):
        new: list[Word] = []
        for w in words:
            if rep in w.text:
                new.extend(Word(w.text.replace(rep, p), p) for p in listed)
            else:
                new.append(w)
        words = new
    else:
        words = words + extra
    return _derive(seg, words)


# ============================================================================================
# find / ls
# ============================================================================================
_FIND_ARG = frozenset(
    {
        "-newer", "-size", "-mtime", "-mmin", "-atime", "-amin", "-ctime", "-cmin", "-user", "-group", "-perm", "-links",
        "-inum", "-samefile", "-uid", "-gid", "-regextype", "-fstype", "-newermt", "-used", "-iregex", "-regex", "-lname",
        "-ilname", "-context", "-fprint", "-fprint0", "-fls", "-printf",
    }
)  # fmt: skip


def _find(seg: Segment, known: list[str]) -> tuple[list[str], list[tuple[str, list[Word]]]]:
    """(known paths a ``find`` matches, its actions: ("exec", words) / ("delete", []))."""
    words = seg.cmd_words[1:]
    roots: list[Word] = []
    i = 0
    while i < len(words) and not words[i].text.startswith(("-", "(", "!", ")")):
        roots.append(words[i])
        i += 1
    terms: list[list[tuple[bool, str, str]]] = [[]]
    actions: list[tuple[str, list[Word]]] = []
    maxdepth = mindepth = None
    neg = False
    while i < len(words):
        t = words[i].text
        nxt = words[i + 1].text if i + 1 < len(words) else ""
        if t in ("-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename", "-type"):
            terms[-1].append((neg, t, nxt))
            neg = False
            i += 2
        elif t in ("-maxdepth", "-mindepth"):
            try:
                if t == "-maxdepth":
                    maxdepth = int(nxt)
                else:
                    mindepth = int(nxt)
            except ValueError:
                pass
            i += 2
        elif t in ("-o", "-or"):
            terms.append([])
            i += 1
        elif t in ("!", "-not"):
            neg = True
            i += 1
        elif t in ("-exec", "-execdir", "-ok", "-okdir"):
            j = i + 1
            while j < len(words) and words[j].text not in (";", "+"):
                j += 1
            actions.append(("exec", words[i + 1 : j]))
            i = j + 1
        elif t == "-delete":
            actions.append(("delete", []))
            i += 1
        elif t in _FIND_ARG:
            i += 2
        else:
            i += 1
    if not roots:
        roots = [Word(".", ".")]
    files = set(known)
    dirs = _known_dirs(files)
    out: list[str] = []
    for r in roots:
        if r.dynamic:
            continue
        root = resolve(r.text, seg.cwd) if (seg.cwd or r.text.startswith(("/", "~"))) else None
        if root is None:
            continue
        shown_root = r.text.rstrip("/") or "/"
        for p in sorted(files | dirs):
            if p != root and not p.startswith(root.rstrip("/") + "/"):
                continue
            rel = p[len(root) :].lstrip("/")
            depth = 0 if not rel else rel.count("/") + 1
            if (maxdepth is not None and depth > maxdepth) or (mindepth is not None and depth < mindepth):
                continue
            shown = shown_root if not rel else (shown_root.rstrip("/") + "/" + rel)
            if any(all(_find_test(test, arg, p, shown, p in dirs) != ng for ng, test, arg in term) for term in terms):
                out.append(p)
    return list(dict.fromkeys(out)), actions


def _find_test(test: str, arg: str, path: str, shown: str, is_dir: bool) -> bool:
    if test == "-type":
        return ("d" in arg) if is_dir else ("f" in arg)
    if test in ("-name", "-iname"):
        return _wild(_wild_tokens(arg), posixpath.basename(path), fold=test == "-iname")
    return _wild(_wild_tokens(arg), shown, fold=test in ("-ipath", "-iwholename"))  # find's * crosses /


def _listed(seg: Segment | None, known: list[str]) -> list[str] | None:
    """Paths a pipeline stage prints one per line (``ls``, ``find``, ``echo``, ``printf``), or None if unknown."""
    if seg is None or seg.verb is None:
        return None
    v = seg.verb
    words = seg.cmd_words[1:]
    if v == "find":
        if any(a == "exec" for a, _ in _find(seg, known)[1]):
            return None
        return _find(seg, known)[0]
    if v == "ls":
        ops, opts = _operands(words, ("-I", "--ignore", "-w", "--width", "-T", "--tabsize"))
        if _flag(opts, "lgnos", ("--format",)):
            return None
        if not ops:
            ops = [Word(".", ".")]
        out: list[str] = []
        dirs = _known_dirs(known)
        for w in ops:
            for p in _paths(w, seg, known):
                kids = [k for k in sorted(set(known) | dirs) if posixpath.dirname(k) == p]
                if kids and not _flag(opts, "d", ("--directory",)):
                    out.extend(resolve(posixpath.basename(k), seg.cwd) for k in kids)
                elif p in known or p in dirs:
                    out.append(p)
        return out
    if v in ("echo", "printf"):
        text = _echo(words) if v == "echo" else _printf(words)
        if text is None:
            return None
        return [resolve(t, seg.cwd) for t in text.split() if seg.cwd or t.startswith("/")]
    return None


# ============================================================================================
# Reads
# ============================================================================================
_PLAIN_READERS: dict[str, frozenset[str]] = {
    "cat": frozenset(),
    "tac": frozenset({"-s", "--separator"}),
    "nl": frozenset({"-b", "-d", "-f", "-h", "-i", "-l", "-n", "-s", "-v", "-w"}),
    "less": frozenset({"-p", "-x", "-y", "-z", "-j", "-b", "-h", "-o", "-t"}),
    "more": frozenset(),
    "head": frozenset({"-n", "-c", "--lines", "--bytes"}),
    "tail": frozenset({"-n", "-c", "--lines", "--bytes", "-s", "--sleep-interval", "--pid"}),
    "bat": frozenset({"-l", "--language", "-r", "--line-range", "--style", "--theme", "-H", "--highlight-line", "--tabs", "--wrap", "--color", "--paging", "-m"}),
    "batcat": frozenset({"-l", "--language", "-r", "--line-range", "--style", "--theme", "-H", "--highlight-line", "--tabs", "--wrap", "--color", "--paging", "-m"}),
    "sort": frozenset({"-k", "-t", "-o", "-S", "-T", "--key", "--field-separator", "--output", "--buffer-size"}),
    "uniq": frozenset({"-f", "-s", "-w"}),
    "strings": frozenset({"-n", "-t", "-e"}),
    "xxd": frozenset({"-l", "-s", "-c", "-g", "-o"}),
    "od": frozenset({"-t", "-A", "-j", "-N", "-w"}),
    "hexdump": frozenset({"-n", "-s", "-e", "-f"}),
}
_GREP_ARG = frozenset({"-e", "-f", "-m", "-A", "-B", "-C", "-d", "-D", "--regexp", "--file", "--max-count", "--context", "--after-context", "--before-context", "--label", "--color", "--colour"})
_RG_ARG = frozenset(
    {"-e", "-f", "-g", "-t", "-T", "-m", "-A", "-B", "-C", "-j", "-M", "-E", "-d", "--glob", "--iglob", "--type", "--type-not", "--max-count", "--regexp", "--file",
     "--context", "--threads", "--max-columns", "--sort", "--sortr", "--color", "--encoding", "--max-depth", "--ignore-file", "-G", "--file-search-regex"}
)  # fmt: skip
_SED_ARG = frozenset({"-e", "-f", "-l", "--expression", "--file", "--line-length"})
_AWK_ARG = frozenset({"-F", "-v", "-f", "--field-separator", "--assign", "--file", "-i", "--include", "-W", "-E"})


def read_targets(seg: Segment, known: Iterable[str]) -> list[str]:
    """Absolute paths a reading verb in ``seg`` consumes (globs, loops, find/xargs expanded against ``known``)."""
    try:
        return list(dict.fromkeys(_reads(seg, sorted(set(known)), 0)))
    except Exception as e:  # never raise on agent-controlled text
        logger.debug("shell.read_targets failed: %r", e)
        return []


def _reads(seg: Segment, known: list[str], depth: int) -> list[str]:
    out: list[str] = []
    if seg.inner and depth < MAX_DEPTH:
        for s in seg.inner:
            out.extend(_reads(s, known, depth + 1))
        return out
    if seg.xargs and seg.verb not in (None, "xargs"):
        listed = _listed(seg.prev, known)
        if listed:
            seg = _with_input(seg, listed)
    v = seg.verb
    if v is None:
        return out
    args = seg.cmd_words[1:]
    files: list[Word] = []
    recursive_dirs = False
    if v in _PLAIN_READERS:
        files, _ = _operands(args, _PLAIN_READERS[v])
    elif v in ("grep", "egrep", "fgrep", "zgrep"):
        ops, opts = _operands(args, _GREP_ARG)
        files = ops if _flag(opts, "ef", ("--regexp", "--file")) else ops[1:]
        recursive_dirs = _flag(opts, "rR", ("--recursive", "--dereference-recursive"))
        if recursive_dirs and not files:
            files = [Word(".", ".")]
    elif v in ("rg", "ag", "ack"):
        ops, opts = _operands(args, _RG_ARG)
        files = ops if _flag(opts, "ef", ("--regexp", "--file")) else ops[1:]
        recursive_dirs = True
        if not files:
            files = [Word(".", ".")]
    elif v == "sed":
        ops, opts = _operands(args, _SED_ARG)
        if any(k.startswith("-i") or k.startswith("--in-place") for k in opts):
            return out
        files = ops if ("-e" in opts or "--expression" in opts or "-f" in opts or "--file" in opts) else ops[1:]
    elif v in ("awk", "gawk", "mawk", "nawk"):
        ops, opts = _operands(args, _AWK_ARG)
        files = [w for w in (ops if ("-f" in opts or "--file" in opts) else ops[1:]) if not _ASSIGN.match(w.text)]
        if any(x == "inplace" for x in opts.get("-i", [])):
            return out
    elif v == "find":
        matched, actions = _find(seg, known)
        for kind, words in actions:
            if kind == "exec" and words and posixpath.basename(words[0].text) in _READ_VERBS:
                out.extend(p for p in matched if p in known)
        return out
    elif _PYTHON.match(v):
        stdin = seg.stdin_text
        if stdin is None and seg.op_before == "|" and seg.prev is not None:
            stdin = _stdout(seg.prev, seg.prev.stdin_text, _Files(None))
        code, _, _ = _python_code(seg, stdin, _Files(None))
        if code:
            out.extend(_py_reads(code, seg.cwd))
        return out
    else:
        return out
    for (op, _), w in zip(seg.redirects, seg.redirect_words, strict=False):
        if op == "<" and w is not None:
            files.append(w)
    for w in files:
        if w.text == "-":
            continue
        for p in _paths(w, seg, known):
            if recursive_dirs and p not in known:
                under = [k for k in known if k.startswith(p.rstrip("/") + "/")]
                out.extend(under if under else [p])
            else:
                out.append(p)
    return out


_READ_VERBS = frozenset(_PLAIN_READERS) | {"grep", "egrep", "fgrep", "rg", "sed", "awk"}


# ============================================================================================
# Writes
# ============================================================================================
class _Files:
    """Contents known before and during one command: an overlay over the caller's mapping."""

    def __init__(self, known):
        if isinstance(known, Mapping):
            self.base = known
        elif known is None:
            self.base = {}
        else:
            self.base = dict.fromkeys(known)
        self.over: dict[str, str | None] = {}
        self.gone: set[str] = set()

    def has(self, p: str) -> bool:
        return p not in self.gone and (p in self.over or p in self.base)

    def get(self, p: str) -> str | None:
        if p in self.gone:
            return None
        if p in self.over:
            return self.over[p]
        v = self.base.get(p)
        return v if isinstance(v, str) else None

    def paths(self) -> list[str]:
        return sorted(p for p in set(self.base) | set(self.over) if p not in self.gone)

    def under(self, d: str) -> list[str]:
        pre = d.rstrip("/") + "/"
        return [p for p in self.paths() if p.startswith(pre)]

    def put(self, p: str, c: str | None) -> None:
        self.over[p] = c
        self.gone.discard(p)

    def drop(self, p: str) -> None:
        self.over.pop(p, None)
        self.gone.add(p)

    def apply(self, op: WriteOp) -> None:
        if op.applied or not op.path:
            return
        op.applied = True
        if op.op in ("overwrite", "edit"):
            self.put(op.path, op.body)
        elif op.op == "append":
            prior = self.get(op.path) if self.has(op.path) else ""
            self.put(op.path, None if prior is None or op.body is None else prior + op.body)
        elif op.op == "unknown":
            for p in [op.path, *self.under(op.path)]:
                if self.has(p):
                    self.put(p, None)
        elif op.op == "delete":
            for p in [op.path, *self.under(op.path)]:
                self.drop(p)
        elif op.op in ("copy", "move") and op.src:
            dst = op.path
            if op.dir_target or (op.dir_target is None and self.under(dst)):
                dst = posixpath.join(dst, posixpath.basename(op.src))
            moved = [(op.src, dst)] if self.has(op.src) else []
            moved += [(p, dst + p[len(op.src) :]) for p in self.under(op.src)]
            for a, b in moved:
                self.put(b, self.get(a))
                if op.op == "move":
                    self.drop(a)


def write_ops(command: str, cwd: str | None, known: Mapping[str, str | None] | Iterable[str] | None = None) -> list[WriteOp]:
    """Every file-system change ``command`` makes, in order.

    ``known`` (optional) maps absolute paths to their content before the command (None: exists,
    content unknown) -- the replay passes its state. It lets globs in ``rm``/``cp``/``mv``/``sed``
    operands expand, ``cat A > B`` and ``sed -i`` produce the new content, and a script written
    earlier (``python /tmp/fix.py``) be analysed. Without it, edits have ``body=None``.
    """
    if not isinstance(command, str) or not command.strip():
        return []
    try:
        segs, _ = split(command, cwd)
        return _ops(segs, _Files(known), 0)
    except Exception as e:  # never raise on agent-controlled text
        logger.debug("shell.write_ops failed: %r", e)
        return []


def _stdin(seg: Segment, files: _Files, outs: dict[int, str | None]) -> tuple[bool, str | None]:
    """(has stdin, its text) from the segment's own heredoc / here-string / ``<`` file, else the pipe."""
    for (op, _), w in reversed(list(zip(seg.redirects, seg.redirect_words, strict=False))):
        if op in ("<<", "<<-", "<<<"):
            return True, seg.stdin_text
        if op == "<" and w is not None:
            p, var = _target(w, seg)
            return True, None if var else files.get(p)
    if seg.op_before == "|" and seg.prev is not None:
        return True, outs.get(id(seg.prev))
    return False, None


def _ops(segs: list[Segment], files: _Files, depth: int) -> list[WriteOp]:
    ops: list[WriteOp] = []
    outs: dict[int, str | None] = {}
    for seg in segs:
        has_in, stdin = _stdin(seg, files, outs)
        py, dynamic = None, False
        if seg.verb and _PYTHON.match(seg.verb) and not seg.inner and not seg.xargs:
            code, argv, dynamic = _python_code(seg, stdin if has_in else None, files)
            py = _py_run(code, seg.cwd, argv, files, depth) if code else None
        if seg.verb and _PYTHON.match(seg.verb):
            out = py.stdout() if py is not None else None
            stdout = None if (out is not None and dynamic and _SHELL_LEFT.search(out)) else out
        else:
            stdout = _stdout(seg, stdin if has_in else None, files)
        mine: list[WriteOp] = []
        if seg.inner and depth < MAX_DEPTH:
            mine += _ops(seg.inner, files, depth + 1)
        mine += _redirect_ops(seg, stdout)
        for op in mine:
            files.apply(op)
        verb_ops = _unresolved(py.ops, dynamic) if py is not None else _verb_ops(seg, stdin if has_in else None, files, depth)
        for op in verb_ops:
            files.apply(op)
        mine += verb_ops
        for op in mine:
            op.verb = op.verb or seg.verb
        outs[id(seg)] = "" if any(o in (">", ">>", "&>", "&>>") for o, _ in seg.redirects) else stdout
        ops += mine
    return ops


def _source(seg: Segment) -> str:
    if seg.heredoc is not None and seg.verb in ("cat", "tee"):
        return "heredoc"
    if seg.verb in ("echo", "printf"):
        return seg.verb
    if seg.verb and _PYTHON.match(seg.verb):
        return "python"
    return "redirect"


def _redirect_ops(seg: Segment, stdout: str | None) -> list[WriteOp]:
    outs = [(k, op, w) for k, ((op, _), w) in enumerate(zip(seg.redirects, seg.redirect_words, strict=False)) if op in (">", ">>", "&>", "&>>", "2>", "2>>")]
    last = max((k for k, op, _ in outs if not op.startswith("2")), default=-1)
    ops: list[WriteOp] = []
    for k, op, w in outs:
        path, var = _target(w, seg)
        if path and _DEV.match(path):
            continue
        append = op.endswith(">>")
        if op.startswith("2"):
            body = None
        elif k == last:
            body = stdout
        else:
            body = ""
        ops.append(WriteOp(path, "append" if append else "overwrite", body, _source(seg), variable=var, target=w.text if w else ""))
    return ops


# -- what a segment prints -----------------------------------------------------------------
def _echo(words: list[Word]) -> str | None:
    newline, escapes = True, False
    i = 0
    while i < len(words) and re.fullmatch(r"-[neE]+", words[i].text):
        flags = words[i].text[1:]
        newline = newline and "n" not in flags
        escapes = ("e" in flags) or (escapes and "E" not in flags)
        i += 1
    rest = words[i:]
    if any(w.dynamic for w in rest):
        return None
    text = " ".join(w.text for w in rest)
    if escapes:
        text, stopped = _c_escapes(text, echo=True)
        if stopped:
            return text
    return text + ("\n" if newline else "")


def _printf(words: list[Word]) -> str | None:
    """``printf FMT ARGS``: literal format with only ``%s``/``%%`` and literal arguments, else None."""
    if words and words[0].text == "--":
        words = words[1:]
    if not words or any(w.dynamic for w in words) or words[0].text.startswith("-v"):
        return None
    fmt, args = words[0].text, [w.text for w in words[1:]]
    pieces: list[str | None] = []  # None = a %s slot
    buf: list[str] = []
    i = 0
    while i < len(fmt):
        c = fmt[i]
        if c == "%":
            nxt = fmt[i + 1] if i + 1 < len(fmt) else ""
            if nxt == "%":
                buf.append("%")
            elif nxt == "s":
                pieces.append(_c_escapes("".join(buf))[0])
                pieces.append(None)
                buf = []
            else:
                return None
            i += 2
            continue
        buf.append(c)
        i += 1
    pieces.append(_c_escapes("".join(buf))[0])
    slots = pieces.count(None)
    if not slots:
        return "".join(p for p in pieces if p is not None)
    out: list[str] = []
    k = 0
    while True:
        for p in pieces:
            if p is None:
                out.append(args[k] if k < len(args) else "")
                k += 1
            else:
                out.append(p)
        if k >= len(args):
            break
    return "".join(out)


def _stdout(seg: Segment, stdin: str | None, files: _Files) -> str | None:
    """What the segment prints, when it is a pure producer we can follow; else None."""
    v = seg.verb
    if seg.inner:
        return None
    if v is None:
        return "" if all(_ASSIGN.match(w.raw) for w in seg.words) else None
    args = seg.cmd_words[1:]
    if v == "echo":
        return _echo(args)
    if v == "printf":
        return _printf(args)
    if v in (":", "true"):
        return ""
    if v == "tee":
        return stdin
    if v == "cat":
        ops, opts = _operands(args)
        if any(k not in ("-u",) for k in opts):
            return None
        if not ops:
            return stdin
        parts: list[str] = []
        for w in ops:
            if w.text == "-":
                if stdin is None:
                    return None
                parts.append(stdin)
                continue
            p, var = _target(w, seg)
            if var or w.glob:
                return None
            c = files.get(p)
            if c is None:
                return None
            parts.append(c)
        return "".join(parts)
    if v == "sed":
        ops, opts = _operands(args, _SED_ARG)
        if any(k.startswith(("-i", "--in-place")) for k in opts):
            return None
        prog = _sed_program(ops, opts)
        if prog is None:
            return None
        fn, rest = prog
        if not rest:
            return fn(stdin) if stdin is not None else None
        texts = []
        for w in rest:
            p, var = _target(w, seg)
            c = None if var else files.get(p)
            if c is None:
                return None
            texts.append(c)
        return fn("".join(texts))
    return None


# -- what a verb writes --------------------------------------------------------------------
def _verb_ops(seg: Segment, stdin: str | None, files: _Files, depth: int) -> list[WriteOp]:
    v = seg.verb
    if v is None or seg.inner:
        return []
    if seg.xargs:
        listed = _listed(seg.prev, files.paths())
        if listed is None:
            if v in ("rm", "sed", "mv", "cp", "tee", "touch", "truncate", "perl"):
                return [WriteOp("", "unknown", None, _SOURCE.get(v, "other"))]
            return []
        seg = _with_input(seg, listed)
    args = seg.cmd_words[1:]
    handler = _HANDLERS.get(v)
    if handler is not None:
        return handler(seg, args, stdin, files, depth)
    if _PYTHON.match(v):
        code, argv, dynamic = _python_code(seg, stdin, files)
        return _py_ops(code, seg.cwd, argv, files, depth, dynamic) if code else []
    if v in _SHELLS or v in ("source", "."):
        return _script_ops(seg, args, stdin, files, depth)
    return []


_SOURCE = {"rm": "rm", "sed": "sed", "mv": "mv", "cp": "cp", "tee": "tee"}


def _tee(seg, args, stdin, files, depth):
    ops, opts = _operands(args)
    append = _flag(opts, "a", ("--append",))
    out = []
    for w in ops:
        path, var = _target(w, seg)
        if path and _DEV.match(path):
            continue
        out.append(WriteOp(path, "append" if append else "overwrite", stdin, "heredoc" if seg.heredoc is not None else "tee", variable=var, target=w.text))
    return out


def _cp_mv(seg, args, stdin, files, depth):
    move = seg.verb == "mv"
    with_arg = {"-t", "--target-directory", "-S", "--suffix", "-m", "--mode", "-o", "--owner", "-g", "--group"}
    ops, opts = _operands(args, with_arg)
    if seg.verb == "install" and _flag(opts, "d", ("--directory",)):
        return [WriteOp(p, "mkdir", None, "other", target=w.text) for w in ops for p in [_target(w, seg)[0]] if p]
    target_dir = (opts.get("-t") or opts.get("--target-directory") or [None])[-1]
    recursive = move or _flag(opts, "rRa", ("--recursive", "--archive"))
    if target_dir is not None:
        dst_w, srcs, into = Word(target_dir, target_dir), ops, True
    elif len(ops) >= 2:
        dst_w, srcs = ops[-1], ops[:-1]
        into = True if (len(srcs) > 1 or dst_w.text.endswith("/")) else None
    else:
        return []
    if _flag(opts, "T", ("--no-target-directory",)):
        into = False
    dst, var = _target(dst_w, seg)
    name = "move" if move else "copy"
    source = "mv" if move else "cp"
    out = []
    for w in srcs:
        if w.dynamic and _loop_texts(w, seg) is None:
            out.append(WriteOp(dst, name, None, source, src=None, variable=var, target=dst_w.text, dir_target=into, recursive=recursive))
            continue
        paths = _paths(w, seg, files.paths(), literal=True)
        if not paths and _has_glob(w.text):
            continue
        for p in paths:
            out.append(WriteOp(dst, name, None, source, src=p, variable=var, target=dst_w.text, dir_target=into, recursive=recursive))
    return out


def _rm(seg, args, stdin, files, depth):
    ops, _ = _operands(args)
    out = []
    for w in ops:
        if w.dynamic and _loop_texts(w, seg) is None:
            out.append(WriteOp("", "delete", None, "rm", variable=True, target=w.text))
            continue
        for p in _paths(w, seg, files.paths(), literal=True):
            out.append(WriteOp(p, "delete", None, "rm", target=w.text))
        if seg.cwd is None and not w.text.startswith(("/", "~")):
            out.append(WriteOp("", "delete", None, "rm", variable=True, target=w.text))
    return out


def _mkdir(seg, args, stdin, files, depth):
    ops, _ = _operands(args, {"-m", "--mode"})
    return [WriteOp(p, "mkdir", None, "other", variable=var, target=w.text) for w in ops for p, var in [_target(w, seg)]]


def _touch(seg, args, stdin, files, depth):
    ops, opts = _operands(args, {"-d", "-t", "-r", "--date", "--reference"})
    if _flag(opts, "c", ("--no-create",)):
        return []
    return [WriteOp(p, "append", "", "other", variable=var, target=w.text) for w in ops for p, var in [_target(w, seg)]]


def _truncate(seg, args, stdin, files, depth):
    ops, opts = _operands(args, {"-s", "--size", "-r", "--reference"})
    size = (opts.get("-s") or opts.get("--size") or [None])[-1]
    out = []
    for w in ops:
        p, var = _target(w, seg)
        out.append(WriteOp(p, "overwrite", "", "other", variable=var, target=w.text) if size == "0" else WriteOp(p, "edit", None, "other", variable=var, target=w.text))
    return out


def _sed(seg, args, stdin, files, depth):
    ops, opts = _operands(args, _SED_ARG)
    ops = [w for w in ops if w.text]
    inplace = [k for k in opts if k.startswith("-i") or k == "--in-place" or (k.startswith("-") and not k.startswith("--") and "i" in k[1:] and k[1:].isalpha())]
    if not inplace:
        return []
    suffix = ""
    for k in inplace:
        if k.startswith("-i") and len(k) > 2 and not k[2:].isalpha():
            suffix = k[2:]
        if k == "--in-place" and opts[k] and opts[k][-1]:
            suffix = opts[k][-1]
    prog = _sed_program(ops, opts)
    fn, rest = prog if prog is not None else (None, ops[1:] if not ({"-e", "--expression", "-f", "--file"} & set(opts)) else ops)
    out = []
    for w in rest:
        if w.dynamic and _loop_texts(w, seg) is None:
            out.append(WriteOp("", "edit", None, "sed", variable=True, target=w.text))
            continue
        paths = _paths(w, seg, files.paths(), literal=True)
        if not paths and _has_glob(w.text):
            out.append(WriteOp("", "edit", None, "sed", target=w.text))
        for p in paths:
            if suffix:
                out.append(WriteOp(p + suffix, "copy", None, "sed", src=p, target=w.text + suffix, dir_target=False))
            prior = files.get(p)
            body = fn(prior) if (fn is not None and prior is not None) else None
            out.append(WriteOp(p, "edit", body, "sed", target=w.text))
    return out


def _perl(seg, args, stdin, files, depth):
    ops, opts = _operands(args, {"-e", "-E", "-M", "-I", "-l", "-0"})
    if not any(k.startswith("-") and not k.startswith("--") and "i" in k[1:] for k in opts):
        return []
    files_w = ops if ("-e" in opts or "-E" in opts) else ops[1:]
    return [WriteOp(p, "edit", None, "other", variable=var, target=w.text) for w in files_w for p, var in [_target(w, seg)]]


def _find_ops(seg, args, stdin, files, depth):
    matched, actions = _find(seg, files.paths())
    out: list[WriteOp] = []
    for kind, words in actions:
        if kind == "delete":
            out.extend(WriteOp(p, "delete", None, "rm", target=p) for p in matched)
        elif kind == "exec" and words:
            verb = posixpath.basename(words[0].text)
            if verb not in _HANDLERS and verb not in ("perl",) and not _PYTHON.match(verb):
                continue
            if not any("{}" in w.text for w in words):
                continue
            plus = any(w.text == "+" for w in args)
            groups = [matched] if plus else [[p] for p in matched]
            for group in groups:
                new: list[Word] = []
                for w in words:
                    if "{}" in w.text:
                        new.extend(Word(w.text.replace("{}", p), p) for p in group)
                    else:
                        new.append(w)
                out.extend(_verb_ops(_derive(seg, new), None, files, depth + 1))
            if verb in ("sed", "perl"):
                out.append(WriteOp("", "unknown", None, _SOURCE.get(verb, "other"), target=seg.text))
    return out


def _git(seg, args, stdin, files, depth):
    i, cwd = 0, seg.cwd
    while i < len(args) and args[i].text.startswith("-"):
        if args[i].text == "-C" and i + 1 < len(args):
            cwd = resolve(args[i + 1].text, cwd) if not args[i + 1].dynamic else None
            i += 2
        elif args[i].text in ("-c", "--git-dir", "--work-tree", "--namespace"):
            i += 2
        else:
            i += 1
    if i >= len(args):
        return []
    sub, rest = args[i].text, args[i + 1 :]
    texts = [w.text for w in rest]
    here = Segment(seg.text, seg.verb, seg.argv, [], None, cwd, seg.op_before, loops=seg.loops)

    def edits(words):
        return [WriteOp(p, "edit", None, "other", variable=var, target=w.text) for w in words for p, var in [_target(w, here)]]

    tree = WriteOp(cwd or "", "unknown", None, "other", variable=cwd is None, target=".")
    if sub in ("checkout", "restore"):
        if "--" in texts:
            return edits(rest[texts.index("--") + 1 :])
        if sub == "restore":
            ops, opts = _operands(rest, {"-s", "--source"})
            if _flag(opts, "", ("--staged",)) and not _flag(opts, "W", ("--worktree",)):
                return []
            return [tree] if any(w.text == "." for w in ops) else edits(ops)
        ops, _ = _operands(rest, {"-b", "-B"})
        if any(w.text == "." for w in ops):
            return [tree]
        paths = [w for w in ops if "/" in w.text or re.search(r"\.\w+$", w.text)]
        return edits(paths) if paths else ([tree] if ops else [])
    if sub == "apply":
        if any(t in ("--check", "--stat", "--numstat", "--summary") for t in texts):
            return []
        ops, opts = _operands(rest, {"-p", "--directory", "--exclude", "--include"})
        pv = (opts.get("-p") or ["1"])[-1]
        strip = int(pv) if pv.isdigit() else 1
        text = stdin
        if ops:
            p, var = _target(ops[0], here)
            text = None if var else files.get(p)
        return _patch_ops(text, cwd, strip, _flag(opts, "R", ("--reverse",)))
    if sub == "stash" and (not texts or texts[0] in ("push", "pop", "apply", "save", "drop", "-u", "--include-untracked")):
        return [] if texts and texts[0] == "drop" else [tree]
    if sub in ("reset",) and "--hard" in texts:
        return [tree]
    if sub in ("clean", "am", "merge", "rebase", "cherry-pick", "revert", "pull", "switch"):
        if sub == "clean" and ("-n" in texts or "--dry-run" in texts):
            return []
        return [tree]
    if sub == "mv" and len(rest) >= 2:
        return _cp_mv(Segment(seg.text, "mv", seg.argv, [], None, cwd, seg.op_before, loops=seg.loops), rest, stdin, files, depth)
    if sub == "rm" and "--cached" not in texts:
        return _rm(here, [w for w in rest if not w.text.startswith("-")], stdin, files, depth)
    return []


def _patch(seg, args, stdin, files, depth):
    ops, opts = _operands(args, {"-p", "-i", "--input", "-d", "--directory", "-o", "--output", "-B", "-r", "-z"})
    pval = (opts.get("-p") or ["0"])[-1]
    strip = int(pval) if pval.isdigit() else 0
    text = stdin
    src = (opts.get("-i") or opts.get("--input") or [None])[-1]
    if src:
        p, var = _target(Word(src, src), seg)
        text = None if var else files.get(p)
    if ops and not src and len(ops) >= 2:
        p, var = _target(ops[1], seg)
        text = None if var else files.get(p)
    if ops and text is None and len(ops) == 1:
        p, var = _target(ops[0], seg)
        return [WriteOp(p, "edit", None, "other", variable=var, target=ops[0].text)]
    return _patch_ops(text, seg.cwd, strip, _flag(opts, "R", ("--reverse",)))


def _patch_ops(text: str | None, cwd: str | None, strip: int, reverse: bool) -> list[WriteOp]:
    """Files a unified diff touches (edit/create/delete; bodies unknown)."""
    if text is None:
        return [WriteOp("", "unknown", None, "other")]
    out: list[WriteOp] = []
    old = None
    for line in text.splitlines():
        if line.startswith("--- "):
            old = line[4:].split("\t")[0].strip()
        elif line.startswith("+++ ") and old is not None:
            new = line[4:].split("\t")[0].strip()
            a, b = (new, old) if reverse else (old, new)
            name = b if b != "/dev/null" else a
            parts = name.split("/")
            rel = "/".join(parts[strip:]) if len(parts) > strip else parts[-1]
            if cwd is None and not rel.startswith("/"):
                out.append(WriteOp("", "edit", None, "other", variable=True, target=rel))
            else:
                path = resolve(rel, cwd)
                op = "delete" if b == "/dev/null" else ("overwrite" if a == "/dev/null" else "edit")
                out.append(WriteOp(path, op, None, "other", target=rel))
            old = None
    return out or [WriteOp("", "unknown", None, "other")]


def _dd(seg, args, stdin, files, depth):
    out = []
    for w in args:
        if w.text.startswith("of="):
            ww = Word(w.text[3:], w.raw[3:], vars=w.vars, opaque=w.opaque)
            p, var = _target(ww, seg)
            out.append(WriteOp(p, "overwrite", stdin if len(args) == 1 else None, "other", variable=var, target=ww.text))
    return out


def _download(seg, args, stdin, files, depth):
    flag = {"curl": ("-o", "--output"), "wget": ("-O", "--output-document")}[seg.verb]
    out = []
    for k, w in enumerate(args):
        val = None
        if w.text in flag and k + 1 < len(args):
            val = args[k + 1]
        elif w.text.startswith(flag[1] + "="):
            val = Word(w.text.split("=", 1)[1], w.raw)
        if val is not None and val.text != "-":
            p, var = _target(val, seg)
            out.append(WriteOp(p, "overwrite", None, "other", variable=var, target=val.text))
    return out


def _script_ops(seg, args, stdin, files, depth) -> list[WriteOp]:
    """``bash script.sh`` / ``bash <<EOF`` / ``source x``: follow the script when its text is known."""
    if depth >= MAX_DEPTH:
        return []
    ops, _ = _operands(args, {"-o", "-O", "+o", "+O"})
    code = None
    if ops:
        p, var = _target(ops[0], seg)
        code = None if var else files.get(p)
    elif stdin is not None:
        code = stdin
    if not code:
        return []
    inner, _ = split(code, seg.cwd)
    return _ops(inner, files, depth + 1)


_HANDLERS: dict[str, Callable[..., list[WriteOp]]] = {
    "tee": _tee,
    "cp": _cp_mv,
    "mv": _cp_mv,
    "install": _cp_mv,
    "rm": _rm,
    "mkdir": _mkdir,
    "touch": _touch,
    "truncate": _truncate,
    "sed": _sed,
    "perl": _perl,
    "find": _find_ops,
    "git": _git,
    "patch": _patch,
    "dd": _dd,
    "curl": _download,
    "wget": _download,
}


# ============================================================================================
# sed (the subset worth applying)
# ============================================================================================
_POSIX_CLASS = {
    "alpha": "a-zA-Z", "digit": "0-9", "alnum": "a-zA-Z0-9", "upper": "A-Z", "lower": "a-z", "space": r"\s",
    "blank": r" \t", "punct": r"!-/:-@\[-`{-~", "xdigit": "0-9A-Fa-f", "word": r"\w", "cntrl": r"\x00-\x1f", "print": r"\x20-\x7e", "graph": r"\x21-\x7e",
}  # fmt: skip


def _sed_regex(pat: str, ere: bool) -> str | None:
    """A POSIX BRE/ERE as a Python regex, or None when unsupported or prone to catastrophic backtracking."""
    out: list[str] = []
    i, n, unbounded = 0, len(pat), 0
    while i < n:
        c = pat[i]
        if c == "\\" and i + 1 < n:
            d = pat[i + 1]
            i += 2
            if d in "(){}+?|":
                if ere:
                    out.append("\\" + d)
                else:
                    out.append(d)
                    unbounded += d == "+"
            elif d.isdigit():
                return None
            elif d == "n":
                out.append(r"\n")
            elif d == "t":
                out.append(r"\t")
            elif d in "<>":
                out.append(r"\b")
            elif d in "wWsSb":
                out.append("\\" + d)
            elif d == "`":
                out.append(r"\A")
            elif d == "'":
                out.append(r"\Z")
            else:
                out.append(re.escape(d))
            continue
        if c == "[":
            k = i + 1
            neg = k < n and pat[k] == "^"
            k += neg
            body: list[str] = []
            first = True
            while k < n and not (pat[k] == "]" and not first):
                m = re.match(r"\[:(\w+):\]", pat[k:])
                if m and m.group(1) in _POSIX_CLASS:
                    body.append(_POSIX_CLASS[m.group(1)])
                    k += m.end()
                else:
                    body.append("\\" + pat[k] if pat[k] in "\\[]^" else pat[k])
                    k += 1
                first = False
            if k >= n:
                return None
            out.append("[" + ("^" if neg else "") + "".join(body) + "]")
            i = k + 1
            continue
        if not ere and c in "(){}+?|":
            out.append(re.escape(c))
        elif c == "*":
            if not out or out[-1] in ("^", "(", "|"):
                out.append(r"\*")
            else:
                out.append("*")
                unbounded += 1
        elif ere and c in "+":
            unbounded += 1
            out.append(c)
        elif ere and c == "{":
            m = re.match(r"\{(\d*)(,?)(\d*)\}", pat[i:])
            if not m:
                return None
            unbounded += bool(m.group(2)) and not m.group(3)
            out.append(m.group(0))
            i += m.end()
            continue
        elif c == "^":
            out.append("^" if (ere or not out) else r"\^")
        elif c == "$":
            out.append("$" if (ere or i == n - 1) else r"\$")
        elif c == ".":
            out.append(".")
        elif ere and c in "()?|":
            out.append(c)
        else:
            out.append(re.escape(c))
        i += 1
    rx = "".join(out)
    # re.sub tries every start position: one unbounded quantifier keeps a line quadratic at worst;
    # a ^-anchored pattern is tried at one position only, so it may have two.
    if unbounded > (2 if rx.startswith("^") else 1) or re.search(r"(?<!\\)\)[*+?{]", rx):
        return None
    try:
        re.compile(rx)
    except re.error:
        return None
    return rx


def _sed_repl(repl: str) -> list[str | int] | None:
    parts: list[str | int] = []
    buf: list[str] = []
    i = 0
    while i < len(repl):
        c = repl[i]
        if c == "\\" and i + 1 < len(repl):
            d = repl[i + 1]
            i += 2
            if d.isdigit():
                parts.append("".join(buf))
                buf = []
                parts.append(int(d))
            elif d in "ULulE":
                return None
            else:
                buf.append({"n": "\n", "t": "\t"}.get(d, d))
            continue
        if c == "&":
            parts.append("".join(buf))
            buf = []
            parts.append(0)
        else:
            buf.append(c)
        i += 1
    parts.append("".join(buf))
    return parts


def _sed_until(s: str, i: int, delim: str) -> tuple[str, int] | None:
    out: list[str] = []
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            if s[i + 1] == delim:
                out.append(delim)
            else:
                out.append(s[i : i + 2])
            i += 2
            continue
        if c == delim:
            return "".join(out), i + 1
        out.append(c)
        i += 1
    return None


def _sed_parse(script: str, ere: bool) -> list[dict] | None:
    cmds: list[dict] = []
    i, n = 0, len(script)
    while i < n:
        while i < n and script[i] in " \t\n;":
            i += 1
        if i >= n:
            break
        addr: tuple | None = None
        m = re.match(r"(\d+|\$)(?:,(\d+|\$))?", script[i:])
        if m:
            a, b = m.group(1), m.group(2)
            addr = ("lines", a, b)
            i += m.end()
        elif script[i] == "/":
            r = _sed_until(script, i + 1, "/")
            if r is None:
                return None
            pat, i = r
            if i < n and script[i] == ",":
                return None
            flags = 0
            if i < n and script[i] == "I":
                flags, i = re.I, i + 1
            rx = _sed_regex(pat, ere)
            if rx is None:
                return None
            addr = ("re", re.compile(rx, flags), None)
        while i < n and script[i] in " \t":
            i += 1
        if i >= n:
            return None
        c = script[i]
        if c == "s" and i + 1 < n:
            delim = script[i + 1]
            r1 = _sed_until(script, i + 2, delim)
            if r1 is None:
                return None
            pat, j = r1
            r2 = _sed_until(script, j, delim)
            if r2 is None:
                return None
            repl, j = r2
            fm = re.match(r"[gIi0-9]*", script[j:])
            flags_s = fm.group(0) if fm else ""
            j += len(flags_s)
            if j < n and script[j] not in " \t\n;}":
                return None
            rx = _sed_regex(pat, ere) if pat else None
            parts = _sed_repl(repl)
            if rx is None or parts is None:
                return None
            nth = int(re.sub(r"\D", "", flags_s) or 0)
            cmds.append({"kind": "s", "addr": addr, "rx": re.compile(rx, re.I if ("I" in flags_s or "i" in flags_s) else 0), "parts": parts, "g": "g" in flags_s, "nth": nth})
            i = j
        elif c == "d":
            cmds.append({"kind": "d", "addr": addr})
            i += 1
        elif c in "aic":
            j = script.find("\n", i)
            text = script[i + 1 : n if j < 0 else j]
            text = text[1:] if text.startswith("\\") else text
            text = text.lstrip(" \t")
            if text.endswith("\\"):
                return None
            cmds.append({"kind": c, "addr": addr, "text": _c_escapes(text)[0] if "\\" in text else text})
            i = n if j < 0 else j
        else:
            return None
    return cmds


def _sed_program(ops: list[Word], opts: Mapping[str, list[str]]) -> tuple[Callable[[str], str | None], list[Word]] | None:
    """(function applying the sed script to a text, the file operands), or None when the script is beyond the subset."""
    if any(k in opts for k in ("-f", "--file", "-z", "--null-data", "-s")) or _flag(opts, "nz", ("--quiet", "--silent")):
        return None
    ere = _flag(opts, "Er", ("--regexp-extended",))
    scripts = list(opts.get("-e", [])) + list(opts.get("--expression", []))
    rest = ops
    if not scripts:
        if not ops or ops[0].dynamic:
            return None
        scripts, rest = [ops[0].text], ops[1:]
    cmds = _sed_parse("\n".join(scripts), ere)
    if not cmds:
        return None

    def run(text: str) -> str | None:
        if text is None or len(text) > MAX_SOURCE:
            return None
        lines = text.split("\n")
        trailing = text.endswith("\n")
        if trailing:
            lines.pop()
        if any(len(line) > MAX_LINE for line in lines):
            return None
        out: list[str] = []
        last = len(lines)
        deadline = time.monotonic() + SED_BUDGET
        for idx, line in enumerate(lines, 1):
            if time.monotonic() > deadline:
                return None
            before: list[str] = []
            after: list[str] = []
            deleted = False
            for c in cmds:
                if not _sed_match(c["addr"], idx, last, line):
                    continue
                if c["kind"] == "s":
                    line = _sed_sub(c, line)
                elif c["kind"] == "d":
                    deleted = True
                    break
                elif c["kind"] == "a":
                    after.append(c["text"])
                elif c["kind"] == "i":
                    before.append(c["text"])
                elif c["kind"] == "c":
                    before.append(c["text"])
                    deleted = True
                    break
            out.extend(before)
            if not deleted:
                out.append(line)
            out.extend(after)
        return "\n".join(out) + ("\n" if out and trailing else "")

    return run, rest


def _sed_match(addr, idx: int, last: int, line: str) -> bool:
    if addr is None:
        return True
    kind, a, b = addr
    if kind == "re":
        return a.search(line) is not None
    lo = last if a == "$" else int(a)
    if b is None:
        return idx == lo
    hi = last if b == "$" else int(b)
    return lo <= idx <= max(lo, hi)


def _sed_sub(c: dict, line: str) -> str:
    count = [0]

    def repl(m: re.Match) -> str:
        count[0] += 1
        if c["nth"] and count[0] < c["nth"]:
            return m.group(0)
        if c["nth"] and not c["g"] and count[0] > c["nth"]:
            return m.group(0)
        if not c["nth"] and not c["g"] and count[0] > 1:
            return m.group(0)
        return "".join(p if isinstance(p, str) else (m.group(p) or "") if p <= (m.re.groups or 0) else "" for p in c["parts"])

    return c["rx"].sub(repl, line)


# ============================================================================================
# Python sources (read with ast, never run)
# ============================================================================================
def _python_code(seg: Segment, stdin: str | None, files) -> tuple[str | None, list[str], bool]:
    """(source a python segment runs, its sys.argv, source holds unresolved shell expansions).

    The source is ``-c CODE``, a heredoc / pipe on stdin, or a known script. Source with a shell
    expansion we could not resolve is still returned, the expansion left as ``${NAME}`` / ``$(...)``;
    :func:`_unresolved` then marks what it touches as unknown.
    """
    args = seg.cmd_words[1:]
    i = 0
    while i < len(args):
        t = args[i].text
        if t == "-c":
            if i + 1 < len(args):
                return args[i + 1].text, ["-c"] + [w.text for w in args[i + 2 :]], args[i + 1].dynamic
            return None, [], False
        if t in ("-m",):
            return None, [], False
        if t in ("-W", "-X", "-Q"):
            i += 2
            continue
        if t.startswith("-") and t != "-":
            i += 1
            continue
        break
    rest = args[i:]
    if not rest or rest[0].text in ("-", "/dev/stdin"):
        if stdin is None and seg.heredoc is not None and not seg.heredoc_quoted:
            # an unquoted heredoc we could not expand: as typed, its expansions marked
            return re.sub(r"\$([A-Za-z_]\w*)", r"${\1}", seg.heredoc), ["-"] + [w.text for w in rest[1:]], True
        return stdin, ["-"] + [w.text for w in rest[1:]], False
    p, var = _target(rest[0], seg)
    if var:
        return None, [], False
    getter = files.get if hasattr(files, "get") else (lambda _p: None)
    code = getter(p)
    return (code if isinstance(code, str) else None), [p] + [w.text for w in rest[1:]], False


class _P:
    """A pathlib-like value."""

    __slots__ = ("p",)

    def __init__(self, p: str):
        self.p = p


class _H:
    """An open file handle."""

    __slots__ = ("path", "mode", "parts", "certain")

    def __init__(self, path: str | None, mode: str, certain: bool):
        self.path, self.mode, self.parts, self.certain = path, mode, [], certain


class _Mod:
    __slots__ = ("name",)

    def __init__(self, name: str):
        self.name = name


class _Def:
    __slots__ = ("node",)

    def __init__(self, node):
        self.node = node


_PATHLIKE = {"pathlib.Path", "pathlib.PurePath", "pathlib.PosixPath", "pathlib.PurePosixPath", "Path", "PurePath", "PosixPath"}


class _Py:
    """Abstract interpretation of a python script, just far enough to see what it reads and writes."""

    def __init__(self, cwd: str | None, argv: list[str], files, depth: int):
        self.cwd = cwd
        self.env: dict[str, object] = {"sys.argv": list(argv)}
        self.files = files
        self.depth = depth
        self.ops: list[WriteOp] = []
        self.reads: list[str] = []
        self.prints = False
        self.uncertain = 0
        self.temps: list[_H] = []
        self.active: set[int] = set()
        self.budget = 200  # function bodies entered
        self.out: list[str | None] = []  # what the script prints, in order (None: unknown)
        self.failed = False

    def stdout(self) -> str | None:
        if self.failed or any(x is None for x in self.out):
            return None
        return "".join(x for x in self.out if x is not None)

    # -- values ----------------------------------------------------------------------------
    def path_of(self, v) -> str | None:
        if isinstance(v, _P):
            v = v.p
        if not isinstance(v, str) or not v:
            return None
        if self.cwd is None and not v.startswith(("/", "~")):
            return None
        return resolve(v, self.cwd)

    def qual(self, node) -> str | None:
        if isinstance(node, ast.Name):
            v = self.env.get(node.id)
            if isinstance(v, _Mod):
                return v.name
            return node.id
        if isinstance(node, ast.Attribute):
            base = self.qual(node.value)
            return f"{base}.{node.attr}" if base else None
        return None

    def expr(self, node):
        if isinstance(node, ast.Constant):
            return node.value if isinstance(node.value, (str, int)) else None
        if isinstance(node, ast.JoinedStr):
            out = []
            for v in node.values:
                if isinstance(v, ast.Constant) and isinstance(v.value, str):
                    out.append(v.value)
                elif isinstance(v, ast.FormattedValue) and v.format_spec is None and v.conversion in (-1, 115):
                    x = self.expr(v.value)
                    if isinstance(x, _P):
                        x = x.p
                    if not isinstance(x, (str, int)):
                        return None
                    out.append(str(x))
                else:
                    return None
            return "".join(out)
        if isinstance(node, ast.Name):
            return self.env.get(node.id)
        if isinstance(node, ast.BinOp):
            a, b = self.expr(node.left), self.expr(node.right)
            if isinstance(node.op, ast.Add) and isinstance(a, str) and isinstance(b, str):
                return a + b
            if isinstance(node.op, ast.Div) and isinstance(a, (_P, str)) and isinstance(b, (_P, str)) and isinstance(a, _P):
                return _P(posixpath.join(a.p, b.p if isinstance(b, _P) else b))
            return None
        if isinstance(node, (ast.List, ast.Tuple)):
            return [self.expr(e) for e in node.elts]
        if isinstance(node, ast.Subscript):
            base = self.expr(node.value) if not (isinstance(node.value, ast.Attribute) and self.qual(node.value) == "sys.argv") else self.env["sys.argv"]
            idx = self.expr(node.slice)
            if isinstance(base, list) and isinstance(idx, int) and -len(base) <= idx < len(base):
                return base[idx]
            return None
        if isinstance(node, ast.Attribute):
            q = self.qual(node)
            if q == "sys.argv":
                return self.env["sys.argv"]
            base = self.expr(node.value)
            if isinstance(base, _P):
                if node.attr == "parent":
                    return _P(posixpath.dirname(base.p))
                if node.attr == "name":
                    return posixpath.basename(base.p)
            return None
        if isinstance(node, ast.Call):
            return self.call(node)
        return None

    # -- calls -----------------------------------------------------------------------------
    def call(self, node: ast.Call):
        args = [self.expr(a) for a in node.args]
        kw = {k.arg: self.expr(k.value) for k in node.keywords if k.arg}
        q = self.qual(node.func) or ""
        if isinstance(node.func, ast.Attribute):
            recv = self.expr(node.func.value)
            m = node.func.attr
            r = self.method(recv, m, args, kw, node)
            if r is not _MISSING:
                return r
        if isinstance(node.func, ast.Name) and isinstance(self.env.get(node.func.id), _Def):
            return self.invoke(self.env[node.func.id], args, kw)
        if q in _PATHLIKE or q.endswith(".Path"):
            parts = [a.p if isinstance(a, _P) else a for a in args]
            if parts and all(isinstance(p, str) for p in parts):
                return _P(posixpath.join(*parts))
            return _P(self.cwd or ".") if not parts else None
        if q in ("os.path.join", "posixpath.join", "join") and args and all(isinstance(a, (str, _P)) for a in args):
            return posixpath.join(*[a.p if isinstance(a, _P) else a for a in args])
        if q in ("os.path.expanduser", "expanduser") and args and isinstance(args[0], str):
            return resolve(args[0], self.cwd) if args[0].startswith("~") else args[0]
        if q in ("os.path.abspath", "os.path.realpath", "os.path.normpath") and args and isinstance(args[0], (str, _P)):
            p = self.path_of(args[0])
            return p
        if q in ("os.getcwd",):
            return self.cwd
        if q in ("str",) and args and isinstance(args[0], (str, _P, int)):
            a = args[0]
            return a.p if isinstance(a, _P) else str(a)
        if q in ("textwrap.dedent", "dedent") and args and isinstance(args[0], str):
            return textwrap.dedent(args[0])
        if q == "open" or q == "io.open" or q == "codecs.open":
            return self.open(args[0] if args else kw.get("file"), args[1] if len(args) > 1 else kw.get("mode", "r"))
        if q == "print":
            self.prints = True
            f = kw.get("file")
            if f is None and "file" not in kw:
                sep, end = kw.get("sep", " "), kw.get("end", "\n")
                ok = all(isinstance(a, str) for a in args) and not any(isinstance(a, ast.Starred) for a in node.args)
                self.out.append(sep.join(args) + end if ok and isinstance(sep, str) and isinstance(end, str) and not self.uncertain else None)
            elif isinstance(f, _H):
                sep = kw.get("sep", " ")
                end = kw.get("end", "\n")
                if all(isinstance(a, str) for a in args) and isinstance(sep, str) and isinstance(end, str) and not self.uncertain:
                    f.parts.append(sep.join(args) + end)
                else:
                    f.parts.append(None)
            return None
        if q in ("sys.stdout.write",):
            self.prints = True
            self.out.append(args[0] if args and isinstance(args[0], str) and not self.uncertain else None)
            return None
        if q.split(".")[-1].startswith(("print", "pprint", "show", "display")) or q in ("help", "exec", "eval", "runpy.run_path", "runpy.run_module"):
            self.out.append(None)
        if q in ("json.dump", "yaml.dump", "yaml.safe_dump", "pickle.dump", "toml.dump") and len(args) > 1 and isinstance(args[1], _H):
            args[1].parts.append(None)
            return None
        if q in ("shutil.copy", "shutil.copy2", "shutil.copyfile", "shutil.copytree", "shutil.move", "os.rename", "os.replace", "os.renames"):
            if len(args) >= 2:
                src, dst = self.path_of(args[0]), self.path_of(args[1])
                is_move = q in ("shutil.move", "os.rename", "os.replace", "os.renames")
                into = None if q in ("shutil.copy", "shutil.copy2", "shutil.move") else False
                self.emit(WriteOp(dst or "", "move" if is_move else "copy", None, "python", src=src, variable=dst is None, dir_target=into, recursive=q == "shutil.copytree" or is_move))
            return None
        if q in ("os.remove", "os.unlink", "shutil.rmtree", "os.rmdir"):
            if args:
                p = self.path_of(args[0])
                self.emit(WriteOp(p or "", "delete", None, "python", variable=p is None))
            return None
        if q in ("os.makedirs", "os.mkdir"):
            if args:
                p = self.path_of(args[0])
                if p:
                    self.emit(WriteOp(p, "mkdir", None, "python"))
            return None
        if q == "os.chdir" and args:
            self.cwd = self.path_of(args[0])
            return None
        if q in ("os.system", "subprocess.run", "subprocess.call", "subprocess.check_call", "subprocess.check_output", "subprocess.Popen", "subprocess.getoutput"):
            cmd = args[0] if args else kw.get("args")
            if isinstance(cmd, list) and all(isinstance(c, str) for c in cmd):
                cmd = shlex.join(cmd)
            if not any(k in kw for k in ("capture_output", "stdout")) and q != "subprocess.check_output" and q != "subprocess.getoutput":
                self.out.append(None)
            if isinstance(cmd, str) and self.depth < MAX_DEPTH:
                inner, _ = split(cmd, self.cwd)
                for op in _ops(inner, self.files if isinstance(self.files, _Files) else _Files(None), self.depth + 1):
                    self.emit(op)
            return None
        return None

    def method(self, recv, m: str, args: list, kw: dict, node):
        if isinstance(recv, str):
            if m == "replace" and len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], str):
                cnt = args[2] if len(args) > 2 and isinstance(args[2], int) else -1
                return recv.replace(args[0], args[1], cnt)
            if m in ("strip", "lstrip", "rstrip") and (not args or isinstance(args[0], str)):
                return getattr(recv, m)(*args)
            if m in ("upper", "lower") and not args:
                return getattr(recv, m)()
            if m == "join" and args and isinstance(args[0], list) and all(isinstance(x, str) for x in args[0]):
                return recv.join(args[0])
            if m == "format":
                return None
            return _MISSING if m not in ("replace", "join") else None
        if isinstance(recv, _H):
            if m == "write":
                recv.parts.append(args[0] if args and isinstance(args[0], str) and not self.uncertain else None)
                return None
            if m == "writelines":
                lines = args[0] if args else None
                ok = isinstance(lines, list) and all(isinstance(x, str) for x in lines) and not self.uncertain
                recv.parts.append("".join(lines) if ok else None)
                return None
            if m in ("read", "readlines", "readline"):
                if recv.path:
                    self.reads.append(recv.path)
                c = self.files.get(recv.path) if (recv.path and hasattr(self.files, "get")) else None
                return c if (m == "read" and isinstance(c, str) and not args) else None
            if m == "close":
                self.close(recv)
                return None
            return None
        if isinstance(recv, _P):
            p = self.path_of(recv)
            if m in ("write_text", "write_bytes"):
                data = args[0] if (m == "write_text" and args and isinstance(args[0], str)) else None
                self.write(p, "w", [data])
                return None
            if m in ("read_text", "read_bytes"):
                if p:
                    self.reads.append(p)
                c = self.files.get(p) if (p and hasattr(self.files, "get")) else None
                return c if (m == "read_text" and isinstance(c, str)) else None
            if m == "open":
                return self.open(recv, args[0] if args else kw.get("mode", "r"))
            if m in ("unlink", "rmdir"):
                self.emit(WriteOp(p or "", "delete", None, "python", variable=p is None))
                return None
            if m == "mkdir":
                if p:
                    self.emit(WriteOp(p, "mkdir", None, "python"))
                return None
            if m in ("rename", "replace") and args:
                dst = self.path_of(args[0])
                self.emit(WriteOp(dst or "", "move", None, "python", src=p, variable=dst is None, dir_target=False, recursive=True))
                return _P(dst) if dst else None
            if m == "touch":
                if p:
                    self.emit(WriteOp(p, "append", "", "python"))
                return None
            if m in ("joinpath",) and all(isinstance(a, str) for a in args):
                return _P(posixpath.join(recv.p, *args))
            if m in ("resolve", "absolute", "expanduser"):
                return _P(p) if p else None
            return None
        return _MISSING

    def open(self, target, mode):
        p = self.path_of(target)
        mode = mode if isinstance(mode, str) else "r"  # an unknown mode is not taken for a write
        h = _H(p, mode, not self.uncertain)
        if not any(ch in mode for ch in "wax+"):
            if p:
                self.reads.append(p)
            return h
        if p is None:
            self.emit(WriteOp("", "append" if "a" in mode else "overwrite", None, "python", variable=True))
            return h
        self.temps.append(h)
        return h

    def write(self, p: str | None, mode: str, parts: list) -> None:
        h = _H(p, mode, not self.uncertain)
        h.parts = list(parts)
        self.close(h)

    def close(self, h: _H) -> None:
        if h in self.temps:
            self.temps.remove(h)
        if not any(ch in h.mode for ch in "wax+"):
            return
        if h.path is None:
            self.emit(WriteOp("", "overwrite", None, "python", variable=True))
            return
        body = "".join(h.parts) if (h.certain and all(isinstance(x, str) for x in h.parts)) else None
        if "a" in h.mode:
            self.emit(WriteOp(h.path, "append", body, "python", target=h.path))
        elif h.path in self.reads or "+" in h.mode:
            self.emit(WriteOp(h.path, "edit", body, "python", target=h.path))
        else:
            self.emit(WriteOp(h.path, "overwrite", body, "python", target=h.path))

    def emit(self, op: WriteOp) -> None:
        if self.uncertain and op.op in ("overwrite", "append", "edit"):
            op.body = None
        self.ops.append(op)
        if isinstance(self.files, _Files):
            self.files.apply(op)

    def invoke(self, d: _Def, args: list, kw: dict):
        """Run a function body with its parameters bound to the call's values (no recursion, bounded)."""
        if id(d.node) in self.active or self.budget <= 0:
            return None
        self.budget -= 1
        self.active.add(id(d.node))
        saved = dict(self.env)
        params = [a.arg for a in d.node.args.posonlyargs + d.node.args.args]
        for k, name in enumerate(params):
            self.env[name] = args[k] if k < len(args) else kw.get(name)
        for a in d.node.args.kwonlyargs:
            self.env[a.arg] = kw.get(a.arg)
        try:
            self.run(d.node.body)
        finally:
            self.env = saved
            self.active.discard(id(d.node))
        return None

    # -- statements ------------------------------------------------------------------------
    def run(self, body) -> None:
        for st in body:
            self.stmt(st)
            for h in list(self.temps):
                if not any(h is v for v in self.env.values()):
                    self.close(h)

    def bind(self, target, value) -> None:
        if isinstance(target, ast.Name):
            self.env[target.id] = value
        elif isinstance(target, (ast.Tuple, ast.List)):
            for t in target.elts:
                self.bind(t, None)

    def stmt(self, st) -> None:
        if isinstance(st, ast.Import):
            for a in st.names:
                self.env[(a.asname or a.name).split(".")[0]] = _Mod(a.name if a.asname else a.name.split(".")[0])
        elif isinstance(st, ast.ImportFrom):
            for a in st.names:
                self.env[a.asname or a.name] = _Mod(f"{st.module}.{a.name}" if st.module else a.name)
        elif isinstance(st, ast.Assign):
            v = self.expr(st.value)
            for t in st.targets:
                self.bind(t, v)
        elif isinstance(st, ast.AnnAssign) and st.value is not None:
            self.bind(st.target, self.expr(st.value))
        elif isinstance(st, ast.AugAssign):
            cur = self.expr(st.target) if isinstance(st.target, ast.Name) else None
            add = self.expr(st.value)
            self.bind(st.target, cur + add if isinstance(st.op, ast.Add) and isinstance(cur, str) and isinstance(add, str) else None)
        elif isinstance(st, ast.Expr):
            self.expr(st.value)
        elif isinstance(st, (ast.With, ast.AsyncWith)):
            opened = []
            for item in st.items:
                v = self.expr(item.context_expr)
                if isinstance(v, _H):
                    opened.append(v)
                if item.optional_vars is not None:
                    self.bind(item.optional_vars, v)
            self.run(st.body)
            for h in opened:
                if h in self.temps:
                    self.close(h)
        elif isinstance(st, ast.If):
            main = _is_main(st.test)
            if not main:
                self.uncertain += 1
            self.run(st.body)
            self.run(st.orelse)
            if not main:
                self.uncertain -= 1
        elif isinstance(st, (ast.For, ast.AsyncFor, ast.While)):
            self.uncertain += 1
            if isinstance(st, (ast.For, ast.AsyncFor)):
                self.bind(st.target, None)
            self.run(st.body)
            self.run(st.orelse)
            self.uncertain -= 1
        elif isinstance(st, ast.Try) or type(st).__name__ == "TryStar":
            self.run(st.body)
            self.uncertain += 1
            for h in st.handlers:
                self.run(h.body)
            self.run(st.orelse)
            self.uncertain -= 1
            self.run(st.finalbody)
        elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.env[st.name] = _Def(st)


def _is_main(test) -> bool:
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    )


def _py_run(code: str, cwd: str | None, argv: list[str], files, depth: int) -> _Py | None:
    if not code or len(code) > MAX_SOURCE:
        return None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # agent code is full of invalid escapes; not our business
            tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError, MemoryError, OverflowError):
        return None
    py = _Py(cwd, argv, files, depth)
    try:
        py.run(tree.body)
        for h in list(py.temps):
            py.close(h)
    except (RecursionError, MemoryError, ValueError, TypeError, AttributeError) as e:
        py.failed = True
        logger.debug("python analysis stopped: %r", e)
    return py


_SHELL_LEFT = re.compile(r"\$\{[A-Za-z_]\w*\}|\$\(|`")


def _unresolved(ops: list[WriteOp], dynamic: bool) -> list[WriteOp]:
    """Ops of python source that still holds shell expansions: a path or body carrying one is unknown."""
    if not dynamic:
        return ops
    for op in ops:
        if _SHELL_LEFT.search(op.path):
            op.path, op.variable = "", True
        if op.body is not None and _SHELL_LEFT.search(op.body):
            op.body = None
        if op.src and _SHELL_LEFT.search(op.src):
            op.src = None
    return ops


def _py_ops(code: str, cwd: str | None, argv: list[str], files, depth: int, dynamic: bool = False) -> list[WriteOp]:
    py = _py_run(code, cwd, argv, files, depth)
    return _unresolved(py.ops, dynamic) if py is not None else []


def _py_reads(code: str, cwd: str | None) -> list[str]:
    py = _py_run(code, cwd, [], _Files(None), MAX_DEPTH)
    if py is None or not py.prints:
        return []
    return list(dict.fromkeys(py.reads))


# ============================================================================================
# Failure markers
# ============================================================================================
_FAIL = re.compile(
    r"No such file or directory|Permission denied|cannot create|Read-only file system|Is a directory|Not a directory|Directory nonexistent"
    r"|cannot move|cannot stat|cannot overwrite|command not found|FileNotFoundError|PermissionError|IsADirectoryError|NotADirectoryError"
    r"|No space left on device|can't read",
    re.I,
)
_READ_ONLY_TOOL = re.compile(r"^\s*(?:ls|cat|head|tail|stat|grep|egrep|rg|wc|du|find|file|diff|realpath|readlink|test|less|more|nl|sort|awk|git|which|type)\s*:", re.I)


def failure_markers(observation: str, paths: Iterable[str] = (), verb: str | None = None) -> bool:
    """True when the observation says a write failed.

    Without ``paths``: any failure marker at all (``No such file or directory``, ``Permission denied``,
    ``cannot create``, ``Read-only file system``, ``Is a directory``, ``command not found`` ...).
    With ``paths`` (the target as written and/or resolved): only a marker on a line naming one of
    them -- and not printed by a read-only tool (``ls: cannot access P`` before ``cat > P``) -- or
    ``command not found`` for ``verb``.
    """
    if not observation:
        return False
    needles = [p for p in paths if p]
    for line in _strip_ansi(observation).splitlines():
        if not _FAIL.search(line):
            continue
        if not needles and verb is None:
            return True
        if _READ_ONLY_TOOL.match(line):
            continue
        if any(n in line for n in needles):
            return True
        if verb and "command not found" in line and re.search(rf"(?<![\w.-]){re.escape(verb)}(?![\w.-])", line):
            return True
    return False


def python_failed(observation: str) -> bool:
    """The interpreter refused the script before running it (syntax / indentation error)."""
    return bool(re.search(r"^\s*(?:SyntaxError|IndentationError|TabError):", _strip_ansi(observation or ""), re.M))
