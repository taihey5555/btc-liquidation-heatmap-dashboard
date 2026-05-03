# Heatmap Models

This MVP is a decision-support visualization. It is not a trading system and does not place orders.

## Model 1: Leverage Bucket Simple Model

Model 1 combines public market snapshots from enabled exchanges and estimates liquidation zones from open interest notional.

Assumptions:
- Open interest is distributed across leverage buckets: 5x, 10x, 25x, 50x, 100x.
- Long liquidation prices are estimated below mark price.
- Short liquidation prices are estimated above mark price.
- A small buffer is applied to avoid placing levels exactly at theoretical maintenance-free liquidation prices.

Limitations:
- It does not know actual account margin, entry prices, or maintenance margin.
- It approximates open interest units where exchanges do not directly provide USD notional.
- It is useful for relative clustering, not exact liquidation price prediction.

## Model 2: OI Delta / Volume Adjustment

Model 2 currently starts from Model 1 and applies a light alternating adjustment as a placeholder for future OI delta and volume changes.

Fallback behavior:
- If historical market snapshots are insufficient, Model 2 remains a conservative Model 1 variant.

Limitations:
- True OI delta logic needs a clean time-series baseline.
- Volume is collected but not yet deeply modeled.

## Model 3: Liquidation Events / Funding Skew Adjustment

Model 3 starts from Model 2 and applies small corrections from:
- funding rate skew
- recent liquidation events, when the WebSocket stream job has saved them

Important limitation:
- Recent liquidation events are already executed liquidations, not future liquidation levels. They are intentionally used as a small activity/confidence signal only.

Fallback behavior:
- If liquidation events are unavailable, Model 3 remains a Model 2 variant with funding skew only.
