# gleason-adult-pilot

## Adult-target Gleason pilot

**Hypothesis:** Test whether one epoch of LoRA supervised fine-tuning learns adult responses from
Gleason conversations, using the existing child-held-out split workflow.

**Data:** 10,898 train examples from 20 children. Validation and test sets contain 1,238 examples
from 2 children each. Children and non-adult speakers are context only; the target response is
always an adult turn. The run used 1,000 deterministically sampled validation examples for loss
and generation evaluation. No test-set evaluation was run.

**Training:** Qwen2.5-1.5B-Instruct with 4-bit base weights and FP16 LoRA (rank 16, alpha 32,
all linear layers), one epoch, effective batch size 16. Completed 682 optimizer steps in 5.26
hours; peak training GPU allocation was 3.19 GiB. The best training checkpoint was step 510
(validation loss 2.3078); final training loss was 2.4402.

**Validation:** Post-training target loss was 2.5179 (perplexity 12.40) over 11,632 target
tokens. Generated responses averaged 7.63 words (validation references: 7.58); length
Wasserstein distance was 0.683. Generation was reproducible on the 32-example repeat check.
Additional aggregate metrics are in `metrics.json`.

This is a pilot result, not a comparison against the child-target experiments. Adapter weights,
checkpoints, generated response samples, and transcript text are intentionally excluded from Git.
