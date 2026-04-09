---
name: radius-dev
description: Use to build on Radius Network with Radius-specific RPC, fee, and compatibility guidance
published: true
---

# Radius Dev Skill

Use this skill whenever the user asks about Radius as a product/network, or needs help building an app, wallet flow, or integration on Radius.

## What Radius means here

In this repository, `Radius` means the Radius network / ecosystem by default.

Radius is a settlement layer for stablecoin-native micropayments. It is built for machine-to-machine payments, is EVM compatible, targets sub-second finality, and is designed for predictable low transaction costs.

Do not default to:

- the geometry meaning of radius
- the legacy RADIUS AAA networking protocol

unless the user explicitly asks for those topics.

## When to use this skill

Use this skill for requests like:

- "what do you know about Radius"
- "tell me about Radius"
- "what is Radius"
- "how do I build on Radius"
- "how do I integrate with Radius"
- "what RPC should I use"
- "what are the chain settings"
- "make this code work on Radius"
- "review this integration for Radius compatibility"

## Core network facts

### Radius Network mainnet

- Network name: Radius Network
- RPC endpoint: `https://rpc.radiustech.xyz`
- Chain ID: `723`
- Currency symbol: `RUSD`
- Explorer: `https://network.radiustech.xyz`
- Faucet: no public faucet API on mainnet; use dashboard flows

### Radius Testnet

- Network name: Radius Testnet
- RPC endpoint: `https://rpc.testnet.radiustech.xyz`
- Chain ID: `72344`
- Currency symbol: `RUSD`
- Explorer: `https://testnet.radiustech.xyz`
- Faucet dashboard: `https://testnet.radiustech.xyz/wallet`
- Faucet API: `https://testnet.radiustech.xyz/api/v1/faucet`

### Token and fee model

- `RUSD` is the native token and fee token.
- `SBC` is the ERC-20 stablecoin commonly used for transfers.
- If an account has SBC but not enough RUSD for gas, Radius can convert SBC to RUSD inline through Turnstile.
- Radius is stablecoin-native and does not rely on a volatile native gas asset.

## Tooling standards

Prefer these tools and patterns for Radius work:

- `viem` for client integrations
- `Foundry` for contract development and scripting
- `pnpm` when a package manager choice matters

Avoid defaulting to:

- `ethers.js` for new examples
- `Hardhat` for Radius-first examples
- Ethereum-specific fee assumptions

## Radius-specific behavior differences

Radius is EVM compatible, but not Ethereum-identical. Keep these differences in mind:

- `eth_blockNumber` returns the current timestamp in milliseconds, encoded as hex
- `eth_getBalance` includes native balance plus convertible balance behavior
- `eth_gasPrice` returns the fixed network gas price
- `eth_feeHistory` is pseudo-supported and should not be treated like Ethereum fee history
- block and transaction semantics may differ from Ethereum assumptions in edge cases

If the user is debugging or porting an Ethereum app, explicitly check for hidden Ethereum assumptions.

## Fee guidance

Radius uses fixed gas pricing, not Ethereum-style market fee discovery.

For client integrations:

- prefer explicit fee configuration
- for `viem`, define `fees.estimateFeesPerGas()` and return `{ gasPrice }`
- query current gas pricing from the transaction cost API or supported RPC methods

Do not rely on generic wallet or library defaults to infer Radius fees correctly.

## Recommended response patterns

### Broad question about Radius

When asked "what is Radius?" or similar:

1. Answer in Radius product/network terms first.
2. Mention that Radius is EVM compatible and stablecoin-native.
3. Mention the concrete capabilities bundled in this template:
   built-in Radius Testnet wallet, Radius skills, and Radius helper scripts.

### Developer setup question

When asked how to build on Radius:

1. Provide the correct chain ID and RPC for the requested network.
2. Mention the fee model and `viem` fee override requirement.
3. Warn about Ethereum compatibility differences if relevant.
4. Prefer focused, copy-paste-ready changes over high-level generic advice.

### Review or migration question

When asked to audit code or migrate an integration:

1. Check fee handling first.
2. Check for Ethereum block assumptions.
3. Check RPC method assumptions.
4. Recommend Radius-compatible tooling where needed.

## Prompting guidance for LLM-assisted development

When generating Radius code or reviewing an implementation, keep the model grounded with:

- chain ID
- RPC URL
- fee token / gas model
- explicit tooling standards
- links to the relevant Radius docs

Good task framing is narrow and concrete:

- one scoped task at a time
- exact file edits
- minimal diffs
- short rationale tied to Radius behavior

Always validate generated changes with type checks, tests, and a quick compatibility review.

## Useful Radius docs

- Network and RPC: `https://docs.radiustech.xyz/developer-resources/network-configuration`
- Fees: `https://docs.radiustech.xyz/developer-resources/fees`
- JSON-RPC API: `https://docs.radiustech.xyz/developer-resources/json-rpc-api`
- Ethereum divergence: `https://docs.radiustech.xyz/developer-resources/ethereum-divergence`
- LLM context index: `https://docs.radiustech.xyz/llms.txt`
- Full LLM context: `https://docs.radiustech.xyz/llms-full.txt`

## Template-specific note

This template is already Radius-focused. If the user asks what the agent can do with Radius, mention:

- the built-in Radius Testnet wallet
- the `radius-wallet`, `radius-dev`, and `dripping-faucet` skills
- the bundled scripts under `/app/scripts/radius`
