"""Create a dedicated local testnet allocator configuration without showing keys.

No network requests, funding, signatures or live-mode changes occur. Existing
allocator configuration is preserved. Run only in the intended project checkout.
"""
import os
import subprocess
import tempfile
from pathlib import Path

from eth_account import Account


def main():
    root = Path(__file__).resolve().parents[1]
    path = root / ".env"
    if not path.is_file():
        raise SystemExit("Create the local .env from .env.example first")
    ignored = subprocess.run(["git", "check-ignore", "--quiet", ".env"], cwd=root, capture_output=True)
    if ignored.returncode:
        raise SystemExit("Refusing setup: .env must be ignored by Git")
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines()
    settings = dict(line.split("=", 1) for line in lines if line and not line.startswith("#") and "=" in line)
    if settings.get("ALLOW_CHAIN_TRANSACTIONS", "").strip() != "false":
        raise SystemExit("Disable chain transactions before allocator setup")
    if settings.get("ARC_ALLOCATOR_PRIVATE_KEY", "").strip() or settings.get("ARC_ALLOCATOR_ADDRESS", "").strip():
        raise SystemExit("Existing allocator settings preserved; no wallet was created")
    for name in ("ARC_ALLOCATOR_PRIVATE_KEY", "ARC_ALLOCATOR_ADDRESS"):
        if sum(line.startswith(name + "=") for line in lines) != 1:
            raise SystemExit("Allocator setting is missing or duplicated; fix .env first")
    account = Account.create()
    replacements = {"ARC_ALLOCATOR_PRIVATE_KEY": "0x" + bytes(account.key).hex(),
                    "ARC_ALLOCATOR_ADDRESS": account.address.lower()}
    updated = [name + "=" + replacements[name] if (name := line.split("=", 1)[0]) in replacements else line for line in lines]
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=".env.allocator-", dir=root, delete=False) as target:
            temporary = Path(target.name)
            target.write("\n".join(updated) + "\n")
        if path.read_text(encoding="utf-8") != original:
            raise SystemExit("Environment file changed during setup; existing file preserved")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    print("Dedicated allocator public address: " + account.address)
    print("Private key saved only in ignored .env. Live transactions remain disabled.")


if __name__ == "__main__":
    main()
