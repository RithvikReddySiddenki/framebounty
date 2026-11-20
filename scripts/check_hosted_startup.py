"""Exercise the actual Bash supervisor with disposable child executables.

Run with Linux Python (WSL on Windows). No Docker daemon, database, keys, remote
requests or installed FrameBounty package are used. Child processes are the only
simulated boundary; the entrypoint, ordering and termination are real.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    root = Path(__file__).resolve().parents[1]
    script = root / "deploy/railway/start.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)
    with tempfile.TemporaryDirectory(prefix="startup-", dir=root / ".local") as directory:
        staging = Path(directory)
        fake = staging / "bin"; fake.mkdir()
        program = "#!" + sys.executable + "\n" + '''import os, sys, signal, time
from pathlib import Path
name = Path(sys.argv[0]).name
role = sys.argv[2] if name == "python" else name
log = Path(os.environ["STARTUP_EVENTS"])
def record(event):
    with log.open("a") as target: target.write(event + "\\n")
record("start:" + role)
if role == "framebounty.hosted":
    assert os.environ["DATABASE_URL"].startswith("postgresql+psycopg://")
    sys.exit(2 if os.environ.get("FAIL_CONFIG") == "true" else 0)
if role == "alembic": sys.exit(0)
def stop(*args):
    record("stop:" + role)
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)
if role == "uvicorn":
    time.sleep(0.5)
    sys.exit(9)
while True: time.sleep(0.1)
'''
        for name in ("python", "alembic", "uvicorn"):
            executable = fake / name
            executable.write_text(program); executable.chmod(0o755)
        for chain, invalid in ((False, False), (True, False), (False, True)):
            events = staging / f"events-{chain}-{invalid}"
            env = {**os.environ, "PATH": str(fake) + os.pathsep + os.environ["PATH"],
                "STARTUP_EVENTS": str(events), "STORAGE_ROOT": str(staging / "cache"),
                "DATABASE_URL": "postgresql://synthetic-placeholder", "RUN_CHAIN_WORKER": str(chain).lower(),
                "FAIL_CONFIG": str(invalid).lower()}
            result = subprocess.run(["bash", str(script)], env=env, capture_output=True, timeout=10)
            assert result.returncode != 0, "Container must fail when a child or config fails"
            observed = events.read_text().splitlines()
            assert observed[0] == "start:framebounty.hosted"
            if invalid:
                assert observed == ["start:framebounty.hosted"]
            else:
                assert observed[1] == "start:alembic"
                assert "start:uvicorn" in observed
                assert "stop:framebounty.worker" in observed
                assert ("start:framebounty.chain_worker" in observed) == chain
                if chain: assert "stop:framebounty.chain_worker" in observed
    print("Hosted supervisor: fixture, chain-worker and invalid-config cases passed")


if __name__ == "__main__": main()
