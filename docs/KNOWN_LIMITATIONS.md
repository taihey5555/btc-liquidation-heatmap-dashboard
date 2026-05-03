# Known Limitations

## Readiness For Step 7

The MVP is ready to proceed to Telegram notification design, with constraints:
- Notifications should use existing heatmap metadata and warnings.
- Notifications should not imply trade execution.
- Alerts should include fallback/source status so mock fallback is never mistaken for live-only analysis.

## Current Limitations

- Heatmap levels are approximate and based on public market data only.
- The app does not know account leverage, liquidation engines, maintenance margin tiers, or user positions.
- Open interest unit handling varies by exchange and remains an estimation risk.
- Model 2 has placeholder OI delta behavior until more historical snapshots are accumulated and modeled.
- Model 3 uses liquidation events as a small historical activity signal, not a prediction of future liquidation.
- WebSocket liquidation streams are Binance/Bybit only.
- OKX/Gate/MEXC liquidation events are not implemented.
- UI price axis remains USD-oriented; JPY mode changes displayed labels, not the underlying heatmap scale.
- Public endpoints can rate-limit, timeout, or change response shape. Mock fallback must remain enabled.

## Operational Checks

Before enabling alerts:
- Confirm `/api/exchanges/status` returns all five exchanges.
- Confirm `warnings` are included in alert payloads.
- Confirm `fallback: true` suppresses or clearly labels live-data alerts.
- Confirm exchange weights sum to 100% or fallback weights are marked.
