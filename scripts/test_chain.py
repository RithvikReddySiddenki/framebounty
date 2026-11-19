"""Run the real transaction suite on an owned, ephemeral local Anvil instance.

No persisted keys or funded wallets are used. On Windows the pinned Linux Arc
toolchain runs through WSL; CI runs it directly. The node is always stopped.
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx


def main():
    root = Path(__file__).resolve().parents[1]
    if not os.getenv("TEST_DATABASE_URL"):
        raise SystemExit("Set TEST_DATABASE_URL to an isolated-test PostgreSQL database")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    binary = root / ".local/arc-foundry/anvil"
    prefix = []
    if os.name == "nt":
        distro = os.getenv("TEST_WSL_DISTRO", "Ubuntu")
        converted = subprocess.check_output(["wsl.exe", "-d", distro, "--exec", "wslpath", "-a", str(binary)], text=True).strip()
        prefix = ["wsl.exe", "-d", distro, "--exec"]
        executable = converted
    else:
        executable = str(binary)
    command = prefix + [executable, "--silent", "--mnemonic-random", "12", "--accounts", "4",
        "--host", "127.0.0.1", "--port", str(port), "--chain-id", "31337", "--network", "ethereum"]
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    node = subprocess.Popen(command, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    url = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(timeout=1, trust_env=False) as client:
            deadline = time.monotonic() + 30
            while True:
                if node.poll() is not None:
                    raise RuntimeError("Owned local chain exited during startup")
                try:
                    response = client.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []})
                    if response.json().get("result") == "0x7a69":
                        break
                except (httpx.HTTPError, ValueError):
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError("Owned local chain did not become ready")
                time.sleep(0.1)
        env = {**os.environ, "TEST_CHAIN_RPC_URL": url}
        result = subprocess.run([sys.executable, "-m", "pytest", "services/api/tests/test_chain.py", "services/api/tests/test_chain_workflow.py", "services/api/tests/test_deployment.py", "-q", *sys.argv[1:]],
            cwd=root, env=env)
        return result.returncode
    finally:
        # RPC terminates the exact instance on Windows too, where killing the
        # wsl.exe wrapper alone need not terminate its Linux child.
        try:
            with httpx.Client(timeout=2, trust_env=False) as client:
                client.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "anvil_shutdown", "params": []})
        except httpx.HTTPError:
            pass
        if node.poll() is None:
            node.terminate()
        try:
            node.wait(timeout=5)
        except subprocess.TimeoutExpired:
            node.kill()
            node.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
