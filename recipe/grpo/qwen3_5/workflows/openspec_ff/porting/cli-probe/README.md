# CLI probes (2026-10-13)

Bundle (node v22.23.3 + `@fission-ai/openspec@1.14.1`, 138 MB) built in `node:22-bookworm-slim`:

    docker run --rm -v $OUT:/out node:22-bookworm-slim sh -c \
      'mkdir -p /out/agent/node/bin && cp /usr/local/bin/node /out/agent/node/bin/ &&
       npm install -g --prefix /out/agent/node @fission-ai/openspec@1.14.1'

Each probe runs offline in a SWE-Gym task image with the bundle mounted at `/opt/opsx`:

    docker run --rm --network none -v $OUT/agent:/opt/opsx:ro -v $PWD/<probe>.sh:/p.sh:ro \
      --entrypoint bash xingyaoww/sweb.eval.x86_64.getmoto_s_moto-7365:latest /p.sh

01: root resolution and `new change` (note: 01 pre-creates the tree by hand; an empty `/openspec/` is not a
root — 03 uses `openspec init --tools none` at `/`, which is the intended setup). 02: validate, apply state,
`archive --yes`. 03: `init`, `schema fork`, fork selected through `config.yaml`, `new change` re-run,
`store list`.
04: `checks/repro.py` inside the change dir; `validate --strict` and `archive --yes` pass, `checks/` moves with the change into `changes/archive/<date>-issue/`.
