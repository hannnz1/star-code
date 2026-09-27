Done — I read all three sources and saved `report.md`.

Unavailable source explicitly noted:
- `http://127.0.0.1:54998/unavailable` returned HTTP 503, so its product details are missing and I did not invent them.
# Product comparison

## Sources read
- `http://127.0.0.1:54998/atlas` — available
- `http://127.0.0.1:54998/birch` — available
- `http://127.0.0.1:54998/unavailable` — unavailable (HTTP 503)

## Comparison

| Product | Price | Project limit | Retention | Export |
|---|---:|---:|---:|---|
| Atlas | 120 USD | 40 projects | 7 days | CSV |
| Birch | 180 USD | 75 projects | 14 days | JSON |
| Unavailable | — | — | — | — |

## Notes
- Atlas is cheaper than Birch by 60 USD.
- Birch allows more projects than Atlas and keeps data longer.
- Atlas exports CSV, while Birch exports JSON.

## Missing information
The `http://127.0.0.1:54998/unavailable` source could not be read because it returned HTTP 503. Its product details are unknown, so no price, project limit, retention, or export format can be compared for that source.

