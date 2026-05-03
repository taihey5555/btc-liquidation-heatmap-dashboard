# BTCUSDT Liquidation Heatmap Backend

FastAPI + SQLite mock backend for the BTCUSDT liquidation heatmap MVP.

This backend does not connect to Binance, Bybit, OKX, Gate, MEXC, or any other live exchange API yet. It returns mock data shaped for the existing frontend and keeps future public market-data integration isolated behind exchange stubs.

## Rules

- No real trading functionality.
- No API keys, secrets, credentials, or private endpoints.
- Public APIs only when live market data is introduced later.
- Mock heatmap fallback must remain available.

## Install

```bash
python -m pip install -r backend/requirements.txt
```

## Run

```bash
uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

## Endpoints

- `GET /api/health`
- `GET /api/heatmap?symbol=BTCUSDT&model=1&currency=USD&range=90d`
- `GET /api/exchanges/status`
- `GET /api/liquidations/recent`

## Test

```bash
pytest backend/tests
```
