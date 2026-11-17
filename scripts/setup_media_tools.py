"""Checksum-pinned portable Windows build linked from ffmpeg.org/download.html.

Only ignored workspace files change; no system installation or PATH edits.
Other platforms should install FFmpeg/ffprobe using their package manager.
"""
import hashlib
import shutil
import zipfile
from pathlib import Path

import httpx

URL = "https://github.com/FFmpeg-Builds/FFmpeg-Builds/releases/download/autobuild-2026-11-17-12-40/ffmpeg-n9.0.2-57-gd838f9f9ae-win64-gpl-9.0.zip"
SHA256 = "bab1a52add45334440a13c92e8a4b7c10bf3d1fc004576ece5dc2f3ba69d5bfd"


def main():
    root = Path(__file__).resolve().parents[1] / ".local" / "ffmpeg"
    root.mkdir(parents=True, exist_ok=True)
    archive = root / "ffmpeg.zip"
    valid = False
    if archive.exists():
        with archive.open("rb") as source:
            valid = hashlib.file_digest(source, "sha256").hexdigest() == SHA256
    if not valid:
        part = root / "download.part"
        digest = hashlib.sha256()
        count = 0
        with httpx.stream("GET", URL, follow_redirects=True, timeout=120) as response:
            response.raise_for_status()
            with part.open("wb") as output:
                for chunk in response.iter_bytes():
                    count += len(chunk)
                    if count > 250_000_000:
                        raise RuntimeError("Unexpected FFmpeg archive size")
                    digest.update(chunk)
                    output.write(chunk)
        if digest.hexdigest() != SHA256:
            raise RuntimeError("FFmpeg archive checksum mismatch")
        part.replace(archive)
    with zipfile.ZipFile(archive) as source:
        for name in ("ffmpeg.exe", "ffprobe.exe"):
            members = [item for item in source.infolist() if Path(item.filename).name == name]
            if len(members) != 1 or members[0].file_size > 400_000_000:
                raise RuntimeError("Unexpected FFmpeg archive member")
            with source.open(members[0]) as incoming, (root / name).open("wb") as output:
                shutil.copyfileobj(incoming, output)
    print(f"Verified portable FFmpeg/ffprobe in {root}")


if __name__ == "__main__":
    main()
