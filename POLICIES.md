# POLICIES.md: university and HiPerGator rules

Outside rules that this project must follow, in addition to the CHILDES/IRB rules in `CLAUDE.md` §2. These are **not** project choices. Breaking them can get a HiPerGator account suspended or banned. When unsure, ask UF Research Computing (https://support.rc.ufl.edu) before running anything.

## 1. No language models from countries of concern

**The rule.** Florida law prohibits using software, LLMs included, that comes from a *foreign country of concern*. Section 288.860(1)(a) of the Florida Statutes lists them: China, Russia, Iran, North Korea, Cuba, the Maduro regime in Venezuela, and Syria, including any entity under significant control of one of them. For LLMs this mainly means China.

UF's official position, quoted from UF Research Computing:

> The University strictly prohibits the deployment or utilization of large-language models that are developed, operated, or otherwise hosted by organizations located in, or controlled by, a foreign country of concern. Accordingly, any use of such models on university computing resources, or the processing of any university data through them, is not permitted.

**What it covers** (per UF Research Computing):
- All UF computing resources, including HiPerGator. It also covers any processing of university data.
- Every kind of use: inference, research, training, evaluation, demos.
- All users, whether or not they are affiliated with UF or located in Florida.
- **Fine-tuned versions too.** LoRA, QLoRA, fine-tuning, quantization or third-party re-releases of such a model do **not** make it acceptable. An adapter trained on a prohibited base model is still prohibited, because it only works on top of that base.
- **No exceptions**, even for legitimate research interest.

**Penalties.** A first offense usually means account suspension with a warning, and a required meeting with UFIT staff before the account is reactivated. A second offense means a permanent HiPerGator ban.

**For this project:**
- **Qwen (Alibaba Cloud, China) is prohibited.** This covers `Qwen/Qwen2.5-1.5B-Instruct`, `Qwen/Qwen2.5-7B-Instruct`, every other Qwen release, and every adapter we trained on them. See `DECISIONS.md` D11 for what was affected and the proposed replacement.
- Also prohibited, as examples (the list is not complete): DeepSeek, Zhipu / Z.ai (GLM, ChatGLM), Moonshot (Kimi), 01.AI (Yi), Baichuan, Shanghai AI Lab (InternLM), MiniMax, Tencent (Hunyuan), Baidu (ERNIE), ByteDance (Doubao, Seed), and their fine-tunes. Avoid models distilled from them as well (for example `DeepSeek-R1-Distill-*`), even when the base is from somewhere else.
- **The code refuses them too.** `src/utils/model_policy.py` holds a deny list of organizations (`Qwen/`, `deepseek-ai/`, `THUDM/`, `zai-org/`, `moonshotai/`, `01-ai/`, `baichuan-inc/`, `internlm/`, `MiniMaxAI/`, `tencent/`, `baidu/`, `ByteDance*`, ...) and name patterns (`qwen`, `deepseek`, `chatglm`, ..., which also catch re-uploads and distills such as `DeepSeek-R1-Distill-Llama-8B`). It runs before anything is downloaded: in `load_tokenizer` and `load_model` (`src/utils/modeling.py`, so training, evaluation and the demo), in `scripts/gpu_smoke_test.py`, and in `scripts/slurm/submit_all.sh`, which checks every config before queuing any job. It also reads an adapter's `adapter_config.json` and refuses an adapter whose base model (`base_model_name_or_path`) is prohibited. The old Qwen configs stay in `configs/` as the record of past runs; the guard makes each of them refuse to load or submit. Check a name by hand with `python -m src.utils.model_policy MODEL_NAME [--adapter PATH]` (exit 3 = prohibited). The list is a safety net, not an approval: a model that passes it still needs the check below.
- **Before adding any model** to a config, check who developed it (the organization on its model card and where that organization is based). Record it in `DECISIONS.md`. If ownership or origin is unclear, do not use it; open a ticket with UF Research Computing first.
- Models that UF Research Computing itself provides on HiPerGator are a good sign of an acceptable model. Its [AI models page](https://docs.rc.ufl.edu/quickstart/ai_models/) lists Llama (Meta), Gemma (Google) and Mistral AI, among others.
- Hosting a model on Hugging Face does not change its origin. The developer is what counts.

Sources:
- UF Research Computing, "Notice on LLMs from Countries of Concern", https://docs.rc.ufl.edu/software/apps/ollama/
- UFIT Information Security Office, Fast Path Solutions (filter "Not Permitted"; includes "Prohibited use of Large Language Models"), https://it.ufl.edu/security/audiences/faculty--staff/fast-path-solutions/
- HiPerGator user guidance on LLMs from countries of concern, as shared with the team on 2026-11-19.

## 2. Do not leave a GPU idle on HiPerGator

UFIT Research Computing prohibits allocating a GPU and leaving it idle, and it actively enforces this. Running fake or non-productive work just to get past the idle-detection tools is also a violation, and they say they will notice.

**For this project:**
- Use batch jobs (`scripts/slurm/submit_all.sh`) for training and evaluation. They release the GPU as soon as the work ends.
- Do not keep an interactive GPU session (`srun --gpus ...`, Open OnDemand, Jupyter) open while you are away, reading logs or writing code. End it, and request a new one when you need it.
- Do not run the chat demo on a HiPerGator GPU and leave it waiting for testers. The demo runs on the desktop (`DECISIONS.md` D10).
- Guidance: https://docs.rc.ufl.edu/scheduler/idle_gpu_policy/
