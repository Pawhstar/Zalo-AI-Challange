# DataMate — ZAC 2026 solution

Answers Vietnamese business questions over each shop's CSV / Excel / SQLite
files. Deterministic, rule-based, fully offline: no model weights, no network,
no randomness (re-runs give identical output).

## Run with Docker

```bash
docker build -t datamate:latest .
docker run --rm --network none \
  -v /path/to/private_test:/data:ro \
  -v /path/to/result:/result \
  datamate:latest
```

`/data` must have the test-set layout: `questions.jsonl`, `calendar.csv`,
`rulebook.md`, `data/<business_id>/...`. Output:

- `/result/submission.jsonl` — one line per question, `{"id", "type", "answer"}`;
  `{"id", "type": "abstain"}` when the system is not confident;
  `{"id", "type": "unanswerable", "reason": ...}` when the period lies outside the shop's data.
- `/result/logs/<question id>.json` — question, final answer, route taken
  (`q` = sales/debt/purchase query engines, `e` = legacy keyword router),
  elapsed time, the shop's loading time, traceback if anything failed.
- `/result/logs/run.log` — per-shop loading times and a summary.

## Run without Docker

```bash
pip install -r requirements.txt
DATA_DIR=/path/to/public_test RESULT_DIR=./result ./predict.sh
```

## Layout

| File | Role |
|---|---|
| `datamate/loader.py` | normalises each shop's files into orders / lines / items / stock / payments |
| `datamate/schema.py` | column roles from the README's column descriptions |
| `datamate/periods.py` | time expressions of rulebook §2 |
| `datamate/query.py` | sales questions: filters × measure × answer shape |
| `datamate/debt.py` | customer debt (rulebook §4) |
| `datamate/purchases.py` | purchases (rulebook §5) |
| `datamate/engine.py` | routing and the abstain policy |
| `datamate/predict.py` | inference entry point |
| `datamate/evaluate.py`, `score.py` | train-set evaluation (development only) |
