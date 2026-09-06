# Independent LLM Blind Review

This was an independent LLM blind review, not a human audit. The prior plan for the user to annotate the CSV was canceled. Historical reports remain archived evidence and may still describe that older plan.

The orchestrating conversation already knew treatments and aggregates. It must not provide reviewer labels. Reviewer.java sends one frozen record at a time to the configured model with no conversation history, tools, scores, version mapping or other records. The same model family as the generator can share biases; stateless requests do not provide human or cross-family validation.

## Inputs and boundaries

- Existing `results/manual-review-blind.csv` is preserved byte-for-byte; its human fields remain blank. No resampling.
- `prepare.py` validates 160 unique IDs, required fields, empty human fields and explicit metadata patterns. It exports only the five allowed fields.
- `freeze.json` binds exact input/rubric bytes. `freeze-pre-newline-correction.json` and `newline-correction.json` document the pre-run Windows LF/CRLF hash correction; the CSV and parsed records were unchanged.
- `check_provenance.py` checks all facts/source messages against the synthetic fixture, checks configured key absence, records endpoint hostname and sample digest without exposing credentials. It never reads the key CSV.
- `Reviewer.java` preserves requests, SSE, usage and failed calls in `results/raw/llm-blind-review-v1/`. Requests are stateless Responses with temperature=0 and max_output_tokens=2048. This differs from the generation model's unset sampling parameters and is not an OLD/NEW treatment change.
- `pacing-amendment.json` records recovery after the first 13 labels and R0014's no-output TPM error. Original source/config snapshots are retained. Existing valid reviews are skipped. Only an existing rate-limit attempt with no output_text delta may be resumed; arbitrary unfinished attempts stop execution. Two attempts per sample remain the bound.
- Pacing uses a conservative character estimate only for scheduling. It is not provider token usage. The label schema retry is disclosed; transport errors do not become FAIL or UNCERTAIN labels.
- `seal.py` requires all 160 review files and hashes them before creating `completed.json`. Only then may `analyze.py` read `manual-review-key.csv`. It validates the seal and original input hashes first.

## Execution (PowerShell, from repository root)

Use Java 21 and a Python 3 runtime. The project API key must already be configured in its existing environment variable; do not put it in command lines or files here.

```powershell
python benchmarks/llm-review-v1/prepare.py
python benchmarks/llm-review-v1/check_provenance.py
javac -encoding UTF-8 -cp build/libs/star-code.jar -d benchmarks/llm-review-v1/classes benchmarks/llm-review-v1/Reviewer.java
java -cp 'benchmarks/llm-review-v1/classes;build/libs/star-code.jar' Reviewer (Join-Path (Get-Location) 'benchmarks')
python benchmarks/llm-review-v1/seal.py
python benchmarks/llm-review-v1/analyze.py
```

The model command is a paid generation step. Offline seal/analysis do not call any model. Never restart a completed study as if it were a new replication; a replication needs a new frozen run namespace. Do not overwrite raw evidence or change failed attempts to success.

Windows restricted Java execution may emit AccessDeniedException even with exit code zero; inspect build logs and use legitimate environment permission approval. A prior batch action was rejected on data destination concerns, then approved after provenance and api.openai.com hostname verification; no alternate transport bypass was used.

## Interpretation

The sample is 160 of 800 candidate records from 4000 fact/view records, stratified by treatment/view/category and score band. It is not 160 independent runs and does not estimate population prevalence without sampling weights/cluster treatment. Summary/effective and forensic failed-output contexts must remain distinguishable.

Raw nominal agreement excludes reviewer UNCERTAIN. Strict maps PASS=1 and PARTIAL/FAIL=0; automatic SUPPORTED=1, other evidence-screen labels=0. Weighted credit is 1 minus absolute score error using PARTIAL=.5; it is not ordinary nominal agreement. Kappa applies to the strict binary labels and is undefined for degenerate marginals. Frozen-v1 exact metrics are diagnostic provenance after the punctuation defect; corrected v2 remains a separately identified supplemental evaluator.
