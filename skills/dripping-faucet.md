---
name: dripping-faucet
description: Use the Radius faucet and funding flows for testnet and dashboard-based wallet setup
published: true
---

# Dripping Faucet Skill

Use this skill whenever the user asks for test funds, faucet access, free SBC, or how to fund a wallet on Radius.

## What this skill means

In this repository, `dripping-faucet` refers to the Radius funding flow for getting started quickly, especially on Radius Testnet.

## When to use this skill

Use this skill for requests like:

- "use the faucet"
- "drip faucet"
- "dripping-faucet"
- "get testnet funds"
- "fund my wallet"
- "claim SBC"
- "how do I use the Radius faucet"
- "how do I get funds on testnet"

## Radius funding model

Radius supports different funding flows depending on network:

### Radius Testnet

- Faucet dashboard: `https://testnet.radiustech.xyz/wallet`
- Faucet API: `https://testnet.radiustech.xyz/api/v1/faucet`
- Explorer: `https://testnet.radiustech.xyz`
- Testnet is the right environment for free funding and development iteration

### Radius Network mainnet

- No public faucet API
- Funding is handled through dashboard-based flows such as claiming SBC or bridging supported assets
- Mainnet dashboard: `https://network.radiustech.xyz`

## How Radius funding works

- Radius uses `SBC` as the stablecoin token commonly transferred by users and apps
- `RUSD` is the native fee token
- If the account has SBC but not enough RUSD for gas, Radius can convert SBC to RUSD inline through Turnstile

That means users often do not need to manually pre-fund gas the same way they would on other EVM chains.

## How to respond

### If the user wants free test funds

1. Confirm they should use Radius Testnet, not mainnet.
2. Provide the faucet dashboard URL.
3. If they need an API or agent flow, provide the testnet faucet API URL.
4. If relevant, show their wallet address first.

### If the user is using this template

1. Explain that the template attempts Radius wallet initialization and test funding on first boot.
2. Mention that the built-in wallet is managed by the bundled Radius scripts.
3. If funding is missing, tell them to check deploy logs for Radius wallet initialization output.

### If the user wants mainnet funds

1. Do not describe mainnet as faucet-driven.
2. Direct them to the Radius dashboard and the documented claim / bridge flows.
3. Clarify that the public faucet API is testnet only.

## Template-specific guidance

This template already includes a Radius wallet bootstrap path. The relevant local context is:

- wallet scripts under `/app/scripts/radius`
- wallet initialization during container boot
- the `radius-wallet` skill for balance, address, and transfer tasks

If a user asks to "get funds" and it sounds like they want to use the agent's built-in wallet, prefer checking the current wallet state first instead of giving only generic faucet advice.

## Troubleshooting guidance

- If testnet funding did not happen automatically, check deploy logs for Radius wallet setup failures.
- If a faucet request succeeds but the user does not see funds, have them verify the wallet address and check the testnet explorer.
- If the user is on mainnet, explain that they should use dashboard or bridge flows instead of expecting a faucet API.
