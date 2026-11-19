"""Install checksum-pinned official Arc Foundry binaries only in ignored .local.

Windows executes these Linux binaries through WSL. This does not alter PATH,
install OS packages, or configure wallets. Run with the project's virtualenv.
"""
import hashlib
import tarfile
from pathlib import Path

import httpx

VERSION = "v0.8.0-4"
SHA256 = "78330505af7dc0d2c9b55fc1aed00d9d063581bb57054949d31ef1c1b4bdbc5e"
URL = f"https://github.com/circlefin/arc-foundry/releases/download/{VERSION}/arc-foundry-{VERSION}-x86_64-unknown-linux-gnu.tar.gz"
SOLC_PATH = "solc-linux-amd64-v0.8.24+commit.e11b9ed9"
SOLC_SHA256 = "fb03a29a517452b9f12bcf459ef37d0a543765bb3bbc911e70a87d6a37c30d5f"


def checksum(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main():
    root = Path(__file__).resolve().parents[1] / ".local" / "arc-foundry"
    root.mkdir(parents=True, exist_ok=True)
    archive = root / "toolchain.tar.gz"
    if not archive.exists() or checksum(archive) != SHA256:
        temporary = root / "download.part"
        digest = hashlib.sha256()
        count = 0
        with httpx.stream("GET", URL, follow_redirects=True, timeout=120) as response:
            response.raise_for_status()
            with temporary.open("wb") as output:
                for chunk in response.iter_bytes():
                    count += len(chunk)
                    if count > 100_000_000:
                        raise RuntimeError("Unexpected toolchain archive size")
                    digest.update(chunk)
                    output.write(chunk)
        if digest.hexdigest() != SHA256:
            raise RuntimeError("Toolchain checksum mismatch; archive will not be executed")
        temporary.replace(archive)
    # Never extract arbitrary member paths, permissions, links or archive metadata.
    with tarfile.open(archive, "r:gz") as source:
        for name in ["forge", "cast", "anvil"]:
            members = [m for m in source.getmembers() if Path(m.name).name == name and m.isfile()]
            if len(members) != 1 or members[0].size > 200_000_000:
                raise RuntimeError(f"Unexpected toolchain member: {name}")
            stream = source.extractfile(members[0])
            if stream is None:
                raise RuntimeError("Unreadable toolchain archive")
            target = root / name
            target.write_bytes(stream.read())
            target.chmod(0o755)
    compiler = root / "solc-0.8.24"
    if not compiler.exists() or checksum(compiler) != SOLC_SHA256:
        response = httpx.get(f"https://binaries.soliditylang.org/linux-amd64/{SOLC_PATH}", timeout=120)
        response.raise_for_status()
        if hashlib.sha256(response.content).hexdigest() != SOLC_SHA256:
            raise RuntimeError("Solidity compiler checksum mismatch")
        compiler.write_bytes(response.content)
    compiler.chmod(0o755)
    print(f"Verified Arc Foundry {VERSION} in {root}")


if __name__ == "__main__":
    main()
