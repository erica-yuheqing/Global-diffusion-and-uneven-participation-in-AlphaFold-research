#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: bash code/16_run_pilot_repairs_v4_1.sh {deepseek|zhipu_cn} [--resume] [--dry-run]" >&2
  exit 2
}

[[ $# -ge 1 && $# -le 3 ]] || usage
provider="$1"
shift
dry_run=false
resume=false
for option in "$@"; do
  case "$option" in
    --dry-run) dry_run=true ;;
    --resume) resume=true ;;
    *) usage ;;
  esac
done

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "$script_dir/.." && pwd)"
cd "$project_root"

lock_file="fulltext/pilot/calibration/pilot_150_v4_targeted_retry_v4_1.lock.json"
input_file="fulltext/pilot/model_inputs_v5/pilot_model_inputs.jsonl"
prompt_file="config/af_review_prompt_v4.txt"
schema_file="config/af_review_output_schema_v2.json"
support_file="code/fulltext_pipeline/model_review_support.py"
runner_file="code/08_run_model_review.py"

for required in "$lock_file" "$input_file" "$prompt_file" "$schema_file" "$support_file" "$runner_file"; do
  [[ -f "$required" ]] || { echo "Missing required file: $required" >&2; exit 1; }
done

expected_prompt_sha="$(jq -r '.protocol.prompt_sha256' "$lock_file")"
expected_schema_sha="$(jq -r '.protocol.schema_sha256' "$lock_file")"
actual_prompt_sha="$(shasum -a 256 "$prompt_file" | awk '{print $1}')"
actual_schema_sha="$(shasum -a 256 "$schema_file" | awk '{print $1}')"
expected_support_sha="$(jq -r '.protocol.validator_support_sha256' "$lock_file")"
expected_runner_sha="$(jq -r '.protocol.runner_sha256' "$lock_file")"
actual_support_sha="$(shasum -a 256 "$support_file" | awk '{print $1}')"
actual_runner_sha="$(shasum -a 256 "$runner_file" | awk '{print $1}')"
[[ "$actual_prompt_sha" == "$expected_prompt_sha" ]] || {
  echo "Prompt hash differs from the retry lock; create a new protocol version." >&2
  exit 1
}
[[ "$actual_schema_sha" == "$expected_schema_sha" ]] || {
  echo "Schema hash differs from the retry lock; create a new protocol version." >&2
  exit 1
}
[[ "$actual_support_sha" == "$expected_support_sha" ]] || {
  echo "Validator support hash differs from the retry lock; create a new protocol version." >&2
  exit 1
}
[[ "$actual_runner_sha" == "$expected_runner_sha" ]] || {
  echo "Runner hash differs from the retry lock; create a new protocol version." >&2
  exit 1
}

case "$provider" in
  deepseek)
    endpoint="https://api.deepseek.com/chat/completions"
    model="deepseek-v4-flash"
    api_key_env="DEEPSEEK_API_KEY"
    output="fulltext/pilot/model_outputs_v5_protocol_v4_1/model_a_targeted_retry_5_high_v4_1.jsonl"
    log="fulltext/logs/model_a_targeted_retry_5_high_v4_1.log"
    ;;
  zhipu_cn)
    endpoint="https://open.bigmodel.cn/api/paas/v4/chat/completions"
    model="glm-5.3-flash"
    api_key_env="ZHIPU_API_KEY"
    output="fulltext/pilot/model_outputs_v5_protocol_v4_1/model_b_targeted_retry_5_high_v4_1.jsonl"
    log="fulltext/logs/model_b_targeted_retry_5_high_v4_1.log"
    ;;
  *) usage ;;
esac

revalidation_file="$(jq -r --arg provider "$provider" '.models[$provider].local_revalidation_path' "$lock_file")"
expected_revalidation_sha="$(jq -r --arg provider "$provider" '.models[$provider].local_revalidation_sha256' "$lock_file")"
[[ -f "$revalidation_file" ]] || { echo "Missing local revalidation: $revalidation_file" >&2; exit 1; }
actual_revalidation_sha="$(shasum -a 256 "$revalidation_file" | awk '{print $1}')"
[[ "$actual_revalidation_sha" == "$expected_revalidation_sha" ]] || {
  echo "Local revalidation differs from the frozen retry scope; rebuild the lock intentionally." >&2
  exit 1
}

work_args=()
while IFS= read -r work_id; do
  [[ -n "$work_id" ]] && work_args+=(--work-id "$work_id")
done < <(jq -r --arg provider "$provider" '.models[$provider].work_ids[]' "$lock_file")
[[ ${#work_args[@]} -eq 10 ]] || {
  echo "Retry lock must contain exactly 5 work IDs for $provider." >&2
  exit 1
}

command=(
  uv run python code/08_run_model_review.py
  --input "$input_file"
  --prompt "$prompt_file"
  --schema "$schema_file"
  --provider "$provider"
  --endpoint "$endpoint"
  --model "$model"
  --api-key-env "$api_key_env"
  --output "$output"
  "${work_args[@]}"
  --all
  --max-api-calls 30
  --workers 2
  --timeout 600
  --http-retries 1
  --validation-retries 2
  --max-output-tokens 20000
  --thinking enabled
  --reasoning-effort high
  --response-format json_object
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
