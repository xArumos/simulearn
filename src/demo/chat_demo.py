"""Live side-by-side demo: untrained Qwen vs the fine-tuned child model, for the same adult line.

    python -m src.demo.chat_demo [--adapter experiments/<run>/adapter] [--port 7860] [--selftest]

You type the adult's lines. Each model keeps its own conversation history (its own past replies),
trimmed to the last 6 turns like in training. Same system prompt and decoding as evaluation
(temperature 0.7, top-p 0.9, max 60 new tokens). <SILENCE FOR X SECONDS> is shown as a visible
pause. Nothing is pre-filled: no CHILDES text is shipped in the demo.
"""
from __future__ import annotations

import argparse
import re
import time

import torch

from src.eval.evaluate import STRONG_PROMPT
from src.utils.config import resolve
from src.utils.modeling import load_model, load_tokenizer

BASE = "Qwen/Qwen2.5-1.5B-Instruct"
DEFAULT_ADAPTER = "experiments/20261016-0003_qwen1.5b_lora_ep1/adapter"
SYSTEM = "You are a 5-year-old child talking with a caregiver. Reply the way a real child of that age would."
DECODING = {"temperature": 0.7, "top_p": 0.9, "max_new_tokens": 60}
CONTEXT_TURNS = 6
SILENCE_RE = re.compile(r"<SILENCE FOR (\d+) SECONDS>")


class Demo:
    def __init__(self, adapter: str):
        self.tok = load_tokenizer(BASE)
        self.model = load_model({"name": BASE, "adapter": str(resolve(adapter)), "dtype": "bfloat16"})
        self.seed = 1234

    @torch.no_grad()
    def reply(self, history: list[dict], adult_line: str, fine_tuned: bool, system: str) -> str:
        msgs = [{"role": "system", "content": system}] + history[-CONTEXT_TURNS:] + [{"role": "user", "content": adult_line}]
        text = self.tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        ids = self.tok(text, return_tensors="pt").to(self.model.device)
        torch.manual_seed(self.seed)
        kw = dict(**ids, do_sample=True, pad_token_id=self.tok.pad_token_id, **DECODING)
        if fine_tuned:
            out = self.model.generate(**kw)
        else:
            with self.model.disable_adapter():  # same weights without the LoRA add-on = untrained Qwen
                out = self.model.generate(**kw)
        return self.tok.decode(out[0, ids["input_ids"].shape[1]:], skip_special_tokens=True).strip()


def render(text: str) -> str:
    """Show silence tags as a visible pause instead of raw text."""
    return SILENCE_RE.sub(lambda m: f"*(…pauses {m.group(1)} s…)*", text).strip() or "*(no reply)*"


def build_ui(demo: Demo):
    import gradio as gr

    def respond(adult_line, base_raw, ft_raw, base_chat, ft_chat, strong_prompt, live_pauses):
        adult_line = (adult_line or "").strip()
        if not adult_line:
            yield "", base_raw, ft_raw, base_chat, ft_chat
            return
        demo.seed += 1
        base_sys = STRONG_PROMPT.format(age=5) if strong_prompt else SYSTEM
        b = demo.reply(base_raw, adult_line, fine_tuned=False, system=base_sys)
        f = demo.reply(ft_raw, adult_line, fine_tuned=True, system=SYSTEM)
        base_raw = base_raw + [{"role": "user", "content": adult_line}, {"role": "assistant", "content": b}]
        ft_raw = ft_raw + [{"role": "user", "content": adult_line}, {"role": "assistant", "content": f}]
        base_chat = base_chat + [{"role": "user", "content": adult_line}, {"role": "assistant", "content": render(b)}]
        ft_chat = ft_chat + [{"role": "user", "content": adult_line}]
        m = SILENCE_RE.match(f)
        if live_pauses and m:  # the child pauses before talking: show "thinking" for X seconds (max 5)
            yield "", base_raw, ft_raw, base_chat, ft_chat + [{"role": "assistant", "content": "*(thinking…)*"}]
            time.sleep(min(int(m.group(1)), 5))
        yield "", base_raw, ft_raw, base_chat, ft_chat + [{"role": "assistant", "content": render(f)}]

    def clear():
        return "", [], [], [], []

    with gr.Blocks(title="SimuLearn child model demo") as ui:
        gr.Markdown("## SimuLearn: untrained vs fine-tuned “5-year-old”\nType what the **adult** says. "
                    "Both models answer the same line. Pauses (`<SILENCE FOR X SECONDS>`) are shown as *(…pauses…)*.")
        base_raw, ft_raw = gr.State([]), gr.State([])
        with gr.Row(equal_height=True):
            with gr.Column():
                gr.Markdown("### Untrained Qwen2.5-1.5B")
                base_chat = gr.Chatbot(value=[], height=460, label="Untrained")
            with gr.Column():
                gr.Markdown("### Fine-tuned on CHILDES (LoRA, run 3)")
                ft_chat = gr.Chatbot(value=[], height=460, label="Fine-tuned")
        with gr.Row():
            box = gr.Textbox(placeholder="Type the adult's line and press Enter…", scale=5, show_label=False, autofocus=True)
            send = gr.Button("Send", variant="primary", scale=1)
            reset = gr.Button("New conversation", scale=1)
        with gr.Row():
            strong = gr.Checkbox(value=False, label="Give the untrained model the stronger “talk like a real child” prompt")
            live = gr.Checkbox(value=True, label="Play the child's pauses in real time (max 5 s)")
        ins = [box, base_raw, ft_raw, base_chat, ft_chat, strong, live]
        outs = [box, base_raw, ft_raw, base_chat, ft_chat]
        box.submit(respond, ins, outs, api_name="respond")
        send.click(respond, ins, outs, api_name=False)
        reset.click(clear, None, outs, api_name=False)
    return ui


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default=DEFAULT_ADAPTER)
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--selftest", action="store_true", help="run two invented lines through both models and exit")
    a = ap.parse_args()
    demo = Demo(a.adapter)
    if a.selftest:
        hist_b, hist_f = [], []
        for line in ["Hi! What are you building with those blocks?", "Wow. How tall is it going to be?"]:  # invented test lines
            b = demo.reply(hist_b, line, False, SYSTEM)
            f = demo.reply(hist_f, line, True, SYSTEM)
            hist_b += [{"role": "user", "content": line}, {"role": "assistant", "content": b}]
            hist_f += [{"role": "user", "content": line}, {"role": "assistant", "content": f}]
            print(f"ADULT:      {line}\nUNTRAINED:  {render(b)}\nFINE-TUNED: {render(f)}\n")
        print(f"VRAM peak {torch.cuda.max_memory_allocated() / 2**30:.2f} GiB")
        return
    build_ui(demo).launch(server_name="0.0.0.0", server_port=a.port, show_error=True)


if __name__ == "__main__":
    main()
