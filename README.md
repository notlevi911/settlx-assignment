# Token Due Diligence Dashboard - Backend

FastAPI backend providing three intelligence APIs for token due diligence with **strict specification compliance**.

## APIs (All Strict Spec Compliant ✅)

1. **Social Intelligence** (`/v1/social/sentiment:score`) - News sentiment, attention metrics, anomaly detection
2. **Contract Truth** (`/v1/contracts/truth:analyze`) - Multi-chain contract verification with PROVEN/INFERRED separation
3. **Liquidity Intelligence** (`/v1/liquidity/intel:snapshot`) - DEX/CEX liquidity depth with scoring & flags

**All APIs return**: `request_id` (UUID), `as_of` (ISO timestamp), `data` wrapper, `evidence[]`, `warnings[]`, `errors[]`

---

## Quick Start

```bash
# Install
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Configure (add API keys to .env)
cp .env.example .env
# Edit .env with your keys

# Run
uvicorn app.main:app --reload --port 8000

# Test
curl http://localhost:8000/docs
```

---

## API Testing

See **[TESTING.md](TESTING.md)** for detailed test examples and expected responses.

### Quick Test Commands

```bash
# API 1: Social Intelligence (BTC news sentiment)
curl -X POST http://localhost:8000/v1/social/sentiment:score \
  -H "Content-Type: application/json" \
  -d '{"asset":{"symbol":"BTC"},"keywords":["bitcoin"],"lookback":{"from":"2025-12-15T00:00:00Z","to":"2025-12-18T00:00:00Z"},"sources":["news"]}'

# API 2: Contract Truth (Multi-chain USDC)
curl -X POST http://localhost:8000/v1/contracts/truth:analyze \
  -H "Content-Type: application/json" \
  -d '{"token":{"symbol":"USDC"},"instances":[{"chain":"ethereum","address":"0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48","type":"erc20"},{"chain":"solana","address":"EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v","type":"spl"}],"options":{"compute_code_hash":true}}'

# API 3: Liquidity Intelligence (WETH on Ethereum)
curl -X POST http://localhost:8000/v1/liquidity/intel:snapshot \
  -H "Content-Type: application/json" \
  -d '{"asset":{"symbol":"WETH"},"dex":[{"provider":"dexscreener","chainId":"ethereum","tokenAddress":"0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"}],"cex":[]}'
```

---

## API Documentation

### 1. Social Intelligence (Quest 2 - Signal Mode) ✅

**POST** `/v1/social/sentiment:score`

Sentiment analysis from crypto news with attention metrics and anomaly detection.

**Features:**
- ✅ News sentiment from CryptoPanic V2 (20+ sources)
- ✅ Deterministic scoring (-1 to +1) with confidence
- ✅ Sentiment labels: very_negative → very_positive
- ✅ Mention velocity with z-score vs 30-day baseline
- ✅ Influencer pressure (top creators)
- ✅ Anomaly detection (volume spikes, coordination signals)
- ✅ Text deduplication (SHA256 hash)
- ✅ Multi-source support (news working, X/Reddit/YouTube unsupported)

**Test Result:**
```
✅ Status: SUCCESS
   Request ID: 52bdfbee-dc7a-4e...
   Sentiment: neutral (score: 0.0)
   Confidence: 0.28
   Mention velocity: 0.004629/min
   Anomalies: 2
   Top posts: 20
   Errors: 0
```

---

### 2. Contract Truth (Quest 1 - Truth Mode) ✅

**POST** `/v1/contracts/truth:analyze`

Multi-chain contract analysis with PROVEN facts and INFERRED cross-chain analysis.

**Features:**
- ✅ **PROVEN facts** from Etherscan V2 + Solana RPC
- ✅ Multi-chain: EVM (Ethereum, BSC, Polygon) + Solana SPL
- ✅ Contract verification status
- ✅ Code identity (runtime hash, deployer)
- ✅ Upgradeability detection (proxy type, admin, timelock)
- ✅ Controls extraction (mint, burn, pause, freeze, fees)
- ✅ Risk flag generation with severity levels
- ✅ **INFERRED** cross-chain equivalence with confidence scoring

**Test Result:**
```
✅ Status: SUCCESS
   Request ID: b0e8524f-2c6c-41...
   Instances analyzed: 2
   Ethereum verified: True
   Ethereum risk flags: 0
   Solana risk flags: 2
   Cross-chain pairs: 1
   Equivalence: unknown (confidence: 0.43)
   Errors: 0
```

---

### 3. Liquidity Intelligence (Quest 3 - Liquidity Mode) ✅

**POST** `/v1/liquidity/intel:snapshot`

DEX & CEX liquidity depth analysis with scoring and risk flags.

**Features:**
- ✅ DEX integration: DexScreener (8+ chains), The Graph (Uniswap V3), DefiLlama (price)
- ✅ Multi-chain DEX: Ethereum, Solana, BSC, Polygon, Arbitrum, Avalanche
- ✅ Top pairs sorted by liquidity with 24h volume
- ✅ Liquidity scoring: Deterministic 0-1 score (low/medium/high)
- ✅ DEX flags: `dex_liquidity_low`, `liquidity_concentrated`
- ✅ Evidence tracking from multiple providers
- ⚠️ CEX placeholder (returns nulls + `thin_depth` flag)

**Test Result:**
```
✅ Status: SUCCESS
   Request ID: 1d4af071-8249-45...
   DEX pairs found: 8
   Top pair liquidity: $90,822,822
   Liquidity score: 0.85 (high)
   DEX flags: 0
   Evidence sources: 3
   Errors: 0
```

---

## Strict Specification Compliance

All three APIs follow identical structure:

```json
{
  "request_id": "uuid",
  "as_of": "2025-12-18T14:30:00.000000+00:00",
  "data": { /* API-specific structure */ },
  "evidence": [
    {"provider": "etherscan", "timestamp": "...", "note": "..."}
  ],
  "warnings": ["..."],
  "errors": [
    {"code": "UNSUPPORTED_SOURCE", "message": "...", "source": "...", "retryable": false}
  ]
}
```

### Data Classification: PROVEN vs INFERRED

**Contract Truth API** separates data into:

- **`data.proven.instances[]`**: Facts from explorers/RPC
  - Verification status, code hashes
  - Proxy detection, admin addresses
  - Control capabilities
  - Risk flags with severity

- **`data.inferred.cross_chain_equivalence[]`**: Cross-chain analysis
  - Confidence scoring (0-1)
  - Similarity reasons
  - Label: proven_same_asset | likely_same_asset | unknown

**Social & Liquidity APIs**: All data is PROVEN from API providers

---

## Configuration

### Required API Keys

```bash
# .env file
ETHERSCAN_API_KEY=your_key_here
CRYPTOPANIC_API_KEY=your_key_here
THEGRAPH_API_KEY=your_key_here
```

### Get Free API Keys

1. **Etherscan** (EVM verification): https://etherscan.io/apis - 5 calls/sec
2. **CryptoPanic** (news sentiment): https://cryptopanic.com/developers/api/ - 100 calls/day
3. **The Graph** (deep liquidity): https://thegraph.com/studio/ - 100k queries/month

---

## Architecture

```
app/
├── api/v1/
│   ├── endpoints/
│   │   ├── social_sentiment.py      # 542 lines - Quest 2 ✅
│   │   ├── contract_truth.py        # 400+ lines - Quest 1 ✅
│   │   └── liquidity_intel.py       # 340 lines - Quest 3 ✅
│   └── schemas/
│       ├── requests.py              # Pydantic request models
│       └── responses.py             # Strict spec response models
├── services/
│   ├── cryptopanic_client.py        # News API integration
│   ├── contract_truth.py            # Etherscan V2 + RPC
│   ├── solana_client.py             # SPL token analysis
│   ├── dexscreener_client.py        # DEX data
│   ├── defillama_client.py          # Price reference
│   └── thegraph_client.py           # Uniswap V3 pools
└── core/
    ├── enums.py                     # ErrorCode, DataCertainty
    └── config.py                    # Environment settings
```

### Key Design Decisions

1. **Strict Spec Compliance**: All APIs use identical top-level structure
2. **PROVEN vs INFERRED**: Contract Truth separates facts from conclusions
3. **Evidence Tracking**: Every data point traces back to source
4. **Structured Errors**: ErrorCode enum with retryable flag
5. **Deterministic Scoring**: Consistent calculations for reproducibility
6. **Multi-Chain**: Single endpoint handles EVM + Solana

---

## Technology Stack

- **FastAPI 1.0.0**: Modern async API framework
- **Pydantic v2.5.3**: Strict data validation
- **Web3.py 6.15.1**: EVM blockchain interaction
- **httpx**: Async HTTP client
- **base58**: Solana address encoding

### External Integrations

| Provider | Purpose | Status |
|----------|---------|--------|
| Etherscan V2 | EVM contract verification | ✅ Working |
| Solana RPC | SPL token analysis | ✅ Working |
| CryptoPanic V2 | News sentiment | ✅ Working (20 sources) |
| DexScreener | DEX liquidity | ✅ Working (8 chains) |
| The Graph | Uniswap V3 pools | ✅ Working (2 pools queried) |
| DefiLlama | Price reference | ✅ Working ($2945.88 WETH) |

---

## Performance

- **Social Intelligence**: ~2-3 seconds (CryptoPanic fetch)
- **Contract Truth**: ~3-5 seconds per chain (Etherscan + RPC)
- **Liquidity Intelligence**: ~2-4 seconds (DexScreener + The Graph)

---

## Known Limitations

### Social Intelligence
- Only news source implemented (X, Reddit, YouTube marked as unsupported)
- Historical baseline uses mock 30-day average

### Contract Truth
- Supply activity events not yet tracked
- Some chains (Avalanche, Arbitrum) require RPC configuration

### Liquidity Intelligence
- CEX orderbook depth not implemented (returns nulls + flag)
- The Graph queries limited to Uniswap V3 on Ethereum

---

## Development

```bash
# Run tests
pytest

# Format code
black app/

# Type checking
mypy app/

# Run with auto-reload
uvicorn app.main:app --reload --port 8000
```

---

## API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

---

## License

Proprietary - Settlx Technical Assessment

---

## Author

Built for Settlx technical assessment by Levi
