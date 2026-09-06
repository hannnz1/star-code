# Fact category analysis

These are forensic evidence-screen counts across all analyzable outputs, not human-confirmed loss. `lost_count` in CSV is null pending human review. Each fact's precise evidence and origin are saved in its raw run's forensics/fact-judgments.json. Architectural decisions and real tool-result semantics are not represented as independent categories in this 50-fact fixture; no coverage claim is made for them.

| Arm | Category | View | Supported | Distorted | Conflict | Unverified | Supported % |
|---|---|---|---:|---:|---:|---:|---:|
| old | api | summary | 49 | 0 | 0 | 51 | 49.00 |
| old | api | effective | 49 | 0 | 0 | 51 | 49.00 |
| old | cause | summary | 93 | 0 | 0 | 7 | 93.00 |
| old | cause | effective | 94 | 0 | 0 | 6 | 94.00 |
| old | class | summary | 39 | 0 | 0 | 1 | 97.50 |
| old | class | effective | 39 | 0 | 0 | 1 | 97.50 |
| old | constraint | summary | 91 | 0 | 0 | 9 | 91.00 |
| old | constraint | effective | 91 | 0 | 0 | 9 | 91.00 |
| old | failed_attempt | summary | 86 | 0 | 0 | 14 | 86.00 |
| old | failed_attempt | effective | 89 | 0 | 0 | 11 | 89.00 |
| old | file | summary | 95 | 0 | 0 | 5 | 95.00 |
| old | file | effective | 95 | 0 | 0 | 5 | 95.00 |
| old | method | summary | 39 | 0 | 0 | 1 | 97.50 |
| old | method | effective | 39 | 0 | 0 | 1 | 97.50 |
| old | negative | summary | 87 | 0 | 0 | 13 | 87.00 |
| old | negative | effective | 88 | 0 | 0 | 12 | 88.00 |
| old | next | summary | 96 | 0 | 0 | 4 | 96.00 |
| old | next | effective | 96 | 0 | 0 | 4 | 96.00 |
| old | number | summary | 90 | 0 | 0 | 10 | 90.00 |
| old | number | effective | 90 | 0 | 0 | 10 | 90.00 |
| old | package | summary | 19 | 0 | 0 | 1 | 95.00 |
| old | package | effective | 19 | 0 | 0 | 1 | 95.00 |
| old | pending | summary | 93 | 0 | 0 | 7 | 93.00 |
| old | pending | effective | 94 | 0 | 0 | 6 | 94.00 |
| new | api | summary | 61 | 0 | 0 | 39 | 61.00 |
| new | api | effective | 61 | 0 | 0 | 39 | 61.00 |
| new | cause | summary | 89 | 0 | 0 | 11 | 89.00 |
| new | cause | effective | 89 | 0 | 0 | 11 | 89.00 |
| new | class | summary | 36 | 0 | 0 | 4 | 90.00 |
| new | class | effective | 36 | 0 | 0 | 4 | 90.00 |
| new | constraint | summary | 92 | 0 | 0 | 8 | 92.00 |
| new | constraint | effective | 92 | 0 | 0 | 8 | 92.00 |
| new | failed_attempt | summary | 92 | 0 | 0 | 8 | 92.00 |
| new | failed_attempt | effective | 92 | 0 | 0 | 8 | 92.00 |
| new | file | summary | 86 | 0 | 0 | 14 | 86.00 |
| new | file | effective | 86 | 0 | 0 | 14 | 86.00 |
| new | method | summary | 35 | 0 | 0 | 5 | 87.50 |
| new | method | effective | 35 | 0 | 0 | 5 | 87.50 |
| new | negative | summary | 84 | 0 | 0 | 16 | 84.00 |
| new | negative | effective | 84 | 0 | 0 | 16 | 84.00 |
| new | next | summary | 93 | 0 | 0 | 7 | 93.00 |
| new | next | effective | 93 | 0 | 0 | 7 | 93.00 |
| new | number | summary | 94 | 0 | 0 | 6 | 94.00 |
| new | number | effective | 94 | 0 | 0 | 6 | 94.00 |
| new | package | summary | 17 | 0 | 0 | 3 | 85.00 |
| new | package | effective | 17 | 0 | 0 | 3 | 85.00 |
| new | pending | summary | 86 | 0 | 0 | 14 | 86.00 |
| new | pending | effective | 86 | 0 | 0 | 14 | 86.00 |

Do not rank unverified categories as confirmed regression. Inspect the human sample and compare OLD/NEW on the same meaning after evaluator validation.
