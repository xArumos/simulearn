"""An offline stand-in for a Llama-3-style instruct tokenizer, so chat-template tests run in CI without the
gated Meta downloads.

The tokenizer is byte-level BPE with no merges (one token per byte, so any text round-trips exactly) plus the
Llama 3 special tokens. The chat template is written for this test, not copied from Meta. It mimics the two
parts that matter here: the system header carries a "Today Date" that comes from strftime_now() unless the
caller passes date_string (as the Llama 3.2 template does), and each turn ends with <|eot_id|>.
"""
from __future__ import annotations

TEMPLATE = (
    "{{- bos_token }}"
    "{%- if date_string is not defined %}"
    "{%- if strftime_now is defined %}{%- set date_string = strftime_now('%d %b %Y') %}"
    "{%- else %}{%- set date_string = '26 Jul 2024' %}{%- endif %}"
    "{%- endif %}"
    "{%- if messages[0]['role'] == 'system' %}"
    "{%- set system_message = messages[0]['content'] | trim %}{%- set messages = messages[1:] %}"
    "{%- else %}{%- set system_message = '' %}{%- endif %}"
    "{{- '<|start_header_id|>system<|end_header_id|>\\n\\n' }}"
    "{{- 'Today Date: ' + date_string + '\\n\\n' }}"
    "{{- system_message + '<|eot_id|>' }}"
    "{%- for m in messages %}"
    "{{- '<|start_header_id|>' + m['role'] + '<|end_header_id|>\\n\\n' + m['content'] | trim + '<|eot_id|>' }}"
    "{%- endfor %}"
    "{%- if add_generation_prompt %}{{- '<|start_header_id|>assistant<|end_header_id|>\\n\\n' }}{%- endif %}"
)

SPECIAL = ["<|begin_of_text|>", "<|start_header_id|>", "<|end_header_id|>", "<|eot_id|>"]


def fake_llama_tokenizer():
    """A PreTrainedTokenizerFast shaped like Llama 3 instruct: eos = <|eot_id|>, no pad token."""
    from tokenizers import Tokenizer, decoders, models, pre_tokenizers
    from transformers import PreTrainedTokenizerFast

    alphabet = sorted(pre_tokenizers.ByteLevel.alphabet())
    vocab = {ch: i for i, ch in enumerate(alphabet)}
    for s in SPECIAL:
        vocab[s] = len(vocab)
    core = Tokenizer(models.BPE(vocab=vocab, merges=[]))
    core.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    core.decoder = decoders.ByteLevel()
    tok = PreTrainedTokenizerFast(tokenizer_object=core, bos_token="<|begin_of_text|>", eos_token="<|eot_id|>",
                                  additional_special_tokens=SPECIAL[1:3])
    tok.chat_template = TEMPLATE
    return tok
