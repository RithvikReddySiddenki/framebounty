"""Isolated browser harness: real PostgreSQL, API, Next.js, FFmpeg and worker.

Only the browser-wallet boundary is simulated with ephemeral signing keys in the
test runner. No mainnet/testnet transaction or live model call is made. A unique
database schema and storage directory prevent interference with normal demo data.
"""
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    root = Path(__file__).resolve().parents[1]
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url or not database_url.startswith("postgresql+psycopg://"):
        raise SystemExit("Set TEST_DATABASE_URL to a real PostgreSQL instance")
    schema = "browser_" + secrets.token_hex(12)
    run_root = root / ".local" / schema
    run_root.mkdir(parents=True)
    url = make_url(database_url).update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
    env = {**os.environ, "DATABASE_URL": url, "APP_MODE": "fixture", "AUTH_ORIGIN": "http://127.0.0.1:3002",
           "NEXT_PUBLIC_ENABLE_LEGACY_WALLET_LOGIN": "true", "GOOGLE_ONLY_AUTH": "false",
           "NEXT_PUBLIC_API_URL": "http://127.0.0.1:8002", "NEXT_OUTPUT_DIR": ".next-e2e",
           "STORAGE_ROOT": str(run_root / "media"), "PYTHON_BIN": sys.executable,
           "FIXTURE_VERIFICATION_RESULT": "pass", "E2E_VIDEO": str(run_root / "synthetic.mp4"), "E2E_DATABASE_URL": url}
    env["PLAYWRIGHT_BROWSERS_PATH"] = os.getenv("PLAYWRIGHT_BROWSERS_PATH", str(root / ".local" / "browsers"))
    from framebounty.media import media_executable
    executable = media_executable("ffmpeg")
    if not executable:
        raise SystemExit("Install real FFmpeg before browser testing")
    subprocess.run([executable, "-v", "error", "-nostdin", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=15",
        "-t", "12", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", env["E2E_VIDEO"]], check=True, timeout=30)
    admin = create_engine(database_url)
    with admin.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
    test_engine = create_engine(url)
    processes, logs = [], []
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        config = Config(str(root / "services/api/alembic.ini"))
        with test_engine.begin() as db:
            config.attributes["connection"] = db
            command.upgrade(config, "head")
        commands = [([sys.executable, "-m", "uvicorn", "framebounty.main:app", "--host", "127.0.0.1", "--port", "8002"], root, "api"),
            (["node", str(root / "apps/web/node_modules/next/dist/bin/next"), "dev", "--hostname", "127.0.0.1", "--port", "3002"], root / "apps/web", "web")]
        with httpx.Client(timeout=2) as client:
            for address in ("http://127.0.0.1:8002/health", "http://127.0.0.1:3002"):
                try:
                    client.get(address)
                except httpx.HTTPError:
                    continue
                raise RuntimeError("Browser-test port is already occupied; refusing to test an unrelated server")
        for args, cwd, label in commands:
            output = (run_root / f"{label}.log").open("w", encoding="utf-8")
            logs.append(output)
            processes.append(subprocess.Popen(args, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, creationflags=flags))
        with httpx.Client(timeout=2) as client:
            deadline = time.monotonic() + 90
            for address in ("http://127.0.0.1:8002/health", "http://127.0.0.1:3002"):
                while True:
                    if any(p.poll() is not None for p in processes):
                        raise RuntimeError(f"Test server exited; inspect {run_root}")
                    try:
                        if client.get(address).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    if time.monotonic() > deadline:
                        raise RuntimeError(f"Test server readiness timed out; inspect {run_root}")
                    time.sleep(0.5)
        result = subprocess.run(["node", str(root / "apps/web/node_modules/@playwright/test/cli.js"), "test", *sys.argv[1:]], cwd=root / "apps/web", env=env, creationflags=flags, capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(result.stdout, flush=True)
        print(result.stderr, file=sys.stderr, flush=True)
        raise SystemExit(result.returncode)
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for log in logs:
            log.close()
        test_engine.dispose()
        with admin.begin() as db:
            # schema is a fixed prefix plus random hexadecimal, generated here.
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


if __name__ == "__main__":
    main()
