#!/usr/bin/env bash
# Queue the HiPerGator run chain (D11 Llama models) as one chain of SLURM jobs.
#
#   scripts/slurm/submit_all.sh --dry-run      # print every sbatch command, submit nothing
#   scripts/slurm/submit_all.sh --smoke-only   # only the two smoke tests (Llama 1B LoRA, Llama 8B QLoRA)
#   scripts/slurm/submit_all.sh                # smoke tests, then everything else once they pass
#   scripts/slurm/submit_all.sh --only llama1b_lora_ep1_age4_hpg   # one run on its own (train -> evaluate)
#
# The chain (models: Llama-3.2-1B and -3B with LoRA in bf16, Llama-3.1-8B with QLoRA in 4-bit; see DECISIONS.md D11):
#   1. Smoke:   1B LoRA smoke and 8B QLoRA smoke, each trained then evaluated.
#   2. After both smoke evals succeed (--dependency=afterok), in parallel:
#        Phase 0  six baselines (evaluation only, no training): 1B, 3B, 8B-in-4-bit x default/strong prompt
#        Phase 1  Llama-1B LoRA ep1 and Llama-3B LoRA ep1 (the run-3 recipe); each train -> evaluate
#        Phase 2  Llama-8B QLoRA ep1; train -> evaluate
#        Phase 3  the same three on the age-4 bucket; each train -> evaluate
# The Qwen and SmolLM2 configs in configs/hpg/ are the record of past runs and are not in the chain. Qwen must never
# be run on HiPerGator (POLICIES.md). Every config's model (and adapter base model) goes through
# src/utils/model_policy.py before anything is queued; a prohibited model stops the whole submission.
# Every run writes to experiments/<stamp>_<run_name>/ (SLURM logs as slurm-<kind>-<jobid>.out there too).
#
# Options:
#   --dry-run          print the sbatch commands with placeholder job ids (JOB_1, JOB_2, ...)
#   --smoke-only       submit only the smoke stage
#   --only RUN_NAME    submit just the config whose run_name is RUN_NAME, with no smoke gate:
#                      train -> evaluate for a training config, a single eval job for a Phase 0 baseline
#   --stamp STAMP      run-id prefix (default: current YYYYMMDD-HHMM)
#   --env-file FILE    settings file (default: scripts/slurm/hpg.env, or $HPG_ENV_FILE)
# Environment: PYTHON (default python3) runs the model-policy check; it needs only the standard library.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

DRY_RUN=0
SMOKE_ONLY=0
ONLY=""
STAMP="$(date +%Y%m%d-%H%M)"
ENV_FILE="${HPG_ENV_FILE:-scripts/slurm/hpg.env}"
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --smoke-only) SMOKE_ONLY=1 ;;
    --only) ONLY="${2:?--only needs a run_name}"; shift ;;
    --stamp) STAMP="${2:?--stamp needs a value}"; shift ;;
    --env-file) ENV_FILE="${2:?--env-file needs a value}"; shift ;;
    -h|--help) sed -n '2,29p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
if [ -n "$ONLY" ] && [ "$SMOKE_ONLY" = 1 ]; then
  echo "error: --only and --smoke-only can't be combined" >&2; exit 2
fi

# ---- Job lists (config paths relative to the repo root) ----
SMOKE_TRAIN=(
  configs/hpg/phase1/llama1b_lora_smoke_hpg.yaml
  configs/hpg/phase2/llama8b_qlora_smoke_hpg.yaml
)
PHASE0_EVAL=(
  configs/hpg/phase0/llama1b_base-default_hpg.yaml
  configs/hpg/phase0/llama1b_base-strong_hpg.yaml
  configs/hpg/phase0/llama3b_base-default_hpg.yaml
  configs/hpg/phase0/llama3b_base-strong_hpg.yaml
  configs/hpg/phase0/llama8b_base-default_hpg.yaml
  configs/hpg/phase0/llama8b_base-strong_hpg.yaml
)
PHASE12_TRAIN=(
  configs/hpg/phase1/llama1b_lora_ep1_hpg.yaml
  configs/hpg/phase1/llama3b_lora_ep1_hpg.yaml
  configs/hpg/phase2/llama8b_qlora_ep1_hpg.yaml
)
PHASE3_TRAIN=(
  configs/hpg/phase3/llama1b_lora_ep1_age4_hpg.yaml
  configs/hpg/phase3/llama3b_lora_ep1_age4_hpg.yaml
  configs/hpg/phase3/llama8b_qlora_ep1_age4_hpg.yaml
)

# ---- Settings ----
if [ ! -f "$ENV_FILE" ]; then
  if [ "$DRY_RUN" = 1 ]; then
    echo "# $ENV_FILE not found; dry run uses scripts/slurm/hpg.env.example" >&2
    ENV_FILE=scripts/slurm/hpg.env.example
  else
    echo "error: $ENV_FILE not found. Copy scripts/slurm/hpg.env.example to scripts/slurm/hpg.env and fill it in." >&2
    exit 1
  fi
fi
# shellcheck disable=SC1090
source "$ENV_FILE"
for v in HPG_ACCOUNT HPG_QOS HPG_PARTITION HPG_GPUS HPG_TIME_SMOKE HPG_TIME_TRAIN HPG_TIME_EVAL; do
  if [ -z "${!v:-}" ]; then echo "error: $v is not set in $ENV_FILE" >&2; exit 1; fi
  if [ "$DRY_RUN" = 0 ] && [[ "${!v}" == *YOUR_GROUP* ]]; then
    echo "error: $v in $ENV_FILE is still the placeholder '${!v}'" >&2; exit 1
  fi
done

# ---- Helpers ----
run_name() {  # run_name: <value> from a config's top level
  sed -n "s/^run_name:[[:space:]]*//p" "$1" | tr -d "\"'" | head -1
}

check_config() {
  local cfg="$1"
  [ -f "$cfg" ] || { echo "error: config $cfg does not exist" >&2; exit 1; }
  [ -n "$(run_name "$cfg")" ] || { echo "error: $cfg has no run_name" >&2; exit 1; }
}

config_value() {  # config_value CONFIG KEY -> value of "  KEY:" in the model: block, without quotes
  sed -n "/^model:/,/^[^[:space:]]/s/^  $2:[[:space:]]*//p" "$1" | tr -d "\"'" | head -1
}

check_model_policy() {  # POLICIES.md §1: refuse prohibited models (and adapters trained on them) before queuing
  local cfg="$1" name adapter args
  name="$(config_value "$cfg" name)"
  [ -n "$name" ] || { echo "error: $cfg has no model.name" >&2; exit 1; }
  args=("$name" --context "$cfg (run_name $(run_name "$cfg"))")
  adapter="$(config_value "$cfg" adapter)"
  if [ -n "$adapter" ] && [ "$adapter" != null ]; then args+=(--adapter "$adapter"); fi
  "${PYTHON:-python3}" -m src.utils.model_policy "${args[@]}" || exit 3
}

check_data() {  # the processed CHILDES data is never in git; it must be copied or rebuilt on /blue first
  local cfg="$1" dir bucket
  dir="$(sed -n 's/^  processed_dir:[[:space:]]*//p' "$cfg" | head -1)"
  bucket="$(sed -n 's/^  bucket:[[:space:]]*//p' "$cfg" | head -1)"
  if [ ! -f "$dir/$bucket/train.jsonl" ]; then
    echo "error: $dir/$bucket/train.jsonl missing (needed by $cfg). See README 'Training on HiPerGator'." >&2
    exit 1
  fi
}

N_JOBS=0
LAST_JOB=""
# submit KIND CONFIG RUN_ID DEPS [ADAPTER]   KIND = train | eval; sets LAST_JOB
submit() {
  local kind="$1" cfg="$2" run_id="$3" deps="$4" adapter="${5:-}" time script
  case "$kind" in
    train) script=scripts/slurm/train.sbatch ;;
    eval) script=scripts/slurm/evaluate.sbatch ;;
  esac
  if [[ "$run_id" == *smoke* ]]; then time="$HPG_TIME_SMOKE"
  elif [ "$kind" = train ]; then time="$HPG_TIME_TRAIN"
  else time="$HPG_TIME_EVAL"; fi

  local args=(sbatch --parsable
    --job-name "sl-${kind}-$(run_name "$cfg")"
    --account "$HPG_ACCOUNT" --qos "$HPG_QOS" --partition "$HPG_PARTITION"
    --gpus "$HPG_GPUS" --cpus-per-task "${HPG_CPUS:-4}" --mem "${HPG_MEM:-64gb}" --time "$time"
    --output "experiments/$run_id/slurm-${kind}-%j.out"
    --export "ALL,PROJECT_ROOT=$ROOT")
  if [ -n "${HPG_MAIL_USER:-}" ]; then args+=(--mail-type END,FAIL --mail-user "$HPG_MAIL_USER"); fi
  if [ -n "$deps" ]; then args+=(--dependency "afterok:$deps" --kill-on-invalid-dep yes); fi
  args+=("$script" "$cfg" "$run_id")
  if [ -n "$adapter" ]; then args+=("$adapter"); fi

  N_JOBS=$((N_JOBS + 1))
  if [ "$DRY_RUN" = 1 ]; then
    LAST_JOB="JOB_$N_JOBS"
    echo "$LAST_JOB = ${args[*]}"
  else
    mkdir -p "experiments/$run_id"
    LAST_JOB="$("${args[@]}" | cut -d';' -f1)"
    echo "$LAST_JOB = ${args[*]}"
  fi
}

# submit_train_eval CONFIG DEPS  -> train job, then an eval job that waits for it; sets LAST_JOB to the eval job
submit_train_eval() {
  local cfg="$1" deps="$2" run_id train_job
  run_id="${STAMP}_$(run_name "$cfg")"
  submit train "$cfg" "$run_id" "$deps"
  train_job="$LAST_JOB"
  submit eval "$cfg" "$run_id" "$train_job" "experiments/$run_id/adapter"
}

# ---- --only: pick the one config by run_name ----
ONLY_CFG=""
ONLY_KIND=""
if [ -n "$ONLY" ]; then
  for cfg in "${PHASE0_EVAL[@]}"; do
    if [ "$(run_name "$cfg")" = "$ONLY" ]; then ONLY_CFG="$cfg"; ONLY_KIND=eval; fi
  done
  for cfg in "${SMOKE_TRAIN[@]}" "${PHASE12_TRAIN[@]}" "${PHASE3_TRAIN[@]}"; do
    if [ "$(run_name "$cfg")" = "$ONLY" ]; then ONLY_CFG="$cfg"; ONLY_KIND=train; fi
  done
  if [ -z "$ONLY_CFG" ]; then
    # A past run outside the chain: if its model is prohibited, say so plainly rather than "unknown run".
    for cfg in configs/hpg/*/*.yaml; do
      if [ "$(run_name "$cfg")" = "$ONLY" ]; then check_model_policy "$cfg"; fi
    done
    echo "error: --only $ONLY matches no run_name in the chain. Known run_names:" >&2
    for cfg in "${SMOKE_TRAIN[@]}" "${PHASE0_EVAL[@]}" "${PHASE12_TRAIN[@]}" "${PHASE3_TRAIN[@]}"; do
      echo "  $(run_name "$cfg")" >&2
    done
    exit 2
  fi
fi

# ---- Checks before anything is queued ----
if [ -n "$ONLY" ]; then ALL=("$ONLY_CFG")
else
  ALL=("${SMOKE_TRAIN[@]}")
  if [ "$SMOKE_ONLY" = 0 ]; then ALL+=("${PHASE0_EVAL[@]}" "${PHASE12_TRAIN[@]}" "${PHASE3_TRAIN[@]}"); fi
fi
for cfg in "${ALL[@]}"; do
  check_config "$cfg"
  check_model_policy "$cfg"
  if [ "$DRY_RUN" = 0 ]; then check_data "$cfg"; fi
done
if [ "$DRY_RUN" = 0 ] && ! command -v sbatch >/dev/null 2>&1; then
  echo "error: sbatch not found; run this on a HiPerGator login node" >&2; exit 1
fi

# ---- --only: one run, no smoke gate ----
if [ -n "$ONLY" ]; then
  echo "# --only $ONLY (stamp $STAMP)"
  if [ "$ONLY_KIND" = train ]; then submit_train_eval "$ONLY_CFG" ""
  else submit eval "$ONLY_CFG" "${STAMP}_$ONLY" ""; fi
  echo "# $N_JOBS jobs$([ "$DRY_RUN" = 1 ] && echo ' (dry run, nothing submitted)'). Watch them with: squeue -u \$USER"
  exit 0
fi

# ---- Stage 1: smoke ----
echo "# stage smoke (stamp $STAMP)"
SMOKE_JOBS=()
for cfg in "${SMOKE_TRAIN[@]}"; do
  submit_train_eval "$cfg" ""
  SMOKE_JOBS+=("$LAST_JOB")
done
GATE="$(IFS=:; echo "${SMOKE_JOBS[*]}")"

if [ "$SMOKE_ONLY" = 1 ]; then
  echo "# --smoke-only: $N_JOBS jobs"
  exit 0
fi

# ---- Stage 2: Phase 0 baselines (eval only), gated on the smoke tests ----
echo "# stage phase0 (after $GATE)"
for cfg in "${PHASE0_EVAL[@]}"; do
  submit eval "$cfg" "${STAMP}_$(run_name "$cfg")" "$GATE"
done

# ---- Stage 3: Phase 1 LoRA, Phase 2 QLoRA and Phase 3 age-4 runs, each train -> evaluate, gated on the smoke tests ----
echo "# stage phase1+phase2+phase3 (after $GATE)"
for cfg in "${PHASE12_TRAIN[@]}" "${PHASE3_TRAIN[@]}"; do
  submit_train_eval "$cfg" "$GATE"
done

echo "# $N_JOBS jobs$([ "$DRY_RUN" = 1 ] && echo ' (dry run, nothing submitted)'). Watch them with: squeue -u \$USER"
