"""Export one canonical backend contract artifact after a pinned Foundry build.

--check is a CI gate: ABI/runtime changes require updating consumers and tests.
Only the ABI and compiler-produced bytecode are tracked, never build caches.
"""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    built = json.loads((root / "contracts/out/FrameBountyEscrow.sol/FrameBountyEscrow.json").read_text())
    source = (root / "contracts/src/FrameBountyEscrow.sol").read_bytes().replace(b"\r\n", b"\n")
    result = {"compiler": "0.8.24", "source_sha256": hashlib.sha256(source).hexdigest(),
        "abi": built["abi"], "creation_bytecode": built["bytecode"]["object"],
        "runtime_bytecode": built["deployedBytecode"]["object"],
        "immutable_references": built["deployedBytecode"]["immutableReferences"]}
    expected = json.dumps(result, indent=2, sort_keys=True) + "\n"
    target = root / "services/api/framebounty/contract_abi/escrow.json"
    if args.check:
        if not target.exists() or target.read_text(encoding="utf-8") != expected:
            raise SystemExit("Canonical escrow artifact is stale; rebuild, export, and update consumers/tests")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(expected, encoding="utf-8")
    print("Canonical escrow ABI/runtime verified" if args.check else "Canonical escrow ABI/runtime exported")


if __name__ == "__main__":
    main()
