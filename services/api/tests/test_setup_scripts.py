"""Real filesystem checks: deploying must preserve unrelated secret settings."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

from framebounty.chain_rpc import ChainFailure

spec = importlib.util.spec_from_file_location("deployment_cli", Path(__file__).resolve().parents[3] / "scripts/deploy_arc.py")
deployment_cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deployment_cli)

CONTRACT = "0x" + "1" * 40


def test_deployed_address_update_preserves_private_settings_and_disabled_flags(tmp_path):
    path = tmp_path / ".env"
    path.write_text("GEMINI_API_KEY=synthetic-test-only\nALLOW_CHAIN_TRANSACTIONS=false\nARC_ESCROW_ADDRESS=\n")
    deployment_cli.configure(tmp_path, CONTRACT)
    assert path.read_text() == "GEMINI_API_KEY=synthetic-test-only\nALLOW_CHAIN_TRANSACTIONS=false\nARC_ESCROW_ADDRESS=" + CONTRACT + "\n"
    deployment_cli.configure(tmp_path, CONTRACT)
    assert "GEMINI_API_KEY=synthetic-test-only" in path.read_text()


def test_existing_different_escrow_configuration_is_preserved(tmp_path):
    path = tmp_path / ".env"
    original = "ARC_ESCROW_ADDRESS=0x" + "2" * 40 + "\n"
    path.write_text(original)
    with pytest.raises(ChainFailure, match="preserved"):
        deployment_cli.configure(tmp_path, CONTRACT)
    assert path.read_text() == original


def test_preexisting_temporary_configuration_is_not_deleted(tmp_path):
    path = tmp_path / ".env"
    path.write_text("ARC_ESCROW_ADDRESS=\n")
    temporary = tmp_path / ".env.deployment.tmp"
    temporary.write_text("preserve preexisting recovery file")
    with pytest.raises(FileExistsError):
        deployment_cli.configure(tmp_path, CONTRACT)
    assert temporary.read_text() == "preserve preexisting recovery file"
    assert path.read_text() == "ARC_ESCROW_ADDRESS=\n"


def test_api_key_alone_cannot_authorize_live_inference():
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run([sys.executable, str(root / "scripts/smoke_gemini.py")],
        env={**os.environ, "GEMINI_API_KEY": "synthetic-invalid-key", "ALLOW_LIVE_MODEL_SMOKE": "false",
             "GEMINI_FREE_TIER_CONFIRMED": "true"}, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "explicitly enable this smoke first" in result.stderr
