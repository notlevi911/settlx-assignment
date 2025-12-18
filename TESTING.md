# Testing the Token Due Diligence API

## Required API Keys

Add to your `.env` file:

```bash
# REQUIRED for Contract Truth (EVM chains)
ETHERSCAN_API_KEY=your_etherscan_api_key_here

# REQUIRED for Social Sentiment
CRYPTOPANIC_API_KEY=your_cryptopanic_api_key_here

# REQUIRED for Liquidity Intel (deep pool analysis)
THEGRAPH_API_KEY=your_thegraph_api_key_here

# OPTIONAL (for better Solana support)
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
# Or use Helius (better): https://mainnet.helius-rpc.com/?api-key=YOUR_KEY

# OPTIONAL (for production RPC)
ETHEREUM_RPC_URL=https://eth.llamarpc.com
```

## How to Get API Keys (FREE)

1. **Etherscan**: https://etherscan.io/apis (free tier: 5 calls/sec)
2. **CryptoPanic**: https://cryptopanic.com/developers/api/ (free tier: 100 calls/day)
3. **The Graph**: https://thegraph.com/studio/ (free tier: 100k queries/month)
4. **Helius (Solana)**: https://www.helius.dev/ (free tier: 100k requests/month)

---

## Starting the Server

```bash
# Restart server
pkill -f "uvicorn app.main:app"
cd /Users/levi/Desktop/settlexshi
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Available Endpoints

### 1. Contract Truth Analysis (Multi-Chain) ✅ STRICT SPEC

**Endpoint:** `POST /v1/contracts/truth:analyze`

```bash
curl -X POST http://localhost:8000/v1/contracts/truth:analyze \
  -H "Content-Type: application/json" \
  -d '{
    "token": {
      "symbol": "USDC",
      "name": "USD Coin"
    },
    "instances": [
      {
        "chain": "ethereum",
        "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "type": "erc20"
      },
      {
        "chain": "solana",
        "address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "type": "spl"
      }
    ],
    "lookback_days": 30,
    "options": {
      "compute_code_hash": true,
      "detect_proxy": true,
      "extract_controls": true
    }
  }'
```

**Expected Response (Strict Spec):**
- ✅ `request_id`: UUID
- ✅ `as_of`: ISO timestamp
- ✅ `data.proven.instances[]`: Array with PROVEN facts
  - `verification`: verified_source, explorer, abi_available, source_hash
  - `code_identity`: runtime_code_hash, deployer, creation_tx
  - `upgradeability`: is_proxy, proxy_type, implementation, admin, timelock_detected, upgrade_authority
  - `controls`: owner_or_admin, can_mint, can_burn, can_pause, can_blacklist_or_freeze, fee_controls
  - `supply_activity`: mint/burn events (placeholder)
  - `risk_flags[]`: id, severity, why
- ✅ `data.inferred.cross_chain_equivalence[]`: INFERRED analysis
  - `pair[]`: ["chain:address", "chain:address"]
  - `confidence`: 0-1 score
  - `reasons[]`: Similarity/difference explanations
### 2. Social Sentiment Analysis ✅ STRICT SPEC

**Endpoint:** `POST /v1/social/sentiment:score`

```bash
curl -X POST http://localhost:8000/v1/social/sentiment:score \
  -H "Content-Type: application/json" \
  -d '{
    "asset": {
      "symbol": "BTC",
      "name": "Bitcoin"
    },
    "keywords": ["bitcoin", "btc"],
    "sources": ["news", "x", "reddit"],
    "lookback": {
      "from": "2025-12-17T00:00:00Z",
      "to": "2025-12-18T12:00:00Z"
    },
    "options": {
      "return_top_posts": 20
    }
  }'
```

**Expected Response (Strict Spec):**
- ✅ `request_id`: UUID
- ✅ `as_of`: ISO timestamp
- ✅ `data.sentiment`: score, label, confidence
  - `by_source`: news (ok), x/reddit (unsupported)
- ✅ `data.attention`:
  - `mention_velocity`: per_min, zscore_vs_30d
  - `creator_concentration`: unique_creators, top_10_share
- ✅ `data.influencer_pressure`: score, top_creators[]
- ✅ `data.anomalies[]`: type, severity, details
- ✅ `data.top_posts[]`: text_hash, creator_id, engagement, sentiment_score, sentiment_label
- ✅ `evidence[]`: Provider timestamps
- ✅ `warnings[]`: Non-critical issues
- ✅ `errors[]`: UNSUPPORTED_SOURCE for x and reddit
- ✅ `sentiment.score`: -1 to +1 with confidence
- ✅ `attention.spike_detected`: Boolean with anomaly_score
- ✅ `coordination.suspected_coordination`: Boolean with evidence
- ✅ `by_source[]`: Breakdown per platform (news, x, reddit)
- ✅ `top_posts[]`: Most significant posts (may be empty)
### 3. Liquidity Intelligence ✅ STRICT SPEC

**Endpoint:** `POST /v1/liquidity/intel:snapshot`

```bash
curl -X POST http://localhost:8000/v1/liquidity/intel:snapshot \
  -H "Content-Type: application/json" \
  -d '{
    "asset": {
      "symbol": "WETH"
    },
    "dex": [
      {
        "provider": "dexscreener",
        "chainId": "ethereum",
        "tokenAddress": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
      }
    ],
    "cex": []
  }'
```

**Expected Response (Strict Spec):**
- ✅ `request_id`: UUID
- ✅ `as_of`: ISO timestamp
- ✅ `data.dex[]`: Array of DEX analyses
  - `provider`: dexscreener
  - `chainId`: ethereum, solana, etc.
  - `pairs_found`: Total number of pairs
  - `top_pairs[]`: pair, dex, liquidity_usd, volume_24h_usd, price_usd
  - `flags[]`: dex_liquidity_low, liquidity_concentrated
- ✅ `data.cex[]`: Array of CEX analyses (placeholder - returns nulls + thin_depth flag)
  - `venue`: binance, coinbase, etc.
  - `symbol`: Trading pair
  - `mid_price`: null (not implemented)
  - `spread_bps`: null
  - `depth`: within_10bps_usd, within_25bps_usd, within_50bps_usd (all null)
  - `flags[]`: thin_depth (high severity)
- ✅ `data.liquidity_score`: score (0-1), label (low/medium/high)
- ✅ `evidence[]`: defillama, thegraph, dexscreener providers
- ✅ `warnings[]`: Non-critical issues
- ✅ `errors[]`: Structured errors
- ✅ `price_impacts[]`: Estimated slippage for each trade size (enhanced with The Graph)
- ✅ `liquidity_risk_score`: 0-100 overall risk
- ✅ `risk_flags[]`: HIGH_CONCENTRATION, STALE_LIQUIDITY warnings
- ✅ `errors[]`: Empty (all integrations working with API keys)
- ✅ Deep pool analysis via The Graph Uniswap V3 subgraph queries

---

---

## Quick Validation Tests

```bash
# 1. Check API status
curl http://localhost:8000/

# 2. Test Solana SPL token (native SOL wrapper)
curl -X POST http://localhost:8000/v1/contracts/truth:analyze \
  -H "Content-Type: application/json" \
  -d '{
    "token": {"symbol": "SOL"},
    "instances": [{
      "chain": "solana",
      "address": "So11111111111111111111111111111111111111112",
      "type": "spl"
    }],
    "lookback_days": 7,
    "options": {"fetch_verified_source": true}
  }'

# 3. Test error handling (invalid address)
curl -X POST http://localhost:8000/v1/contracts/truth:analyze \
  -H "Content-Type: application/json" \
  -d '{
    "token": {"symbol": "FAKE"},
## Response Validation Checklist (Strict Spec)

### ✅ All APIs - Common Structure
- ✅ `request_id`: UUID format
- ✅ `as_of`: ISO timestamp (YYYY-MM-DDTHH:MM:SS.ffffff+00:00)
- ✅ `data`: Main response wrapper object
- ✅ `evidence[]`: Array with provider, timestamp, note
- ✅ `warnings[]`: Array of non-critical issue strings
- ✅ `errors[]`: Array with code, message, source, retryable, timestamp

### Contract Truth (`/v1/contracts/truth:analyze`)
- ✅ `data.proven.instances[]`: PROVEN facts from explorers/RPC
  - Each instance: chain, address, type, verification, code_identity, upgradeability, controls, supply_activity, risk_flags
  - `risk_flags[]`: id (MINT_PRIVILEGE, PROXY_UPGRADEABLE, etc.), severity, why
- ✅ `data.inferred.cross_chain_equivalence[]`: INFERRED analysis
  - Each equivalence: pair[], confidence (0-1), reasons[], label
- ✅ Works with EVM (Ethereum, BSC, Polygon) + Solana SPL

### Social Sentiment (`/v1/social/sentiment:score`)
- ✅ `data.sentiment`: score (-1 to +1), label (very_negative → very_positive), confidence, by_source
- ✅ `data.attention`: mention_velocity (per_min, zscore_vs_30d), creator_concentration
- ✅ `data.influencer_pressure`: score, top_creators[]
- ✅ `data.anomalies[]`: type (volume_spike, coordination_signal), severity, details
- ✅ `data.top_posts[]`: text_hash (sha256), creator_id, timestamp, engagement, sentiment_score, sentiment_label
- ✅ News source working via CryptoPanic V2 (20+ sources)
- ✅ X/Reddit/YouTube return UNSUPPORTED_SOURCE errors

### Liquidity Intel (`/v1/liquidity/intel:snapshot`)
- ✅ `data.dex[]`: provider, chainId, pairs_found, top_pairs[], flags[]
  - `top_pairs[]`: pair, dex, liquidity_usd, volume_24h_usd, price_usd
  - `flags[]`: dex_liquidity_low, liquidity_concentrated
- ✅ `data.cex[]`: venue, symbol, mid_price (null), depth (nulls), flags[] (thin_depth)
- ✅ `data.liquidity_score`: score (0-1), label (low/medium/high)
- ✅ Evidence from: dexscreener (pairs), defillama (price), thegraph (Uniswap V3 pools)
- ✅ Works with 8+ chains: Ethereum, Solana, BSC, Polygon, Arbitrum, Avalanche, etc.

### Liquidity Intel (`/v1/liquidity/intel:snapshot`)
- ✅ `dex.hhi_index` Herfindahl concentration
- ✅ `dex.concentration_risk_score` 0-100
- ✅ `dex.top_pools[]` with age_days
- ✅ `dex.turnover_ratio` volume/liquidity
- ✅ `price_impacts[]` for each trade size (DexScreener + The Graph)
- ✅ `liquidity_risk_score` 0-100
- ✅ `risk_flags[]` like HIGH_CONCENTRATION
- ✅ `errors[]` should be empty with proper API keys
- ✅ The Graph queries provide tick-level liquidity distribution

---

## Common Error Codes

- `UPSTREAM_ERROR`: External API failure (retryable)
- `UPSTREAM_TIMEOUT`: Request timeout (retryable)
- `RATE_LIMITED`: Too many requests (retryable)
- `UNSUPPORTED_SOURCE`: Feature not implemented (not retryable)
- `INVALID_REQUEST`: Bad input parameters (not retryable)
- `PARSE_ERROR`: Failed to parse response (retryable)
