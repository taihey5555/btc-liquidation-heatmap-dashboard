# VPS Deployment

This guide runs the BTCUSDT Liquidation Heatmap MVP on an Ubuntu VPS for 24 to 72 hour observation sessions.

The project is still an observation and visualization tool only. It has no trading endpoints, no order execution, no private exchange API usage, and no Telegram notifications in Step 6.8.

## Target Layout

Use a non-root service user and keep the project under `/opt`.

```bash
sudo adduser --system --group --home /opt/btc-liquidation-heatmap-dashboard btcmap
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip nodejs npm tmux curl
sudo git clone https://github.com/taihey5555/btc-liquidation-heatmap-dashboard.git /opt/btc-liquidation-heatmap-dashboard
sudo chown -R btcmap:btcmap /opt/btc-liquidation-heatmap-dashboard
cd /opt/btc-liquidation-heatmap-dashboard
```

If your Ubuntu package repository provides an old Node.js, install an LTS Node.js release from your preferred trusted source before running `npm install`.

## Environment

Create a private `.env` from the tracked template.

```bash
sudo -u btcmap cp .env.example .env
sudo -u btcmap nano .env
chmod 600 .env
```

Minimum VPS values:

```bash
BTC_HEATMAP_DATABASE_PATH=/opt/btc-liquidation-heatmap-dashboard/backend/heatmap.db
BTC_HEATMAP_CORS_ORIGINS=http://127.0.0.1:3000,http://localhost:3000
BTC_HEATMAP_ENABLED_EXCHANGES=binance,bybit,okx,gate,mexc
BTC_HEATMAP_OBSERVATION_INTERVAL_SECONDS=60
BTC_HEATMAP_OBSERVATION_DURATION_HOURS=24
BTC_HEATMAP_TELEGRAM_ENABLED=false
NEXT_PUBLIC_HEATMAP_API_BASE=http://127.0.0.1:8000
PORT=3000
```

Do not commit `.env`. API keys are not required. Telegram variables are intentionally disabled until the notification step.

## Backend Setup

```bash
cd /opt/btc-liquidation-heatmap-dashboard
sudo -u btcmap python3 -m venv backend/.venv
sudo -u btcmap backend/.venv/bin/python -m pip install --upgrade pip
sudo -u btcmap backend/.venv/bin/python -m pip install -r backend/requirements.txt
```

Start FastAPI manually:

```bash
sudo -u btcmap backend/.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Health checks:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/exchanges/status
curl http://127.0.0.1:8000/api/observation/reports/latest
```

`/api/observation/reports/latest` can return `null` before the first report is generated.

## Frontend Setup

```bash
cd /opt/btc-liquidation-heatmap-dashboard
sudo -u btcmap npm install
sudo -u btcmap npm run build
sudo -u btcmap npx next start --hostname 127.0.0.1 --port 3000
```

If the UI is exposed outside the VPS, put Nginx or another reverse proxy in front of it and avoid exposing the FastAPI port directly.

## Observation Mode

Run a 24 hour observation:

```bash
cd /opt/btc-liquidation-heatmap-dashboard/backend
sudo -u btcmap ../backend/.venv/bin/python -m app.jobs.run_observation --symbol BTCUSDT --interval 60 --duration-hours 24
```

Run a 72 hour observation:

```bash
cd /opt/btc-liquidation-heatmap-dashboard/backend
sudo -u btcmap ../backend/.venv/bin/python -m app.jobs.run_observation --symbol BTCUSDT --interval 60 --duration-hours 72
```

Generate the latest report:

```bash
cd /opt/btc-liquidation-heatmap-dashboard/backend
sudo -u btcmap ../backend/.venv/bin/python -m app.jobs.generate_observation_report --run-id latest
curl http://127.0.0.1:8000/api/observation/reports/latest
```

Observation Mode records live heatmap snapshots, cluster events, fallback state, warnings, and anomalies in SQLite. It does not send notifications.

## tmux Operation

Create a tmux session:

```bash
tmux new -s btc-heatmap
```

Backend pane:

```bash
cd /opt/btc-liquidation-heatmap-dashboard
source backend/.venv/bin/activate
uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

Create another pane with `Ctrl+b`, then `%`, and start the frontend:

```bash
cd /opt/btc-liquidation-heatmap-dashboard
npx next start --hostname 127.0.0.1 --port 3000
```

Create another pane and start Observation Mode:

```bash
cd /opt/btc-liquidation-heatmap-dashboard/backend
source .venv/bin/activate
python -m app.jobs.run_observation --symbol BTCUSDT --interval 60 --duration-hours 24
```

Detach with `Ctrl+b`, then `d`.

Attach again:

```bash
tmux attach -t btc-heatmap
```

List sessions:

```bash
tmux ls
```

Stop a session:

```bash
tmux kill-session -t btc-heatmap
```

## systemd Operation

Template service files are in `deploy/systemd`.

Install them:

```bash
sudo cp deploy/systemd/btc-heatmap-backend.service /etc/systemd/system/
sudo cp deploy/systemd/btc-heatmap-frontend.service /etc/systemd/system/
sudo cp deploy/systemd/btc-heatmap-observation.service /etc/systemd/system/
sudo systemctl daemon-reload
```

Start and enable:

```bash
sudo systemctl enable --now btc-heatmap-backend.service
sudo systemctl enable --now btc-heatmap-frontend.service
sudo systemctl enable --now btc-heatmap-observation.service
```

Check status:

```bash
sudo systemctl status btc-heatmap-backend.service
sudo systemctl status btc-heatmap-frontend.service
sudo systemctl status btc-heatmap-observation.service
```

Read logs:

```bash
journalctl -u btc-heatmap-backend.service -f
journalctl -u btc-heatmap-frontend.service -f
journalctl -u btc-heatmap-observation.service -f
```

To run a 72 hour observation under systemd, edit `btc-heatmap-observation.service` and change `--duration-hours 24` to `--duration-hours 72`, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl restart btc-heatmap-observation.service
```

## Safety Notes

- Keep `.env` out of git. Only `.env.example` is tracked.
- Do not add exchange API keys; the MVP uses public market data only.
- Do not expose FastAPI directly to the internet unless you add access controls.
- Prefer SSH keys and disable password SSH login where possible.
- Use a firewall and open only required ports, typically SSH and your reverse proxy port.
- Start with local-only binding on `127.0.0.1` and access through SSH port forwarding or a protected reverse proxy.
- Back up `backend/heatmap.db` before deleting or rebuilding the VPS.
- Telegram notification settings are intentionally absent until Step 7.

Example firewall baseline:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```

## Verification Before a 24h Run

```bash
cd /opt/btc-liquidation-heatmap-dashboard/backend
../backend/.venv/bin/pytest

cd /opt/btc-liquidation-heatmap-dashboard
npm run build
npm run lint

curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/exchanges/status
curl "http://127.0.0.1:8000/api/heatmap?symbol=BTCUSDT&model=1&currency=USD&range=90d&source=live"
```

If live exchange calls fail, the API should continue with successful exchanges or return mock fallback metadata. That behavior is expected and must remain intact.
