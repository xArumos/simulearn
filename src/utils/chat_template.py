"""The one place that applies a tokenizer's chat template, with the date pinned.

Llama 3.2's chat template writes "Today Date: <today's date>" into the system header unless the caller passes
`date_string`. Left alone, the prompt the model trained on would differ from the one it is evaluated or served
with a day later. Every caller (training collator, evaluation, the demo) goes through apply_chat_template()
below, which always passes the same date.

CHAT_TEMPLATE_DATE is "26 Jul 2024": the date Llama 3.1's template uses by default and Llama 3.2's template
falls back to, so all three Llama models see an identical system header. Templates that never mention a date
(SmolLM2, for example) ignore the extra argument.
"""
from __future__ import annotations

CHAT_TEMPLATE_DATE = "26 Jul 2024"


def apply_chat_template(tok, messages: list[dict], **kwargs):
    """tok.apply_chat_template(messages, **kwargs) with date_string pinned to CHAT_TEMPLATE_DATE."""
    kwargs.setdefault("date_string", CHAT_TEMPLATE_DATE)
    return tok.apply_chat_template(messages, **kwargs)
