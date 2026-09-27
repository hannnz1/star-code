# Product Comparison Report

## Sources read
- `http://127.0.0.1:56984/atlas` — available
- `http://127.0.0.1:56984/birch` — available
- `http://127.0.0.1:56984/unavailable` — unavailable (HTTP 503)

## Comparison

| Product | Price | Project limit | Retention | Export |
|---|---:|---:|---:|---|
| Atlas | 120 USD | 40 projects | 7 days | CSV |
| Birch | 180 USD | 75 projects | 14 days | JSON |

## Notes
- Birch costs 60 USD more than Atlas.
- Birch supports 35 more projects than Atlas.
- Birch retains data 7 days longer than Atlas.
- Atlas exports CSV, while Birch exports JSON.

## Unavailable source
The source at `http://127.0.0.1:56984/unavailable` could not be read because it returned HTTP 503.

### Missing information from the unavailable source
Because the source was unavailable, I could not verify any product details from it, such as:
- product name
- price
- project limit
- retention period
- export format

No content from that source has been inferred or invented.