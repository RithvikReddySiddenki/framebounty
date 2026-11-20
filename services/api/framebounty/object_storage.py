"""Private Supabase objects with local decoder/cache files.

No public/signed URLs are returned. Authorization and paid-original gates remain
in the API. Persist bytes before publishing their DB reference; a crash may leave
a private orphan, but never a successful submission backed only by ephemeral disk.
"""
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .media import LocalStorage, MAX_UPLOAD, MediaUnavailable


class SupabaseStorage(LocalStorage):
    def __init__(self, root=None, transport=None):
        super().__init__(root)
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        parsed = urlparse(self.url)
        self.bucket = os.getenv("SUPABASE_STORAGE_BUCKET", "framebounty-media")
        self.secret = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        if (parsed.scheme != "https" or not parsed.hostname or not parsed.hostname.endswith(".supabase.co")
                or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment
                or parsed.port not in {None, 443} or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", self.bucket)
                or not self.secret):
            raise MediaUnavailable("Supabase private storage is not configured")
        self.transport = transport

    def client(self):
        return httpx.Client(base_url=self.url + "/storage/v1/", timeout=120, follow_redirects=False,
            transport=self.transport, headers={"apikey": self.secret, "Authorization": "Bearer " + self.secret})

    def check_private(self, client):
        response = client.get("bucket/" + self.bucket)
        response.raise_for_status()
        if response.json().get("public") is not False:
            raise MediaUnavailable("Media bucket must be private")

    def persist(self, key: str, content_type: str):
        source = self.path(key)
        if not source.is_file() or source.stat().st_size > MAX_UPLOAD:
            raise MediaUnavailable("Private media is unavailable or oversized")
        try:
            with self.client() as client, source.open("rb") as body:
                self.check_private(client)
                # Keys are random and immutable. Never overwrite an existing object.
                response = client.post("object/" + self.bucket + "/" + key, content=body,
                    headers={"Content-Type": content_type, "Content-Length": str(source.stat().st_size), "x-upsert": "false"})
                response.raise_for_status()
        except (httpx.HTTPError, ValueError, TypeError):
            raise MediaUnavailable("Private media storage is unavailable; retry without assuming submission succeeded") from None

    def materialize(self, key: str) -> Path:
        destination = self.path(key)
        temporary = None
        try:
            with self.client() as client:
                self.check_private(client)
                if destination.is_file(): return destination
                with client.stream("GET", "object/" + self.bucket + "/" + key) as response:
                    if response.status_code == 404: return destination
                    response.raise_for_status()
                    # A failed/oversized response never becomes a readable cache file.
                    with tempfile.NamedTemporaryFile(dir=self.root, delete=False) as target:
                        temporary = Path(target.name)
                        count = 0
                        for chunk in response.iter_bytes(1024 * 1024):
                            count += len(chunk)
                            if count > MAX_UPLOAD: raise MediaUnavailable("Private media exceeds the supported limit")
                            target.write(chunk)
                        target.flush(); os.fsync(target.fileno())
                    temporary.replace(destination)
                return destination
        except (httpx.HTTPError, ValueError, TypeError):
            raise MediaUnavailable("Private media storage is unavailable") from None
        finally:
            if temporary is not None: temporary.unlink(missing_ok=True)


def private_storage():
    backend = os.getenv("STORAGE_BACKEND", "local")
    if backend == "local": return LocalStorage()
    if backend == "supabase": return SupabaseStorage()
    raise MediaUnavailable("Unknown private storage backend")
