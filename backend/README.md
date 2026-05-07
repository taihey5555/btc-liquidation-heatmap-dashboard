# BTCUSDT Liquidation Heatmap Backend

FastAPI + SQLite backend for the BTCUSDT liquidation heatmap MVP.

This backend returns mock data by default and can optionally collect BTCUSDT public REST market data from Binance, Bybit, OKX, Gate, and MEXC for the live MVP heatmap.

Binance and Bybit public liquidation WebSocket streams are supported as a separate job. Private APIs and trading endpoints are not implemented.

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

For VPS deployment, see `docs/DEPLOYMENT.md`.

## Run Liquidation Streams

From the `backend` directory:

```bash
python -m app.jobs.run_liquidation_streams
```

This starts Binance `btcusdt@forceOrder` and Bybit `allLiquidation.BTCUSDT` public WebSocket streams in parallel and stores normalized events in SQLite. No API key is required. There is no trading functionality.

## Run Market Snapshot Collector

From the `backend` directory:

```bash
python -m app.jobs.run_market_collector --symbol BTCUSDT --interval 60
```

This periodically stores public REST `market_snapshots` and derives `oi_delta_buckets` from open-interest increases. Use `--interval 10` for short local checks and `--interval 60` for normal VPS observation. The collector only reads public market data and never sends orders.

## Run Observation Mode

From the `backend` directory:

```bash
python -m app.jobs.run_observation --symbol BTCUSDT --interval 60 --duration-hours 24
python -m app.jobs.generate_observation_report --run-id latest
```

Observation Mode records live heatmap snapshots, fallback state, warnings, cluster events, and anomalies into SQLite. It does not send Telegram notifications and it does not trade.

## Endpoints

- `GET /api/health`
- `GET /api/heatmap?symbol=BTCUSDT&model=1&currency=USD&range=90d`
- `GET /api/heatmap?symbol=BTCUSDT&model=1&currency=USD&range=90d&source=live`
- `GET /api/exchanges/status`
- `GET /api/liquidations/recent?symbol=BTCUSDT&limit=100`
- `GET /api/observation/reports/latest`

`source=mock` always returns local mock data.

`source=live` calls Binance and Bybit public REST market data. If one exchange fails, the API continues with the other exchange. If both fail, the response falls back to mock data with `fallback: true` and warnings.

`/api/liquidations/recent` reads recently stored WebSocket liquidation events. If the stream job is not running or no events have arrived, it returns an empty list.

## Model Data Flow

- Model 1 uses current public REST open interest and a simple leverage bucket distribution.
- Model 2 adds `market_snapshots` history and persisted `oi_delta_buckets`. OI increases are mapped to estimated long or short liquidation zones based on price direction, then decayed by range.
- Model 3 starts from Model 2, adds funding skew, and lightly adjusts buckets using real liquidation events. Executed liquidations can also consume nearby bands so old bright levels fade after they are hit.

Range-specific behavior is intentionally different: 12h/24h uses tighter buckets and shorter OI delta lookback; 3d/7d uses medium aggregation; 30d+ uses longer lookback with stronger time decay.

## Test

```bash
pytest backend/tests
```

## Operational Review Docs

- `docs/MODELS.md`
- `docs/EXCHANGE_DATA_NOTES.md`
- `docs/KNOWN_LIMITATIONS.md`
- `docs/OBSERVATION_MODE.md`
- `docs/DEPLOYMENT.md`
