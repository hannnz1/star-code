# Product comparison

## Sources read
- `http://127.0.0.1:61910/atlas` — available
- `http://127.0.0.1:61910/birch` — available
- `http://127.0.0.1:61910/unavailable` — **unavailable** (HTTP 503)

## Comparison

| Product | Price | Project limit | Retention | Export |
|---|---:|---:|---:|---|
| Atlas | 120 USD | 40 projects | 7 days | CSV |
| Birch | 180 USD | 75 projects | 14 days | JSON |
| Unavailable source | N/A | N/A | N/A | N/A |

## Notes
- Atlas is cheaper than Birch by 60 USD, but Birch allows 35 more projects and twice the retention period.
- Atlas exports CSV, while Birch exports JSON.

## Unavailable source and missing information
- The `http://127.0.0.1:61910/unavailable` source could not be read because the server returned HTTP 503.
- No product details were available from that source, so price, project limit, retention, and export format are unknown.
- I have not inferred or invented any content for the unavailable source.
