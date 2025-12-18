# Token Due Diligence Engine

FastAPI backend for crypto token risk assessment. Analyzes contracts, social sentiment, and liquidity across multiple blockchains.

## Architecture

Three analysis streams:
- **Contract Truth**: On-chain safety verification (Ethereum, Solana, BSC, Polygon)
- **Social Sentiment**: Narrative and attention metrics via news aggregation
- **Liquidity Intelligence**: DEX concentration and slippage estimation

All data classified as PROVEN, INFERRED, or UNKNOWN with evidence tracking.

## Prerequisites

- Python 3.9+
- API Keys (free tiers):
  - Etherscan: https://etherscan.io/apis (5 calls/sec)
  - CryptoPanic: https://cryptopanic.com/developers/api/ (100 calls/day)
  - The Graph: https://thegraph.com/studio/ (100k queries/month free)

## Installation

```bash
# Clone repository
cd /Users/levi/Desktop/settlexshi

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Create `.env` file in project root:

```bash
# Required
ETHERSCAN_API_KEY=your_etherscan_key
CRYPTOPANIC_API_KEY=your_cryptopanic_key
THEGRAPH_API_KEY=your_thegraph_key

# Optional (defaults provided)
ETHEREUM_RPC_URL=https://eth.llamarpc.com
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
```

### How to Get API Keys

**Etherscan** (required for EVM contract verification):
1. Visit https://etherscan.io/apis
2. Sign up and create API key
3. Free tier: 5 calls/sec

**CryptoPanic** (required for social sentiment):
1. Visit https://cryptopanic.com/developers/api/
2. Register for developer account
3. Free tier: 100 calls/day

**The Graph** (required for deep liquidity analysis):
1. Visit https://thegraph.com/studio/
2. Sign in with wallet or email
3. Go to "API Keys" section
4. Create new API key
5. Free tier: 100k queries/month

## Running the Server

```bash
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API documentation available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API Endpoints

### 1. Contract Truth Analysis

**POST /v1/contracts/truth:analyze**

Analyzes smart contract safety across multiple chains.

Request:
```json
{
  "token": {"symbol": "USDC", "name": "USD Coin"},
  "instances": [
    {"chain": "ethereum", "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "type": "erc20"},
    {"chain": "solana", "address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "type": "spl"}
  ],
  "lookback_days": 30,
  "options": {
    "fetch_verified_source": true,
    "extract_controls": true,
    "detect_proxy_or_upgradeability": true
  }
}
```

Response includes:
- Verification status per chain
- Proxy type detection (EIP1967_TRANSPARENT, UUPS, NOT_PROXY)
- Admin controls (mint, pause, freeze, burn)
- Cross-chain consistency checks
- Overall risk score (0-100)

### 2. Social Sentiment Scoring

**POST /v1/social/sentiment:score**

Analyzes social narrative and attention metrics.

Request:
```json
{
  "asset": {"symbol": "BTC", "name": "Bitcoin"},
  "keywords": ["bitcoin", "btc"],
  "sources": ["news"],
  "lookback": {
    "from": "2025-12-17T00:00:00Z",
    "to": "2025-12-18T12:00:00Z"
  },
  "options": {"return_top_posts": 10}
}
```

Response includes:
- Sentiment score (-1 to +1) with confidence
- Attention spike detection
- Coordination risk assessment
- Per-source breakdown
- Top keywords

### 3. Liquidity Intelligence

**POST /v1/liquidity/intel:snapshot**

Analyzes DEX liquidity concentration and slippage.

Request:
```json
{
  "asset": {"symbol": "WETH", "coingecko_id": "weth"},
  "dex": [{
    "provider": "dexscreener",
    "chainId": "ethereum",
    "tokenAddress": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
  }],
  "trade_sizes_usd": [1000, 10000, 100000],
  "options": {"compute_price_impact": true}
}
```

Response includes:
- HHI concentration index
- Pool age distribution
- Price impact estimates (enhanced with The Graph tick data)
- Turnover ratios
- Risk flags (HIGH_CONCENTRATION, STALE_LIQUIDITY)
- Deep pool math via The Graph Uniswap V3 queries

## Project Structure

```
settlexshi/
├── app/
│   ├── main.py                    # FastAPI application entry
│   ├── api/
│   │   └── v1/
│   │       ├── api.py             # API router
│   │       ├── endpoints/         # Endpoint handlers
│   │       │   ├── contract_truth.py
│   │       │   ├── social_sentiment.py
│   │       │   └── liquidity_intel.py
│   │       └── schemas/           # Request/response models
│   │           ├── requests.py
│   │           └── responses.py
│   ├── services/                  # Business logic
│   │   ├── contract_truth.py
│   │   ├── social_intel.py
│   │   ├── liquidity_intel.py
│   │   ├── etherscan_client.py
│   │   ├── solana_client.py
│   │   ├── cryptopanic_client.py
│   │   ├── dexscreener_client.py
│   │   ├── defillama_client.py
│   │   └── thegraph_client.py
│   └── core/
│       ├── config.py              # Settings management
│       └── models.py              # Core data models
├── requirements.txt
├── .env                           # API keys (not in git)
├── TESTING.md                     # Test examples
└── README.md
```

## Error Handling

All endpoints return structured errors with codes:
- `UPSTREAM_ERROR`: External API failure (retryable)
- `UPSTREAM_TIMEOUT`: Request timeout (retryable)
- `RATE_LIMITED`: Too many requests (retryable)
- `UNSUPPORTED_SOURCE`: Feature not implemented (not retryable)
- `INVALID_REQUEST`: Bad input parameters (not retryable)
- `PARSE_ERROR`: Failed to parse response (retryable)

## Data Classification

Every field is classified as:
- **PROVEN**: Verified on-chain or from authoritative source
- **INFERRED**: Calculated heuristic or derived metric
- **UNKNOWN**: Insufficient data or unavailable

Example response:
```json
{
  "is_verified": true,
  "proxy_type": "NOT_PROXY",
  "current_supply": 2576345.09,
  "proven_fields": ["is_verified", "proxy_type", "current_supply"],
  "inferred_fields": [],
  "unknown_fields": ["supply_change_24h_pct"]
}
```

## Testing

See `TESTING.md` for detailed test examples and validation checklists.

Quick health check:
```bash
curl http://localhost:8000/
```

## Supported Chains

### Contract Analysis
- Ethereum (ERC20)
- Binance Smart Chain (BEP20)
- Polygon (ERC20)
- Arbitrum (ERC20)
- Optimism (ERC20)
- Solana (SPL)

### Proxy Detection
- EIP-1967 (Transparent + UUPS)
- EIP-1822 (Universal Upgradeable Proxy)
- OpenZeppelin patterns

### Social Sources
- CryptoPanic News (implemented)
- X/Twitter (placeholder)
- Reddit (placeholder)

### Liquidity Providers
- DexScreener (implemented)
- The Graph / Uniswap V3 (implemented)
- DefiLlama CEX (placeholder)

## Development

Run with auto-reload:
```bash
uvicorn app.main:app --reload
```

Check logs for upstream errors and retryable failures.

## License

Internal use only.
