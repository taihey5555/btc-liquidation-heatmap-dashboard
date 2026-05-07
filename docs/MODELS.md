# Heatmap Models

This MVP is a decision-support visualization. It is not a trading system and does not place orders.

## Public-Data Relative Heatmap

This project does not use the CoinGlass paid heatmap API. The live view is a public-data model built from exchange market data such as mark price, open interest, funding, order book availability, and recent liquidation events when the stream job is running.

The raw `long_liq_usd` and `short_liq_usd` values are retained for internal model comparison, but the chart should be interpreted primarily through:
- `relative_intensity`: 0-1 normalized cluster strength
- `total_score`: relative bucket score within the current response
- `confidence`: data quality and freshness confidence
- `dominant_side`: long, short, or balanced

The UI intentionally labels these as estimated relative clusters. They are not CoinGlass values and should not be interpreted as exact liquidation amounts.

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

Model 2 starts from Model 1 and adds open-interest delta evidence from stored `market_snapshots`.

How it works:
- The market collector stores public REST snapshots on a schedule, usually every 10-60 seconds.
- When OI increases, the model treats it as new position buildup.
- If price rises while OI rises, the new OI is treated as probable long buildup, and liquidation zones are projected below current price.
- If price falls while OI rises, the new OI is treated as probable short buildup, and liquidation zones are projected above current price.
- The derived levels are saved as `oi_delta_buckets` with side, price bucket, score, confidence, and source timestamps.
- Model 2 reads those buckets as a range-specific matrix and applies time decay, so newer OI buildup is stronger and older buildup fades.

Range behavior:
- 12h/24h uses tighter buckets and short lookback.
- 3d/7d uses medium aggregation.
- 30d/90d/180d/1y uses longer lookback with decay, so old levels do not stay bright forever.

Fallback behavior:
- If persisted OI delta buckets are unavailable, Model 2 falls back to recent `market_snapshots`.
- If snapshot history is also insufficient, Model 2 remains a conservative Model 1 variant.

Limitations:
- OI delta does not reveal exact entry price, leverage, or side. Price direction is a heuristic.
- Volume is collected but still used lightly.
- The output remains a relative estimated heatmap, not a paid CoinGlass-equivalent feed.

## Model 3: Liquidation Events / Funding Skew Adjustment

Model 3 starts from Model 2 and applies small corrections from:
- funding rate skew
- recent liquidation events, when the WebSocket stream job has saved them
- consumed liquidation bands, where recent executions reduce nearby already-hit zones

Important limitation:
- Recent liquidation events are already executed liquidations, not future liquidation levels. They are intentionally used as a small activity/confidence signal only.

Fallback behavior:
- If liquidation events are unavailable, Model 3 remains a Model 2 variant with funding skew only.
