# Exchange Data Notes

All integrations use public market data only. No API keys or trading endpoints are used.

## Data Coverage

| Exchange | Mark/Fair Price | Index Price | Open Interest | Funding Rate | Volume | Order Book | Liquidation Events |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Binance | Yes | Yes | Yes | Yes | Yes | Yes | Public WS `btcusdt@forceOrder` |
| Bybit | Yes | Yes | Yes | Yes | Yes | Yes | Public WS `allLiquidation.BTCUSDT` |
| OKX | Yes | Yes | Yes | Yes | Yes | Yes | Not implemented |
| Gate | Yes | Yes | Yes | Yes | Yes | Yes | Not implemented |
| MEXC | Fair price | Yes when available | Yes | Yes | Yes | Yes | Not implemented |

## Symbol Mapping

| Internal | Binance | Bybit | OKX | Gate | MEXC |
| --- | --- | --- | --- | --- | --- |
| BTCUSDT | BTCUSDT | BTCUSDT | BTC-USDT-SWAP | BTC_USDT | BTC_USDT |

## Open Interest Unit Notes

`open_interest_usd` is used for exchange weights. The safest value is an exchange-provided USD notional. When that is unavailable, the MVP estimates USD notional.

- Binance USD-M BTCUSDT: `openInterest` is treated as BTC/base quantity and approximated as `open_interest * mark_price`.
- Bybit linear BTCUSDT: `openInterestValue` is preferred. If unavailable, `openInterest * mark_price` is used.
- OKX BTC-USDT-SWAP: `oiUsd` is preferred. If unavailable, `oiCcy * mark_price` is used.
- Gate BTC_USDT: `position_size * quanto_multiplier * mark_price` is used as an MVP estimate.
- MEXC BTC_USDT: `holdVol * fair_price` is used as an MVP estimate when contract size is unavailable.

## Guardrails

The backend excludes non-finite, too-small, or extreme `open_interest_usd` values from weight calculation. If all values are unusable, exchange weights fall back to mock proportions for the selected exchanges.

If one exchange dominates the weight above the warning threshold, the heatmap response includes a warning to verify `open_interest_usd` unit handling.
