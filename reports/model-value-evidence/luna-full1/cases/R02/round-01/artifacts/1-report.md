# Product comparison

| Product | Price | Project limit | Retention | Export |
|---|---:|---:|---:|---|
| Atlas | 120 USD | 40 projects | 7 days | CSV |
| Birch | 180 USD | 75 projects | 14 days | JSON |

## Comparison

Birch costs 60 USD more than Atlas, and offers 35 additional projects, 7 additional days of retention, and JSON export rather than CSV. Atlas is the lower-priced option; Birch has the higher project limit and longer retention. The sources do not specify billing period or other product features, so those cannot be compared.

## Unavailable source

The `/unavailable` source could not be read: it returned HTTP 503. Its product name and all product details—including price, project limit, retention, and export format—are therefore unknown. No content is inferred for that source.

## Sources

- Atlas: [http://127.0.0.1:52609/atlas](http://127.0.0.1:52609/atlas) — read successfully; source ID `92f341089c14457ba6928527af36e3ad`.
- Birch: [http://127.0.0.1:52609/birch](http://127.0.0.1:52609/birch) — read successfully; source ID `a8ba03c04d5c4bf4b69b6a3576f8fa79`.
- Unavailable: [http://127.0.0.1:52609/unavailable](http://127.0.0.1:52609/unavailable) — HTTP 503; no page content available.
