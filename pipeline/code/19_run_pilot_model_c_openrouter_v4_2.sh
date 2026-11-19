#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: bash code/19_run_pilot_model_c_openrouter_v4_2.sh {core|recommended|expanded} [--smoke] [--resume] [--dry-run]" >&2
  exit 2
}

[[ $# -ge 1 && $# -le 4 ]] || usage
scope="$1"
shift
case "$scope" in
  core|recommended|expanded) ;;
  *) usage ;;
esac

dry_run=false
resume=false
smoke=false
for option in "$@"; do
  case "$option" in
    --dry-run) dry_run=true ;;
    --resume) resume=true ;;
    --smoke) smoke=true ;;
    *) usage ;;
  esac
done

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "$script_dir/.." && pwd)"
cd "$project_root"

merge_lock="fulltext/pilot/calibration/pilot_150_v4_1_merge.lock.json"
model_c_lock="fulltext/pilot/calibration/model_c_openrouter_v4_2.lock.json"
input_file="fulltext/pilot/adjudication_v4_1/pilot_150_model_c_${scope}_inputs.jsonl"
input_meta="fulltext/pilot/adjudication_v4_1/pilot_150_model_c_${scope}_inputs.meta.json"
prompt_file="config/af_review_prompt_v4.txt"
schema_file="config/af_review_output_schema_v2.json"
runner_file="code/08_run_model_review.py"
support_file="code/fulltext_pipeline/model_review_support.py"

for required in "$merge_lock" "$model_c_lock" "$input_file" "$input_meta" "$prompt_file" "$schema_file" "$runner_file" "$support_file"; do
  [[ -f "$required" ]] || { echo "Missing required file: $required" >&2; exit 1; }
done

check_hash() {
  local file="$1"
  local expected="$2"
  local label="$3"
  local actual
  actual="$(shasum -a 256 "$file" | awk '{print $1}')"
  [[ "$actual" == "$expected" ]] || {
    echo "$label SHA-256 differs from its frozen manifest." >&2
    exit 1
  }
}

check_hash "$input_file" "$(jq -r '.input_sha256' "$input_meta")" "Model C input"
check_hash "$merge_lock" "$(jq -r '.base_merge_lock.sha256' "$model_c_lock")" "Base A/B merge lock"
check_hash "$prompt_file" "$(jq -r '.protocol.prompt_sha256' "$model_c_lock")" "Prompt"
check_hash "$schema_file" "$(jq -r '.protocol.schema_sha256' "$model_c_lock")" "Schema"
check_hash "$runner_file" "$(jq -r '.protocol.runner_sha256' "$model_c_lock")" "Runner"
check_hash "$support_file" "$(jq -r '.protocol.support_sha256' "$model_c_lock")" "Validator support"

[[ "$(jq -r '.transport.provider' "$model_c_lock")" == "openrouter" \
  && "$(jq -r '.transport.endpoint' "$model_c_lock")" == "https://openrouter.ai/api/v1/responses" \
  && "$(jq -r '.transport.model' "$model_c_lock")" == "openai/gpt-5.6-luna" \
  && "$(jq -r '.transport.api_style' "$model_c_lock")" == "responses" \
  && "$(jq -r '.transport.reasoning_effort' "$model_c_lock")" == "xhigh" \
  && "$(jq -r '.transport.response_format' "$model_c_lock")" == "json_schema" \
  && "$(jq -r '.transport.router_metadata' "$model_c_lock")" == "true" \
  && "$(jq -r '.transport.remote_schema_explicit_literal_types' "$model_c_lock")" == "true" ]] || {
  echo "Model C OpenRouter v4.2 transport lock is invalid." >&2
  exit 1
}

records="$(jq -r '.records' "$input_meta")"
[[ "$records" =~ ^[0-9]+$ && "$records" -gt 0 ]] || {
  echo "Invalid Model C record count in $input_meta" >&2
  exit 1
}
case "$scope" in
  core) [[ "$records" -eq 35 ]] || { echo "Expected 35 core records" >&2; exit 1; }; max_calls=120 ;;
  recommended) [[ "$records" -eq 69 ]] || { echo "Expected 69 recommended records" >&2; exit 1; }; max_calls=220 ;;
  expanded) [[ "$records" -eq 102 ]] || { echo "Expected 102 expanded records" >&2; exit 1; }; max_calls=320 ;;
esac

output="fulltext/pilot/model_outputs_v5_protocol_v4_2/model_c_${scope}_openrouter_xhigh_v4_2.jsonl"
log="fulltext/logs/model_c_${scope}_openrouter_xhigh_v4_2.log"
scope_args=(--all)
if [[ "$smoke" == true ]]; then
  scope_args=(--limit 5)
  max_calls=20
fi

command=(
  uv run python code/08_run_model_review.py
  --input "$input_file"
  --prompt "$prompt_file"
  --schema "$schema_file"
  --provider openrouter
  --endpoint "https://openrouter.ai/api/v1/responses"
  --api-style responses
  --model openai/gpt-5.6-luna
  --api-key-env OPENROUTER_API_KEY
  --output "$output"
  "${scope_args[@]}"
  --max-api-calls "$max_calls"
  --workers 4
  --timeout 600
  --http-retries 1
  --validation-retries 2
  --max-output-tokens 20000
  --thinking none
  --reasoning-effort xhigh
  --response-format json_schema
)

[[ "$resume" == true ]] && command+=(--resume)

if [[ "$dry_run" == true ]]; then
  "${command[@]}" --dry-run
else
  mkdir -p "$(dirname "$output")" "$(dirname "$log")"
  if [[ "$resume" == true ]]; then
    caffeinate -i "${command[@]}" 2>&1 | tee -a "$log"
  else
    caffeinate -i "${command[@]}" 2>&1 | tee "$log"
  fi
fi
