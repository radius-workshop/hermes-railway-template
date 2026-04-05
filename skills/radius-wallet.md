---
name: radius-wallet
description: Built-in Radius Testnet wallet — check balances, send SBC tokens, show wallet address
published: true
---

# Radius Wallet Skill

This agent supports **multiple Radius wallet providers** and can use either local or Para wallets per action.

This agent has a built-in Radius Testnet wallet. Use this skill any time the user asks about their wallet, balance, address, tokens, or anything Radius-related.

## When to use this skill

Use this skill whenever the user asks anything like:

- "what is my wallet" / "show my wallet" / "my wallet address"
- "what is my radius wallet" / "radius wallet" / "show radius wallet"
- "check my balance" / "what's my balance" / "how much do I have"
- "get my wallet balance" / "wallet balance"
- "how much SBC" / "how much RUSD" / "my tokens"
- "send tokens" / "send SBC" / "transfer SBC"
- "fund wallet" / "get testnet tokens" / "get SBC"
- "radius" (when used in the context of a wallet or blockchain query)

**Default behavior:** At the start of any session, proactively mention that a Radius Testnet wallet is available if the user seems to be exploring what the agent can do.

## Wallet model

- Wallet manifest: `RADIUS_WALLET_MANIFEST` (JSON file)
- Configured wallets come from `RADIUS_WALLETS` (e.g. `local,para`)
- Default wallet comes from `RADIUS_DEFAULT_WALLET`

Use this command to inspect wallets:

```bash
node /app/scripts/radius/cmd-wallets.mjs
```

## Available commands (via terminal)

### List wallets / default wallet

```bash
node /app/scripts/radius/cmd-wallets.mjs
```

### Check balance (default wallet)

```bash
node /app/scripts/radius/cmd-balance.mjs
```

### Check balance (explicit wallet)

```bash
node /app/scripts/radius/cmd-balance.mjs --wallet=local
node /app/scripts/radius/cmd-balance.mjs --wallet=para
```

### Send SBC (default wallet)

```bash
node /app/scripts/radius/cmd-send.mjs 0xRECIPIENT AMOUNT
```

### Send SBC (explicit wallet)

```bash
node /app/scripts/radius/cmd-send.mjs --wallet=para 0xRECIPIENT 10
```

### Fund from faucet
1. **"What is my wallet?" / "what is my radius wallet?" / "show wallet"** — print `RADIUS_WALLET_ADDRESS` from env, or run `balance.mjs` and show the address field.

2. **"Check balance" / "get my wallet balance" / "how much SBC do I have?"** — run `balance.mjs` and report RUSD and SBC balances.

```bash
node /app/scripts/radius/cmd-fund.mjs --wallet=local
node /app/scripts/radius/cmd-fund.mjs --wallet=para
node /app/scripts/radius/cmd-fund.mjs --wallet=both
```

## Responding to user requests

- “show my wallets” / “list wallets” → run `cmd-wallets.mjs`.
- “show default wallet” → use `cmd-wallets.mjs` and report `defaultWallet`.
- “use the para wallet” or “use local wallet” → run the requested command with `--wallet=...`.
- “fund my para wallet” / “fund both wallets” → run `cmd-fund.mjs` with explicit wallet target.
- “send 10 SBC to 0x... using para” → confirm recipient + amount, then run `cmd-send.mjs --wallet=para ...`.
- “check local wallet balance” → run `cmd-balance.mjs --wallet=local`.

Always return tx hash + explorer link for sends and funding transactions.
