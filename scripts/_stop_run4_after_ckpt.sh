#!/usr/bin/env bash
# Wait until checkpoint-473 of run 4 is fully saved, then stop training (resume later with --resume).
C=/mnt/c/Users/justin/dev/simulearn-testing/experiments/20261016-1000_qwen1.5b_lora_ep1_ctx10/checkpoints/checkpoint-473
for i in $(seq 1 120); do                      # give up after 20 min
  if [ -f "$C/trainer_state.json" ] && [ -f "$C/optimizer.pt" ]; then
    sleep 5                                     # let the writes flush
    pkill -TERM -f '[s]rc.train.sft_lora' && echo "STOPPED at $(date +%T) after $(basename $C)"
    sleep 5; pgrep -af '[s]rc.train.sft_lora' >/dev/null && echo STILL-RUNNING || echo TRAINING-PROCESS-GONE
    exit 0
  fi
  sleep 10
done
echo TIMEOUT-NO-CHECKPOINT
