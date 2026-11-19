#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: bash code/13_run_pilot_calibration_v4.sh {deepseek|zhipu_cn} [--resume] [--dry-run]" >&2
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

lock_file="fulltext/pilot/calibration/pilot_11_manual_case_review_v1.lock.json"
input_file="fulltext/pilot/model_inputs_v5/pilot_model_inputs.jsonl"
prompt_file="config/af_review_prompt_v4.txt"
schema_file="config/af_review_output_schema_v2.json"

[[ -f "$lock_file" && -f "$input_file" && -f "$prompt_file" && -f "$schema_file" ]] || {
  echo "Missing calibration lock, input, prompt, or schema." >&2
  exit 1
}

work_args=()
while IFS= read -r work_id; do
  [[ -n "$work_id" ]] && work_args+=(--work-id "$work_id")
done < <(jq -r '.ordered_work_ids[]' "$lock_file")
[[ ${#work_args[@]} -eq 22 ]] || {
  echo "Calibration lock must contain exactly 11 work IDs." >&2
  exit 1
}

case "$provider" in
  deepseek)
    endpoint="https://api.deepseek.com/chat/completions"
    model="deepseek-v4-flash"
    api_key_env="DEEPSEEK_API_KEY"
    output="fulltext/pilot/model_outputs_v5_protocol_v4/model_a_calibration_11_high_v4.jsonl"
    log="fulltext/logs/model_a_calibration_11_high_v4.log"
    ;;
  zhipu_cn)
    endpoint="https://open.bigmodel.cn/api/paas/v4/chat/completions"
    model="glm-5.3-flash"
    api_key_env="ZHIPU_API_KEY"
    output="fulltext/pilot/model_outputs_v5_protocol_v4/model_b_calibration_11_high_v4.jsonl"
    log="fulltext/logs/model_b_calibration_11_high_v4.log"
    ;;
  *)
    usage
    ;;
esac

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
  --max-api-calls 66
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
