# Product comparison report

## Sources read
- `http://127.0.0.1:56984/atlas` — available
- `http://127.0.0.1:56984/birch` — available
- `http://127.0.0.1:56984/unavailable` — unavailable (HTTP 503)

## Comparison

| Product | Price | Project limit | Retention | Export |
|---|---:|---:|---:|---|
| Atlas | 120 USD | 40 projects | 7 days | CSV |
| Birch | 180 USD | 75 projects | 14 days | JSON |
| Unavailable | Not available | Not available | Not available | Not available |

## Notes
- Atlas is cheaper than Birch by 60 USD.
- Birch allows 35 more projects than Atlas.
- Birch retains data twice as long as Atlas.
- Atlas exports CSV, while Birch exports JSON.

## Unavailable source
The source `http://127.0.0.1:56984/unavailable` could not be read because it returned HTTP 503. No product details were available from that source, so its price, project limit, retention, and export format are missing and are not inferred here.
