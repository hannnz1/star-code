# Product comparison report

## Sources read
- `http://127.0.0.1:53188/atlas` — available and read successfully.
- `http://127.0.0.1:53188/birch` — available and read successfully.
- `http://127.0.0.1:53188/unavailable` — unavailable; the source returned HTTP 503 and no content was provided.

## Comparison
| Product | Price | Project limit | Retention | Export |
|---|---:|---:|---:|---|
| Atlas | 120 USD | 40 projects | 7 days | CSV |
| Birch | 180 USD | 75 projects | 14 days | JSON |

## Notes
- Atlas is cheaper than Birch by 60 USD.
- Birch supports more projects than Atlas by 35 projects.
- Birch retains data longer than Atlas by 7 days.
- Atlas exports CSV, while Birch exports JSON.

## Missing information
- The unavailable source at `http://127.0.0.1:53188/unavailable` could not be read, so its product details, price, limits, retention, and export format are unknown.
- No other missing information was encountered for the two readable sources.
