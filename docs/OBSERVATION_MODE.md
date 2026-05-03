# Observation Mode

Observation Mode records live heatmap behavior before Telegram alerts are introduced.

It does not send Telegram messages, does not place trades, and does not use API keys. It uses the existing public market data and mock fallback paths.

## Run A 24 Hour Observation

From the `backend` directory:

```bash
python -m app.jobs.run_observation --symbol BTCUSDT --interval 60 --duration-hours 24
```

For a short dry run:

```bash
python -m app.jobs.run_observation --symbol BTCUSDT --interval 1 --duration-hours 0.01 --dry-run
```

The job records:
- Model 1, 2, and 3 heatmap snapshots
- exchange weights
- warnings and fallback state
- strong liquidation clusters
- anomalies

## Generate A Report

```bash
python -m app.jobs.generate_observation_report --run-id latest
```

Reports are saved to SQLite in `observation_reports` as JSON and Markdown.

## API

- `GET /api/observation/runs`
- `GET /api/observation/runs/{run_id}`
- `GET /api/observation/reports/latest`
- `GET /api/observation/anomalies?run_id=latest`
- `GET /api/observation/clusters?run_id=latest`

## What To Review

- fallback count
- exchange API failures
- extreme exchange weight concentration
- repeated cluster zones
- max cluster USD
- score and confidence distributions
- Model 1/2/3 differences

## Step 7 Readiness

Telegram notification rules should only be added after at least one observation report shows:
- live source is available most of the time
- fallback events are clearly labeled
- anomaly frequency is understood
- cluster thresholds produce a manageable number of candidates

Telegram alerts must include `source`, `fallback`, and `warnings`.
