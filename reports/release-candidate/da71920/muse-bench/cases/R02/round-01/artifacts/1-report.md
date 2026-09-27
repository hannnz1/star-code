# Product comparison report

## Sources read
- `http://127.0.0.1:53188/atlas` — available
- `http://127.0.0.1:53188/birch` — available
- `http://127.0.0.1:53188/unavailable` — unavailable (HTTP 503)

## Comparison

| Product | Price | Project limit | Retention | Export |
|---|---:|---:|---:|---|
| Atlas | 120 USD | 40 projects | 7 days | CSV |
| Birch | 180 USD | 75 projects | 14 days | JSON |
| Unavailable | N/A | N/A | N/A | N/A |

## Notes

- Atlas is cheaper than Birch by 60 USD.
- Birch allows more projects than Atlas (75 vs 40).
- Birch retains data longer than Atlas (14 days vs 7 days).
- Atlas exports CSV, while Birch exports JSON.

## Unavailable source and missing information

The source `http://127.0.0.1:53188/unavailable` could not be read because it returned HTTP 503.

Missing information from that source:
- product name, if any
- price
- project limit
- retention period
- export format

I did not infer or invent any content for the unavailable source.