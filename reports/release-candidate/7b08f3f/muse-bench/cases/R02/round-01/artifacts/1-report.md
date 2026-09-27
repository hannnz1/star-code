# Product comparison

## Sources read
- `http://127.0.0.1:59302/atlas` — available
- `http://127.0.0.1:59302/birch` — available
- `http://127.0.0.1:59302/unavailable` — unavailable (HTTP 503)

## Comparison

| Product | Price | Project limit | Retention | Export |
|---|---:|---:|---:|---|
| Atlas | 120 USD | 40 projects | 7 days | CSV |
| Birch | 180 USD | 75 projects | 14 days | JSON |

## Notes on the unavailable source
The `http://127.0.0.1:59302/unavailable` source could not be read because it returned HTTP 503. Its product name, price, project limit, retention period, and export format are all missing. No content from that source is available, so nothing further can be compared or inferred from it.
