#!/usr/bin/env python3
"""
Send SBC tokens on Radius Testnet.
Usage: python send.py <to_address> <amount_sbc>

Reads the private key from RADIUS_PRIVATE_KEY env var
or ${HERMES_HOME}/.radius/key.

Output (JSON on stdout):
  { from, to, amount_sbc, tx_hash, block_number, status }
"""
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from chain import (
    create_web3, SBC_ADDRESS, SBC_DECIMALS, ERC20_ABI,
    format_units, parse_units, CHAIN_ID,
)

HERMES_HOME = os.environ.get("HERMES_HOME", "/data/.hermes")
KEY_FILE = Path(HERMES_HOME) / ".radius" / "key"

if len(sys.argv) < 3:
    print("Usage: python send.py <to_address> <amount_sbc>", file=sys.stderr)
    sys.exit(1)

to_arg = sys.argv[1]
amount_arg = sys.argv[2]

from web3 import Web3

if not Web3.is_address(to_arg):
    print(f"Invalid address: {to_arg}", file=sys.stderr)
    sys.exit(1)

try:
    amount_num = float(amount_arg)
    if amount_num <= 0:
        raise ValueError()
except (ValueError, TypeError):
    print(f"Invalid amount: {amount_arg}", file=sys.stderr)
    sys.exit(1)

private_key = os.environ.get("RADIUS_PRIVATE_KEY", "")
if not private_key and KEY_FILE.exists():
    private_key = KEY_FILE.read_text().strip()
if not private_key:
    print(
        "No wallet configured. Set RADIUS_PRIVATE_KEY or run wallet_init.py first.",
        file=sys.stderr,
    )
    sys.exit(1)

w3, account = create_web3(private_key)

to_address = Web3.to_checksum_address(to_arg)
sbc_contract = w3.eth.contract(address=Web3.to_checksum_address(SBC_ADDRESS), abi=ERC20_ABI)

balance = sbc_contract.functions.balanceOf(account.address).call()
amount = parse_units(amount_arg, SBC_DECIMALS)

if balance < amount:
    print(
        f"Insufficient SBC balance. Have {format_units(balance, SBC_DECIMALS)}, need {amount_arg}.",
        file=sys.stderr,
    )
    sys.exit(1)

print(f"Sending {amount_arg} SBC from {account.address} to {to_arg}...", file=sys.stderr)

nonce = w3.eth.get_transaction_count(account.address)
tx = sbc_contract.functions.transfer(to_address, amount).build_transaction({
    "chainId": CHAIN_ID,
    "nonce": nonce,
    "from": account.address,
    "gas": 200000,
    "gasPrice": w3.eth.gas_price,
})

signed = account.sign_transaction(tx)
tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
tx_hash_hex = tx_hash.hex()

print(f"Tx submitted: {tx_hash_hex}. Waiting for confirmation...", file=sys.stderr)
receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

result = {
    "from": account.address,
    "to": to_arg,
    "amount_sbc": amount_arg,
    "tx_hash": tx_hash_hex,
    "block_number": str(receipt["blockNumber"]),
    "status": "success" if receipt["status"] == 1 else "reverted",
}
print(json.dumps(result, indent=2))
