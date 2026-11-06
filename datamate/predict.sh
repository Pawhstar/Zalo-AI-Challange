#!/usr/bin/env bash
# Reads the test set mounted at /data and writes /result/submission.jsonl
# plus per-question logs in /result/logs/. Fully offline, deterministic.
#   DATA_DIR / RESULT_DIR override the default paths.
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"
RESULT_DIR="${RESULT_DIR:-/result}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export PYTHONHASHSEED=0
export PYTHONPATH="${HERE}${PYTHONPATH:+:${PYTHONPATH}}"
export PYTHONUTF8=1

mkdir -p "${RESULT_DIR}/logs"
python -m datamate.predict --data "${DATA_DIR}" --out "${RESULT_DIR}"
