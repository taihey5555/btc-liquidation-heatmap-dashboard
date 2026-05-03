# BTCUSDT Liquidation Heatmap Backend

FastAPI + SQLite mock backend for the BTCUSDT liquidation heatmap MVP.

This backend returns mock data by default and can optionally collect BTCUSDT public REST market data from Binance USD-M Futures and Bybit V5 linear markets for the live MVP heatmap.

OKX, Gate, MEXC, WebSocket liquidation streams, private APIs, and trading endpoints are not implemented.

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
- `GET /api/heatmap?symbol=BTCUSDT&model=1&currency=USD&range=90d&source=live`
- `GET /api/exchanges/status`
- `GET /api/liquidations/recent`

`source=mock` always returns local mock data.

`source=live` calls Binance and Bybit public REST market data. If one exchange fails, the API continues with the other exchange. If both fail, the response falls back to mock data with `fallback: true` and warnings.

## Test

```bash
pytest backend/tests
```
