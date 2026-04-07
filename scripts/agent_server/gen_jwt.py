#!/usr/bin/env python3
"""
Generate a self-signed DID JWT for A2A authentication.
Usage: python gen_jwt.py

Reads the signing key from RADIUS_PRIVATE_KEY env var.
Derives a did:web DID from PUBLIC_URL or RAILWAY_PUBLIC_DOMAIN.

Output (JSON on stdout):
  { did, token }
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auth import setup_auth, get_did, issue_token


async def main() -> None:
    raw_key = os.environ.get("RADIUS_PRIVATE_KEY", "")
    if not raw_key:
        # Fall back to wallet key file — the terminal environment may not
        # inherit RADIUS_PRIVATE_KEY even though the container has it.
        hermes_home = os.environ.get("HERMES_HOME", "/data/.hermes")
        key_file = os.path.join(hermes_home, ".radius", "key")
        if os.path.exists(key_file):
            with open(key_file) as f:
                raw_key = f.read().strip()
    if not raw_key:
        print("RADIUS_PRIVATE_KEY is not set and no key file found", file=sys.stderr)
        sys.exit(1)

    base_url = (
        os.environ.get("PUBLIC_URL")
        or (
            f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}"
            if os.environ.get("RAILWAY_PUBLIC_DOMAIN")
            else f"http://localhost:{os.environ.get('PORT', '3000')}"
        )
    )

    await setup_auth(base_url)
    did = get_did()
    token = await issue_token("hermes")
    print(json.dumps({"did": did, "token": token}))


if __name__ == "__main__":
    asyncio.run(main())
