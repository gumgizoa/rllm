# openspec_ff (porting/03-decisions.md D-1, D-2, G10-5): node v22.23.3 and @fission-ai/openspec 1.14.1
# under /opt/rllm/agent/node, appended to the openhands-sdk bake recipe's final stage (debian:bullseye-slim).
# Neither the task images nor the plain agent image carry node; setup.sh puts the `openspec` wrapper on PATH.
COPY --from=node:22.23.3-bookworm-slim /usr/local/bin/node /opt/rllm/agent/node/bin/node
COPY --from=node:22.23.3-bookworm-slim /usr/local/lib/node_modules/npm /tmp/npm
RUN PATH=/opt/rllm/agent/node/bin:$PATH node /tmp/npm/bin/npm-cli.js install -g --prefix /opt/rllm/agent/node @fission-ai/openspec@1.14.1 && \
    rm -rf /tmp/npm /root/.npm && \
    OPENSPEC_TELEMETRY=0 OPENSPEC_NO_UPDATE_CHECK=1 /opt/rllm/agent/node/bin/node /opt/rllm/agent/node/lib/node_modules/@fission-ai/openspec/bin/openspec.js --version
