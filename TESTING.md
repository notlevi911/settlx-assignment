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

### 1. Contract Truth Analysis (Multi-Chain)

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
      "fetch_verified_source": true,
      "fetch_abi_or_idl": true,
      "detect_proxy_or_upgradeability": true,
      "extract_controls": true,
      "compute_code_hash": true
    }
  }'
```

**Expected Response:**
- ✅ `analyses[]` with entry for each chain
- ✅ `proxy_type`: EIP1967_TRANSPARENT, UUPS, or NOT_PROXY
- ✅ `controls`: has_mint, has_pause, ownership_renounced
- ✅ `proven_fields`, `inferred_fields`, `unknown_fields` arrays
- ✅ `cross_chain_consistent`: true/false
- ✅ `cross_chain_notes`: Inconsistency warnings
- ✅ `overall_risk_score`: 0-100
- ✅ `critical_flags`: Array of risk warnings

---

### 2. Social Sentiment Analysis

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
      "return_top_posts": 10,
      "detect_coordination": true
    }
  }'
```

**Expected Response:**
- ✅ `sentiment.score`: -1 to +1 with confidence
- ✅ `attention.spike_detected`: Boolean with anomaly_score
- ✅ `coordination.suspected_coordination`: Boolean with evidence
- ✅ `by_source[]`: Breakdown per platform (news, x, reddit)
- ✅ `top_posts[]`: Most significant posts (may be empty)
- ✅ `errors[]`: UNSUPPORTED_SOURCE for x and reddit
- ✅ News works via CryptoPanic

---

### 3. Liquidity Intelligence

**Endpoint:** `POST /v1/liquidity/intel:snapshot`

```bash
curl -X POST http://localhost:8000/v1/liquidity/intel:snapshot \
  -H "Content-Type: application/json" \
  -d '{
    "asset": {
      "symbol": "WETH",
      "coingecko_id": "weth"
    },
    "dex": [
      {
        "provider": "dexscreener",
        "chainId": "ethereum",
        "tokenAddress": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
      }
    ],
    "trade_sizes_usd": [1000, 10000, 100000],
    "options": {
      "compute_price_impact": true
    }
  }'
```

**Expected Response:**
- ✅ `dex.hhi_index`: Herfindahl concentration (0-1)
- ✅ `dex.concentration_risk_score`: 0-100
- ✅ `dex.top_pools[]`: Array with age_days, liquidity, volume
- ✅ `dex.turnover_ratio`: volume/liquidity metric
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
    "instances": [{
      "chain": "ethereum",
      "address": "0x0000000000000000000000000000000000000000",
      "type": "erc20"
    }],
    "lookback_days": 7
  }'
```

---

## Response Validation Checklist

### Contract Truth (`/v1/contracts/truth:analyze`)
- ✅ `analyses[]` has entry for each chain
- ✅ `proxy_type` enum: EIP1967_TRANSPARENT, UUPS, or NOT_PROXY
- ✅ `controls.has_mint`, `has_pause`, etc. populated
- ✅ `proven_fields`, `inferred_fields`, `unknown_fields` arrays
- ✅ `cross_chain_consistent` boolean
- ✅ `cross_chain_notes` for inconsistencies
- ✅ `errors[]` array with ErrorCode enums
- ✅ `overall_risk_score` 0-100
- ✅ `critical_flags` array

### Social Sentiment (`/v1/social/sentiment:score`)
- ✅ `by_source[]` breakdown (news, x, reddit)
- ✅ `sentiment.score` -1 to +1 with confidence
- ✅ `attention.spike_detected` with anomaly_score
- ✅ `coordination.suspected_coordination` with evidence
- ✅ Structured errors for unsupported sources
- ✅ `evidence[]` with provider timestamps

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
