"""Radius Testnet chain configuration and utilities."""

CHAIN_ID = 72344
CHAIN_NAME = "Radius Testnet"
RPC_URL = "https://rpc.testnet.radiustech.xyz"
FAUCET_BASE = "https://testnet.radiustech.xyz/api/v1/faucet"
BLOCK_EXPLORER_URL = "https://testnet.radiustech.xyz"

SBC_ADDRESS = "0x33ad9e4BD16B69B5BFdED37D8B5D9fF9aba014Fb"
SBC_DECIMALS = 6
RUSD_DECIMALS = 18

ERC20_ABI = [
    {
        "type": "function",
        "name": "balanceOf",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "transfer",
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
    },
    {
        "type": "function",
        "name": "decimals",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint8"}],
        "stateMutability": "view",
    },
]


def format_units(value: int, decimals: int) -> str:
    """Format integer units to decimal string (mirrors viem's formatUnits)."""
    negative = value < 0
    if negative:
        value = -value
    s = str(value).zfill(decimals)
    integer = s[:-decimals] if len(s) > decimals else "0"
    fraction = s[len(s) - decimals:]
    fraction = fraction.rstrip("0")
    sign = "-" if negative else ""
    return f"{sign}{integer}{f'.{fraction}' if fraction else ''}"


def parse_units(amount_str: str, decimals: int) -> int:
    """Parse decimal string to integer units (mirrors viem's parseUnits)."""
    from decimal import Decimal, ROUND_DOWN
    d = Decimal(str(amount_str))
    return int((d * Decimal(10 ** decimals)).to_integral_value(rounding=ROUND_DOWN))


def create_web3(private_key: str = None):
    """Return (w3, account). account is None if private_key is not provided."""
    from web3 import Web3
    from eth_account import Account

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    account = Account.from_key(private_key) if private_key else None
    return w3, account
