"""Model/tokenizer loading shared by training and evaluation. All choices come from the config."""
from __future__ import annotations

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


def load_tokenizer(name: str):
    tok = AutoTokenizer.from_pretrained(name)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    return tok


def load_model(mcfg: dict, for_training: bool = False):
    dtype = getattr(torch, mcfg.get("dtype", "bfloat16"))
    kwargs = {"dtype": dtype, "device_map": mcfg.get("device_map", "cuda"),
              "attn_implementation": mcfg.get("attn_implementation", "sdpa")}
    if mcfg.get("load_in_4bit"):
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype)
    model = AutoModelForCausalLM.from_pretrained(mcfg["name"], **kwargs)
    if mcfg.get("adapter"):
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, mcfg["adapter"], is_trainable=for_training)
    if not for_training:
        model.eval()
    return model
