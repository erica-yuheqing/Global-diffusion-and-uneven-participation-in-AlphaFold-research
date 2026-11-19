#!/usr/bin/env bash
set -euo pipefail

mode="${1:-}"
resume_flag=()
if [[ $# -gt 0 ]]; then
  shift
fi
if [[ "${1:-}" == "--resume" ]]; then
  resume_flag=(--resume)
  shift
fi
if [[ $# -ne 0 ]]; then
  echo "Usage: bash code/36_run_production_model_c_openrouter.sh smoke|all [--resume]" >&2
  exit 2
fi

case "$mode" in
  smoke)
    selection=(--limit 5)
    max_calls=30
    ;;
  all)
    selection=(--all)
    max_calls=65000
    ;;
  *)
    echo "Usage: bash code/36_run_production_model_c_openrouter.sh smoke|all [--resume]" >&2
    exit 2
    ;;
esac

input="fulltext/production/adjudication_v1/production_model_c_inputs_v1.jsonl"
meta="fulltext/production/adjudication_v1/production_model_c_inputs_v1.meta.json"
output="fulltext/production/model_outputs_v1/model_c_gpt_5_6_luna_xhigh_v1.jsonl"
log="fulltext/logs/model_c_production_xhigh_v1.log"

if [[ ! -f "$input" || ! -f "$meta" ]]; then
  echo "Model C input is missing. Run code/35_prepare_production_model_c.py first." >&2
  exit 1
fi
expected_sha="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["input_sha256"])' "$meta")"
actual_sha="$(shasum -a 256 "$input" | awk '{print $1}')"
if [[ "$expected_sha" != "$actual_sha" ]]; then
  echo "Model C input SHA-256 does not match its frozen metadata." >&2
  exit 1
fi

mkdir -p "$(dirname "$output")" "$(dirname "$log")"
caffeinate -i uv run python code/08_run_model_review.py \
  --input "$input" \
  --prompt config/af_review_prompt_v4.txt \
  --schema config/af_review_output_schema_v2.json \
  --provider openrouter \
  --endpoint https://openrouter.ai/api/v1/responses \
  --api-style responses \
  --model openai/gpt-5.6-luna \
  --api-key-env OPENROUTER_API_KEY \
  --output "$output" \
  "${selection[@]}" \
  "${resume_flag[@]}" \
  --max-api-calls "$max_calls" \
  --workers 4 \
  --timeout 600 \
  --http-retries 1 \
  --validation-retries 2 \
  --max-output-tokens 20000 \
  --thinking none \
  --reasoning-effort xhigh \
  --response-format json_schema \
  2>&1 | tee -a "$log"
