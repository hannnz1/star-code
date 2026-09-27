# Product comparison report

## Sources read
- `http://127.0.0.1:54998/atlas` — available
- `http://127.0.0.1:54998/birch` — available
- `http://127.0.0.1:54998/unavailable` — **unavailable** (HTTP 503)

## Comparison

| Product | Price | Project limit | Retention | Export |
|---|---:|---:|---:|---|
| Atlas | 120 USD | 40 projects | 7 days | CSV |
| Birch | 180 USD | 75 projects | 14 days | JSON |
| Unavailable source | Missing | Missing | Missing | Missing |

## Notes
- Atlas is cheaper than Birch by 60 USD.
- Birch offers a higher project limit, longer retention, and JSON export.
- The `unavailable` source could not be read, so its product details are not available and are not inferred here.

## Missing information for the unavailable source
- Product name/content beyond the URL path
- Price
- Project limit
- Retention period
- Export format
