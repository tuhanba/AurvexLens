# SYNTHETIC — NOT MARKET DATA

Everything in this folder is generated test data. It is never market data and
must never be used for analysis. Snapshots built from it carry
`data_origin = "SYNTHETIC"` and reports carry the label
`SYNTHETIC — NOT MARKET DATA`.

Design (so tests can assert known answers):
- server time rule: `US_DST+2` (server = New York local time + 7 h)
- schedule (New York time): Sun 18:00 open, Fri 17:00 close, daily break 17:00–18:00
  → server time: weekend `Sat 00:00 -> Mon 01:00`, daily break `00:00 -> 01:00`
- period: 2026-02-23 .. 2026-04-10 (covers the US/EU DST divergence weeks of March 2026)
- one injected UNEXPLAINED gap: 2026-03-18 10:00–10:45 server
- one holiday: 2026-04-03 (whole day closed) → HOLIDAY_CANDIDATE
- volatility spike: 2026-03-06 15:30 server (= 08:30 New York)
- bar OHLC built from bid ticks; bar `spread` = spread of the first tick in the bar
