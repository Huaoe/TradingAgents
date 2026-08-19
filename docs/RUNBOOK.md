# Hyperliquid Trading Agent — Local Runbook

This runbook explains how to install, run, and stop the app locally for personal paper/live trading.

## Prerequisites

- Python 3.10+
- Node.js 20+
- Git
- (Optional) Docker + Docker Compose for containerized launch

## 1. Clone and install

```bash
git clone https://github.com/Huaoe/TradingAgents.git
cd TradingAgents

# Install the engine package (required by the backend)
pip install -e engine/

# Install the app backend (with dev tools)
pip install -e "app/[dev]"

cd app/frontend
npm install
```

## 2. Configure environment

Copy the root `.env.example` to `.env` and fill in the providers you use:

```bash
cp .env.example .env
```

Set at least one LLM key if you want real `TradingAgentsGraph` signal generation, e.g.:

```bash
OPENAI_API_KEY=sk-...
```

The app defaults to a deterministic signal engine when no LLM key is set, which is fine for paper-trade testing.

Optional trading safety variables:

```bash
# Disable live trading by default; only set to true when you intend real orders.
LIVE_TRADING=false

# Select the network used consistently for market data and order execution.
# The default is mainnet for complete market data; live orders remain gated below.
# Set this to testnet to use testnet for both data and execution.
HYPERLIQUID_NETWORK=mainnet
```

## 3. Run in development

Two terminals are needed:

**Terminal 1 — backend:**

```bash
cd app
python -m backend.main
```

The FastAPI server starts at `http://localhost:8000`.

**Terminal 2 — frontend:**

```bash
cd app/frontend
npm run dev
```

The Vite dev server starts at `http://localhost:5173` and proxies `/api` to the backend.

Open `http://localhost:5173` in your browser.

## 4. First-time setup

1. Go to **Wallets** and add one or more Hyperliquid wallets. You can add a paper/test wallet with a dummy address and private key for testing.
2. Select an active wallet from the sidebar.
3. Go to **Scanner**, pick a symbol, and click **Analyze** to generate your first signal.
4. Accept the signal on the **Signals** page — it will execute a paper trade.
5. View the position on **Positions** and the portfolio summary on the **Dashboard**.

## 5. Run with Docker

Build and start the combined web image from the repository root:

```bash
docker compose -f app/docker-compose.web.yml up --build -d
```

The app is then available at `http://localhost:8000` (backend serves the built frontend).

Stop:

```bash
docker compose -f app/docker-compose.web.yml down
```

## 6. Important safety reminders

- The app starts in **paper mode**. No real orders are sent.
- Live trading requires all of the following: `LIVE_TRADING=true`, the wallet's
  **live trading** switch enabled from the Portfolio UI/API, and `mode=live` on
  the trade request. Both gates are checked for every live open and close; an
  error identifies the gate that is off.
- Market data and execution use the same `HYPERLIQUID_NETWORK` setting. The
  backend defaults to `mainnet` for data, and the Dashboard displays the active
  network. Set `HYPERLIQUID_NETWORK=testnet` to switch both data and execution
  to testnet.
- Before mainnet trading, fund the Hyperliquid mainnet account with USDC
  bridged via Arbitrum. Execution supports an approved Hyperliquid API agent
  wallet because it passes `account_address=wallet.address` to the SDK.
- For live opens, the app updates the asset leverage on Hyperliquid immediately
  before submitting the market order. The requested leverage is clamped to the
  market's `maxLeverage`; a rejected leverage update aborts the order.
- Never commit `.env`, wallet private keys, or `app/backend/data/*` to Git.
- Test with small size for at least 7 days in paper mode before moving real capital.

## 7. Lint and test

```bash
# Python linting
ruff check app/backend
ruff format app/backend

# Backend tests
pytest app/backend/tests

# Frontend build and lint
cd app/frontend
npm run build
npm run lint
```

## 8. Troubleshooting

- **Port 8000 already in use:** set `PORT=8001` and update `app/frontend/.env` (`VITE_API_URL=http://localhost:8001`).
- **No signals appearing:** check that at least one LLM key is set or rely on the deterministic engine; verify `cd app && python -m backend.main` is running.
- **Database errors:** delete `app/backend/data/*.db` files to reset state (this loses paper positions/alerts).
