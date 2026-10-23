"""Keep docker sandboxes off the internet.

Sandboxes join ``NETWORK``, a docker ``--internal`` network: docker gives it no
route out, so neither the internet nor the host is reachable from it. The one
way out is ``RELAY``, a small container on both that network and the default
bridge. It drops everything it is asked to forward except TCP to the host ports
the gateway opens with :func:`allow_host_port`, so an agent can reach its model
but cannot fetch the task's upstream release, clone its repository or reach
other services on the host.

Sandboxes resolve ``host.docker.internal`` to the relay, so gateway URLs keep
working unchanged.

Grading can opt back into the internet (:class:`NetworkOpeningEvaluator`):
once the agent is done, the sandbox also joins ``VERIFY_NETWORK``, an ordinary
bridge, for tests that download datasets, models or build backends.
"""

from __future__ import annotations

import fcntl
import io
import logging
import os
import tempfile
import threading

logger = logging.getLogger(__name__)

NETWORK = "rllm-sandbox-isolated"
RELAY = "rllm-egress-relay"
RELAY_IMAGE = "rllm-egress-relay:1"
VERIFY_NETWORK = "rllm-sandbox-verify"
_RELAY_DOCKERFILE = b'FROM alpine:3.20\nRUN apk add --no-cache iptables\nENTRYPOINT ["sleep", "infinity"]\n'

# Several eval/train processes can start at once; the docker objects are shared.
_thread_lock = threading.Lock()
_LOCK_PATH = os.path.join(tempfile.gettempdir(), "rllm-egress-relay.lock")


class _ProcessLock:
    def __enter__(self):
        _thread_lock.acquire()
        self._fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o666)
        fcntl.flock(self._fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self._fd, fcntl.LOCK_UN)
        os.close(self._fd)
        _thread_lock.release()


def _client(client=None):
    if client is not None:
        return client
    import docker

    return docker.from_env()


def _ensure_image(client) -> None:
    import docker

    try:
        client.images.get(RELAY_IMAGE)
    except docker.errors.ImageNotFound:
        logger.info("Building %s", RELAY_IMAGE)
        client.images.build(fileobj=io.BytesIO(_RELAY_DOCKERFILE), tag=RELAY_IMAGE, rm=True)


def _ensure_network(client):
    nets = client.networks.list(names=[NETWORK])
    if nets:
        return nets[0]
    return client.networks.create(NETWORK, driver="bridge", internal=True)


def _subnet(network) -> str:
    network.reload()
    return network.attrs["IPAM"]["Config"][0]["Subnet"]


def _relay_exec(relay, script: str) -> None:
    rc, out = relay.exec_run(["sh", "-c", script])
    if rc != 0:
        raise RuntimeError(f"egress relay rule setup failed (rc={rc}): {out.decode(errors='replace')[-500:]}")


def _ensure_relay_container(client, network):
    import docker

    try:
        relay = client.containers.get(RELAY)
        if relay.status != "running":
            # Its iptables rules lived in the old network namespace; start clean.
            relay.remove(force=True)
            relay = None
    except docker.errors.NotFound:
        relay = None
    if relay is None:
        relay = client.containers.run(
            RELAY_IMAGE,
            name=RELAY,
            detach=True,
            cap_add=["NET_ADMIN"],
            sysctls={"net.ipv4.ip_forward": "1"},
            extra_hosts={"host.docker.internal": "host-gateway"},
        )
        network.connect(relay)
    relay.reload()
    if NETWORK not in relay.attrs["NetworkSettings"]["Networks"]:
        network.connect(relay)
        relay.reload()
    subnet = _subnet(network)
    # Idempotent: each rule is added only if absent (-C checks, -A appends).
    _relay_exec(
        relay,
        "iptables -P FORWARD DROP"
        " && { iptables -C FORWARD -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null"
        " || iptables -A FORWARD -m state --state ESTABLISHED,RELATED -j ACCEPT; }"
        f" && {{ iptables -t nat -C POSTROUTING -s {subnet} -j MASQUERADE 2>/dev/null"
        f" || iptables -t nat -A POSTROUTING -s {subnet} -j MASQUERADE; }}",
    )
    return relay


def ensure_relay(client=None) -> str:
    """Create the isolated network and the relay if missing; return the relay's address on it."""
    client = _client(client)
    with _ProcessLock():
        _ensure_image(client)
        network = _ensure_network(client)
        relay = _ensure_relay_container(client, network)
    return relay.attrs["NetworkSettings"]["Networks"][NETWORK]["IPAddress"]


def allow_host_port(port: int, client=None) -> None:
    """Let sandboxes reach TCP ``port`` on the host (through the relay) and nothing else new."""
    client = _client(client)
    ensure_relay(client)
    with _ProcessLock():
        relay = client.containers.get(RELAY)
        subnet = _subnet(client.networks.list(names=[NETWORK])[0])
        port = int(port)
        host = "$(getent hosts host.docker.internal | awk '{print $1}')"
        _relay_exec(
            relay,
            f"H={host}; [ -n \"$H\" ]"
            f" && {{ iptables -t nat -C PREROUTING -s {subnet} -p tcp --dport {port} -j DNAT --to-destination $H:{port} 2>/dev/null"
            f" || iptables -t nat -A PREROUTING -s {subnet} -p tcp --dport {port} -j DNAT --to-destination $H:{port}; }}"
            f" && {{ iptables -C FORWARD -s {subnet} -d $H -p tcp --dport {port} -j ACCEPT 2>/dev/null"
            f" || iptables -A FORWARD -s {subnet} -d $H -p tcp --dport {port} -j ACCEPT; }}",
        )
    logger.info("Sandbox egress: host port %d open through %s", port, RELAY)


def ensure_verify_network(client=None):
    """The bridge a sandbox joins for grading; created on first use."""
    client = _client(client)
    with _ProcessLock():
        nets = client.networks.list(names=[VERIFY_NETWORK])
        return nets[0] if nets else client.networks.create(VERIFY_NETWORK, driver="bridge")


class NetworkOpeningEvaluator:
    """Evaluator wrapper: give the sandbox the internet, then grade as usual.

    The agent has finished by the time ``evaluate`` runs, so what it could
    have fetched no longer matters; the tests get the network they need.
    """

    def __init__(self, inner, sandbox):
        self.inner = inner
        self.sandbox = sandbox

    def evaluate(self, task, episode):
        self.sandbox.open_network()
        return self.inner.evaluate(task, episode)

    def __getattr__(self, name):
        # Callers read evaluator attributes (e.g. sandbox, script_path); keep
        # the wrapper transparent to them.
        return getattr(self.inner, name)
