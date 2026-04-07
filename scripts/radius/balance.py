#!/usr/bin/env python3
"""
Print the Radius wallet balances (RUSD native + SBC ERC-20).
Usage: python balance.py [address]

If address is omitted, reads from RADIUS_WALLET_ADDRESS env var
or ${HERMES_HOME}/.radius/address.

Output (JSON on stdout):
  { address, rusd, rusd_raw, sbc, sbc_raw }
"""
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chain import (
    create_web3, SBC_ADDRESS, SBC_DECIMALS, RUSD_DECIMALS, ERC20_ABI, format_units,
)

HERMES_HOME = os.environ.get("HERMES_HOME", "/data/.hermes")
KEY_FILE = Path(HERMES_HOME) / ".radius" / "key"
ADDR_FILE = Path(HERMES_HOME) / ".radius" / "address"

private_key = os.environ.get("RADIUS_PRIVATE_KEY", "")
if not private_key and KEY_FILE.exists():
    private_key = KEY_FILE.read_text().strip()
if not private_key:
    print(
        "No wallet configured. Set RADIUS_PRIVATE_KEY or run wallet_init.py first.",
        file=sys.stderr,
    )
    sys.exit(1)

address = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.environ.get("RADIUS_WALLET_ADDRESS", "")
    or (ADDR_FILE.read_text().strip() if ADDR_FILE.exists() else "")
)

if not address:
    print(
        "No address found. Provide one as an argument or run wallet_init.py first.",
        file=sys.stderr,
    )
    sys.exit(1)

from web3 import Web3

w3, _ = create_web3(private_key)
checksum_addr = Web3.to_checksum_address(address)

rusd_raw = w3.eth.get_balance(checksum_addr)

contract = w3.eth.contract(address=Web3.to_checksum_address(SBC_ADDRESS), abi=ERC20_ABI)
sbc_raw = contract.functions.balanceOf(checksum_addr).call()

result = {
    "address": address,
    "rusd": format_units(rusd_raw, RUSD_DECIMALS),
    "rusd_raw": str(rusd_raw),
    "sbc": format_units(sbc_raw, SBC_DECIMALS),
    "sbc_raw": str(sbc_raw),
}
print(json.dumps(result, indent=2))
