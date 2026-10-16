"""The generator's stages wired together, each leaving its output in ``<out>/gen-work/``.

Every subcommand runs the stages it needs from the start: the rule stages are cheap and must see
the current files, and the model stages are served by the cache when nothing changed. The work
files are for review and debugging (what G2 compiled, what G6 rejected and why); the committed
outputs are only ``rubric.yaml``, ``rubric.md``, ``rubric.lock``, ``eval.py`` and the LLM cache.
"""

from __future__ import annotations

import json
import logging
from functools import cached_property
from pathlib import Path

from . import compile as C
from . import critic as K
from . import extract as X
from . import ground as G
from . import items as I
from . import manifest as M
from . import parse as P
from . import selftest
from . import templates as T
from .config import GeneratorConfig
from .llm import LLM
from .vocab import kinds as kind_table

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, cfg: GeneratorConfig, llm: LLM, out_dir: Path, spec=None, pkg_dir: Path | None = None, say=None):
        self.cfg = cfg
        self.llm = llm
        self.out = Path(out_dir)
        self.work = self.out / "gen-work"
        self._spec = spec
        self._pkg = pkg_dir
        self.say = say or (lambda msg: logger.info("%s", msg))

    # -- helpers -------------------------------------------------------------------------------
    def _write(self, name: str, data) -> None:
        self.work.mkdir(parents=True, exist_ok=True)
        (self.work / name).write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str) + "\n")

    @cached_property
    def spec_and_pkg(self):
        if self._spec is not None:
            return self._spec, Path(self._pkg or Path(self._spec.docs_dir).parent)
        return M.load_spec(self.cfg)

    # -- stages --------------------------------------------------------------------------------
    @cached_property
    def manifest(self) -> M.Manifest:
        spec, pkg = self.spec_and_pkg
        m = M.build(spec, self.cfg, pkg)
        self._write("manifest.json", m.to_json())
        self.say(f"G0 manifest: {len(m.entries)} files ({', '.join(f'{r}={n}' for r, n in sorted(_count(e.role for e in m.entries).items()))})")
        return m

    @cached_property
    def parsed(self) -> dict[str, P.Parsed]:
        pm = P.parse_manifest(self.manifest, bool(self.cfg.parse.get("template_comments")), self.cfg.parse.get("example_markers"))
        self._write("parse.json", {k: v.to_json() for k, v in pm.items()})
        n = sum(len(p.candidates) for p in pm.values())
        self.say(f"G1 parse: {n} modal candidates, {sum(len(p.sp_generic) for p in pm.values())} generic system-prompt sentences")
        return pm

    @cached_property
    def kinds(self):
        table, origin = kind_table(self.cfg.workflow)
        self.say(f"kinds: {len(table)} from the {origin} table")
        return table, origin

    @cached_property
    def stage_model(self) -> dict:
        model, log = X.stage_model(self.cfg, self.manifest, self.llm)
        self._write("stages.json", {"model": model, "log": log})
        self.say(f"G3 stage model ({model['origin']}): {len(model['stages'])} stages, {len(model['artifacts'])} artifacts")
        return model

    @cached_property
    def templates(self) -> T.TemplateResult:
        r = T.compile_all(self.cfg, self.manifest, self.stage_model)
        self._write("templates.json", {"cands": I.dump(r.cands), "may_items": r.may_items, "log": r.log})
        self.say(f"G2 templates: {len(r.cands)} items from {len(self.cfg.templates)} skeletons" + (f" ({len(r.log)} notes)" if r.log else ""))
        return r

    @cached_property
    def statements(self) -> list[X.Statement]:
        if not self.llm.enabled:
            self.say("G4 statements: skipped (no LLM)")
            return []
        rows, log = X.statements(self.cfg, self.manifest, self.parsed, self.stage_model, self.llm)
        self.work.mkdir(parents=True, exist_ok=True)
        X.write_jsonl(self.work / "statements.jsonl", rows)
        self._write("statements.log.json", log)
        self.say(f"G4 statements: {len(rows)} ({len(log)} dropped/errors)")
        return rows

    @cached_property
    def mapped(self) -> X.MapResult:
        if not self.llm.enabled:
            return X.MapResult()
        r = X.map_items(self.statements, self.cfg, self.manifest, self.stage_model, self.kinds[0], self.llm, self.templates.cands)
        self._write("mapped.json", {"cands": I.dump(r.cands), "unitemized": r.unitemized, "log": r.log})
        self.say(f"G5 mapping: {len(r.cands)} candidates, {len(r.unitemized)} unitemized statements")
        return r

    @cached_property
    def grounded(self) -> G.GroundResult:
        cands = [*self.templates.cands, *C.stage_cands(self.stage_model, self.cfg, self.manifest), *C.manual_cands(self.cfg, self.manifest), *self.mapped.cands]
        r = G.ground(cands, self.cfg, self.manifest, self.parsed, self.stage_model, self.kinds[0])
        self._write("ground.json", {"accepted": I.dump(r.accepted), "rejected": r.rejected, "may_items": r.may_items, "implicit_items": r.implicit_items})
        self.say(f"G6 ground: {len(r.accepted)} accepted, {len(r.rejected)} rejected")
        return r

    @cached_property
    def critic(self) -> K.CriticResult:
        if not self.llm.enabled:
            self.say("G7 critic: skipped (no LLM)")
            return K.CriticResult()
        handled = {(m.get("doc"), n) for m in self.grounded.may_items for n in range(m["lines"][0], m["lines"][1] + 1)}
        handled |= {(u["doc"], n) for u in self.mapped.unitemized for n in range(u["lines"][0], u["lines"][1] + 1)}
        r = K.run(self.grounded.accepted, self.statements, self.cfg, self.manifest, self.parsed, self.stage_model, self.kinds[0], self.llm, self.templates.cands, handled)
        self._write("critic.json", {"added": I.dump(r.added), "rejected": r.rejected, "conflicts": r.conflicts, "rounds": r.rounds, "log": r.log, "statements": [s.to_json() for s in r.statements]})
        self.say(f"G7 critic: {r.rounds} rounds, +{len(r.added)} items, {len(r.rejected)} rejected, {len(r.conflicts)} conflicts")
        return r

    # -- outputs -------------------------------------------------------------------------------
    def inputs(self) -> C.Inputs:
        dropped = {r["id"] for r in self.critic.rejected}
        accepted = [c for c in [*self.grounded.accepted, *self.critic.added] if c.id not in dropped]
        sp = [{"doc": sid, "lines": [c.line_start, c.line_end], "modality": c.modality, "text": c.text} for sid, p in self.parsed.items() for c in p.sp_generic]
        table, origin = self.kinds
        cache = self.llm.cache_dir
        try:
            cache_rel = str(cache.resolve().relative_to(self.out.resolve().parent))
        except ValueError:
            cache_rel = str(cache)
        return C.Inputs(
            cfg=self.cfg,
            manifest=self.manifest,
            model=self.stage_model,
            accepted=accepted,
            kinds=table,
            kinds_origin=origin,
            rejected=[*self.grounded.rejected, *self.critic.rejected],
            conflicts=list(self.critic.conflicts),
            may_items=[*self.templates.may_items, *self.grounded.may_items, *self.critic.may_items],
            implicit_items=[*self.grounded.implicit_items, *self.critic.implicit_items],
            unitemized=list(self.mapped.unitemized),
            sp_generic=sp,
            llm=self.llm.describe() if self.llm.enabled else {"backend": "none"},
            cache_dir=cache_rel if self.llm.enabled else "",
        )

    def build(self, force_eval: bool = False, run_selftest: bool = False) -> dict:
        inp = self.inputs()
        rub, report = C.compile_rubric(inp)
        if run_selftest:
            inp.selftest = selftest.run(rub, self.cfg, self.manifest)
            rub.generated["selftest"] = inp.selftest
            res = inp.selftest.get("results") or []
            n = {k: sum(1 for r in res if r.get("status") == k) for k in ("ok", "fail", "n/a", "error")}
            self.say(f"G9 selftest: {inp.selftest.get('status')}, golden {inp.selftest.get('golden')}, {n['ok']} ok / {n['fail']} fail / {n['n/a']} n/a / {n['error']} error")
            for f in inp.selftest.get("failures") or []:
                self.say(f"  FAIL {f}")
        paths = C.write_outputs(rub, self.out, inp, report, force_eval=force_eval)
        report["llm"] = {"calls": self.llm.calls, "cache_hits": self.llm.hits, "cost_usd": round(self.llm.cost, 4)}
        self._write("report.json", report)
        self.say(f"G8 compile: {report['n_items']} items {report['by_requirement']} -> {paths['rubric']}")
        return {"paths": paths, "report": report, "selftest": inp.selftest}

    def check(self) -> list[str]:
        return C.check(self.out / "rubric.yaml", self.manifest)


def _count(xs) -> dict:
    out: dict = {}
    for x in xs:
        out[x] = out.get(x, 0) + 1
    return out
