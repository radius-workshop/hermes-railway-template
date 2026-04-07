#!/usr/bin/env python3
"""
Radius wallet init — runs once on first boot.
- Generates a new private key (or uses RADIUS_PRIVATE_KEY if set).
- Persists key + address under ${HERMES_HOME}/.radius/.
- Requests testnet SBC from the faucet (unless RADIUS_AUTO_FUND=false).
"""
import os
import sys
import time
import json
import secrets
import requests
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chain import (
    create_web3, SBC_ADDRESS, SBC_DECIMALS, ERC20_ABI,
    FAUCET_BASE, format_units,
)

HERMES_HOME = os.environ.get("HERMES_HOME", "/data/.hermes")
RADIUS_DIR = Path(HERMES_HOME) / ".radius"
KEY_FILE = RADIUS_DIR / "key"
ADDR_FILE = RADIUS_DIR / "address"

RADIUS_DIR.mkdir(parents=True, exist_ok=True)


def generate_private_key() -> str:
    """Generate a new secp256k1 private key (0x-prefixed hex)."""
    from eth_account import Account
    acct = Account.create()
    return "0x" + bytes(acct.key).hex()


# Determine private key
private_key = os.environ.get("RADIUS_PRIVATE_KEY", "")
is_new_key = False

if not private_key:
    if KEY_FILE.exists():
        private_key = KEY_FILE.read_text().strip()
        print("[radius] Using stored wallet key.")
    else:
        private_key = generate_private_key()
        is_new_key = True
        print("[radius] Generated new wallet private key.")

from eth_account import Account
account = Account.from_key(private_key)
address = account.address
print(f"[radius] Wallet address: {address}")

# Persist key (restricted permissions) and address
if is_new_key or not KEY_FILE.exists():
    KEY_FILE.write_text(private_key)
    KEY_FILE.chmod(0o600)

ADDR_FILE.write_text(address)

# Faucet funding
auto_fund = os.environ.get("RADIUS_AUTO_FUND", "")
if auto_fund in ("false", "0"):
    print("[radius] RADIUS_AUTO_FUND disabled, skipping faucet.")
    sys.exit(0)


def get_challenge(addr: str) -> str:
    res = requests.get(f"{FAUCET_BASE}/challenge/{addr}", params={"token": "SBC"}, timeout=15)
    res.raise_for_status()
    data = res.json()
    return data.get("message") or data.get("challenge", "")


def sign_message(message: str) -> str:
    from eth_account.messages import encode_defunct
    msg = encode_defunct(text=message)
    signed = account.sign_message(msg)
    return "0x" + signed.signature.hex()


def drip_with_signature(addr: str) -> dict:
    message = get_challenge(addr)
    signature = sign_message(message)
    res = requests.post(
        f"{FAUCET_BASE}/drip",
        json={"address": addr, "token": "SBC", "signature": signature},
        timeout=15,
    )
    data = res.json()
    if not res.ok:
        raise RuntimeError(data.get("error") or data.get("message") or json.dumps(data))
    return data


def drip(addr: str):
    res = requests.post(
        f"{FAUCET_BASE}/drip",
        json={"address": addr, "token": "SBC"},
        timeout=15,
    )
    data = res.json()
    if res.ok:
        return data

    err_code = data.get("error", "")
    if err_code == "signature_required" or res.status_code == 401:
        print("[radius] Faucet requires signed request, signing challenge...")
        return drip_with_signature(addr)
    if err_code == "rate_limited":
        retry_ms = data.get("retry_after_ms") or (data.get("retry_after_seconds", 0) * 1000)
        print(f"[radius] Faucet rate-limited. Retry after {int(retry_ms / 1000)}s.")
        return None
    raise RuntimeError(data.get("error") or data.get("message") or json.dumps(data))


def get_sbc_balance(addr: str) -> int:
    from web3 import Web3
    w3, _ = create_web3(private_key)
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(SBC_ADDRESS), abi=ERC20_ABI
    )
    return contract.functions.balanceOf(Web3.to_checksum_address(addr)).call()


try:
    print("[radius] Requesting SBC from faucet...")
    result = drip(address)
    if result:
        tx_hash = result.get("tx_hash") or result.get("txHash") or result.get("hash", "")
        if tx_hash:
            print(f"[radius] Faucet tx: {tx_hash}")
        print("[radius] Faucet request submitted. Waiting for balance...")
        for _ in range(5):
            time.sleep(3)
            try:
                bal = get_sbc_balance(address)
                if bal > 0:
                    print(f"[radius] SBC balance: {format_units(bal, SBC_DECIMALS)} SBC")
                    break
            except Exception:
                pass
except Exception as err:
    print(f"[radius] Faucet funding failed: {err}", file=sys.stderr)
    print("[radius] Continuing — use /radius fund in chat to retry.")

print("[radius] Wallet initialization complete.")
