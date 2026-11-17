"""Explicit live, read-only preflight; not the funded Arc smoke test."""
import json
from dataclasses import asdict

import httpx

from framebounty.arc import preflight

if __name__ == "__main__":
    with httpx.Client(timeout=15) as client:
        print(json.dumps(asdict(preflight(client)), indent=2))
