"""Live side-by-side demo: untrained Qwen vs the fine-tuned child model, for the same adult line.

    python -m src.demo.chat_demo [--config configs/demo.yaml] [--adapters-dir DIR] [--host 0.0.0.0] [--port 7860]
                                 [--device auto|cpu|cuda] [--require-password] [--selftest]

The model code (loading, prompts, generation) is in src/demo/engine.py; this file is the Gradio page.
You type the adult's lines and pick the child's age (one LoRA adapter per age bucket, listed in
configs/demo.yaml; ages without an adapter are hidden). Each model keeps its own conversation history,
trimmed like in training: the last 6 turns including the new adult line. Same system prompt and decoding
as evaluation (temperature 0.7, top-p 0.9, max 60 new tokens). <SILENCE FOR X SECONDS> is shown as a
visible pause. Runs on the GPU in bf16 (locally, or ZeroGPU on the hosted Space), or on the CPU in fp32. With
load_in_4bit: true in the config it runs in 4-bit NF4 on a local CUDA GPU only (QLoRA models, D11). Nothing is pre-filled:
no CHILDES text is shipped in the demo.

Optional environment variables: MONGODB_URI saves chats and 👍/👎 ratings (src/demo/store.py);
DEMO_PASSWORD puts a password on the page (any username). When run with main(), they are also read from the
repo's git-ignored .env (template: .env.example; local MongoDB: docker-compose.yml).
The always-on desktop service (scripts/serve_demo.sh) binds 127.0.0.1 and requires DEMO_PASSWORD.
"""
from __future__ import annotations

import argparse
import os
import time

import gradio as gr
import torch

from backend.app.env import load_env_file
from src.demo.engine import (  # noqa: F401  (re-exported: tests, space/app.py and upload_adapters.sh import them from here)
    SILENCE_RE,
    Demo,
    build_messages,
    check_4bit,
    find_adapters,
    pick_device,
    render,
    system_prompt,
    timed,
)
from src.demo.store import DemoStore, new_session_id
from src.utils.config import load_config, resolve

DEFAULT_CONFIG = "configs/demo.yaml"
SIDES = ("untrained", "fine-tuned")


def check_password(required: bool) -> None:
    """The service is reachable through the tunnel, so it refuses to start without a password."""
    if required and not os.getenv("DEMO_PASSWORD"):
        raise SystemExit("DEMO_PASSWORD is empty. Set it in the repo's .env (template: .env.example) and start again.")


def build_ui(demo: Demo, store: DemoStore, reply_both=None):
    """By default each column calls demo.reply separately, so the child's column can show first (the untrained one
    is slow on a CPU). The Space passes reply_both(ft_request, base_request) -> ((text, secs), (text, secs)): one
    @spaces.GPU call per turn, which uses less of each visitor's ZeroGPU quota (space/app.py)."""
    ages = sorted(demo.adapters)
    default_age = demo.cfg.get("default_age") if demo.cfg.get("default_age") in ages else ages[0]
    age_choices = [(f"{a} years old ({demo.adapters[a]['label']})", a) for a in ages]

    def empty_session():
        return {"id": None, "conv": {}, "versions": {s: [] for s in SIDES}}

    def respond(adult_line, name, age, base_raw, ft_raw, base_chat, ft_chat, strong_prompt, live_pauses, session):
        adult_line = (adult_line or "").strip()
        if not adult_line:
            yield "", base_raw, ft_raw, base_chat, ft_chat, session
            return
        owner = (name or "").strip() or "anonymous"
        if session["id"] is None:
            session = {**empty_session(), "id": new_session_id(), "conv": store.start(owner, age, list(SIDES))}
        demo.seed += 1
        seed = demo.seed

        def save(side, reply, model, secs):
            meta = {"session": session["id"], "side": side, "age": age, "strong_prompt": bool(strong_prompt and side == "untrained"),
                    "seed": seed, "gen_seconds": round(secs, 2), "device": demo.device}
            session["versions"][side].append(store.log_turn(session["conv"].get(side), owner, adult_line, reply, model, meta))

        # The child reply comes first: it is short, while the untrained model often writes all 60 tokens
        # (20-50 s on a CPU), so its column fills in afterwards.
        user_msg = {"role": "user", "content": adult_line}
        base_chat = base_chat + [user_msg]
        waiting = {"role": "assistant", "content": "*(writing…)*"}
        locked = gr.update(value="", interactive=False)  # no new line until both replies are in
        ft_req = (ft_raw, adult_line, age, system_prompt(age))
        base_req = (base_raw, adult_line, None, system_prompt(age, strong=strong_prompt))
        if reply_both:
            (f, f_secs), (b, b_secs) = reply_both(ft_req, base_req)
        else:
            f, f_secs = timed(demo.reply, ft_req)
        save("fine-tuned", f, f"age{age}:{demo.adapters[age]['path'].parent.name}", f_secs)
        ft_raw = ft_raw + [user_msg, {"role": "assistant", "content": f}]
        ft_chat = ft_chat + [user_msg]
        m = SILENCE_RE.match(f)
        if live_pauses and m:  # the child pauses before talking: show "thinking" for X seconds (max 5)
            yield locked, base_raw, ft_raw, base_chat + [waiting], ft_chat + [{"role": "assistant", "content": "*(thinking…)*"}], session
            time.sleep(min(int(m.group(1)), 5))
        ft_chat = ft_chat + [{"role": "assistant", "content": render(f)}]
        yield locked, base_raw, ft_raw, base_chat + [waiting], ft_chat, session
        if not reply_both:
            b, b_secs = timed(demo.reply, base_req)
        save("untrained", b, demo.cfg["base_model"], b_secs)
        base_raw = base_raw + [user_msg, {"role": "assistant", "content": b}]
        yield gr.update(value="", interactive=True), base_raw, ft_raw, base_chat + [{"role": "assistant", "content": render(b)}], ft_chat, session

    def make_rate(side):
        def rate(data: gr.LikeData, name, note, raw, session):
            turn = data.index // 2 if isinstance(data.index, int) else data.index[0] // 2
            versions = session["versions"][side]
            if turn >= len(versions) or 2 * turn + 1 >= len(raw):
                return note, gr.update()
            ok = store.rate(session["conv"].get(side), (name or "").strip() or "anonymous", versions[turn], side,
                            data.liked is True, raw[2 * turn + 1]["content"], note or "")
            msg = "Thanks, rating saved." if ok else "Rating not saved (saving is off)."
            return "", gr.update(value=msg, visible=True)
        return rate

    def clear():
        return gr.update(value="", interactive=True), [], [], [], [], empty_session(), gr.update(visible=False)

    saving = ("Chats and ratings are **saved** for the research team." if store.enabled
              else "Saving is **off** (no database configured).")
    with gr.Blocks(title="SimuLearn child model demo") as ui:
        gr.Markdown(
            "## SimuLearn: untrained vs fine-tuned child model\n"
            "You play the **adult** (teacher or caregiver). Type a line and both models answer it: an untrained AI on the left, "
            "and our model fine-tuned on real child–adult conversations on the right. Pauses (`<SILENCE FOR X SECONDS>`) are "
            "shown as *(…pauses…)*. Click 👍 or 👎 on any reply to rate it.\n\n"
            f"**For SimuLearn team testing only. Please don't type real names or personal details about real children.** {saving}  \n"
            "<sub>Training data: CHILDES (MacWhinney, 2000, *The CHILDES Project*, talkbank.org), CC BY-NC-SA.</sub>")
        base_raw, ft_raw, session = gr.State([]), gr.State([]), gr.State(empty_session())
        with gr.Row():
            name = gr.Textbox(label="Your name (so we know who tested)", scale=2)
            age = gr.Dropdown(age_choices, value=default_age, label="Child's age (changing it starts a new conversation)", scale=3)
        with gr.Row(equal_height=True):
            with gr.Column():
                gr.Markdown("### Untrained Qwen2.5-1.5B")
                base_chat = gr.Chatbot(value=[], height=440, label="Untrained")
            with gr.Column():
                gr.Markdown("### Fine-tuned on CHILDES (LoRA)")
                ft_chat = gr.Chatbot(value=[], height=440, label="Fine-tuned")
        with gr.Row():
            box = gr.Textbox(placeholder="Type the adult's line and press Enter…", scale=5, show_label=False, autofocus=True)
            send = gr.Button("Send", variant="primary", scale=1)
            reset = gr.Button("New conversation", scale=1)
        with gr.Row():
            note = gr.Textbox(label="Optional note: type it, then click 👍/👎 on the reply it's about", scale=4)
            saved = gr.Markdown(visible=False)
        with gr.Row():
            strong = gr.Checkbox(value=False, label="Give the untrained model the stronger “talk like a real child” prompt")
            live = gr.Checkbox(value=True, label="Play the child's pauses in real time (max 5 s)")
        ins = [box, name, age, base_raw, ft_raw, base_chat, ft_chat, strong, live, session]
        outs = [box, base_raw, ft_raw, base_chat, ft_chat, session]
        box.submit(respond, ins, outs, api_name="respond")
        send.click(respond, ins, outs, api_name=False)
        reset_outs = [box, base_raw, ft_raw, base_chat, ft_chat, session, saved]
        reset.click(clear, None, reset_outs, api_name=False)
        age.change(clear, None, reset_outs, api_name=False)
        base_chat.like(make_rate("untrained"), [name, note, base_raw, session], [note, saved], api_name=False)
        ft_chat.like(make_rate("fine-tuned"), [name, note, ft_raw, session], [note, saved], api_name=False)
    return ui


def launch(ui, port: int, host: str = "0.0.0.0") -> None:
    password = os.getenv("DEMO_PASSWORD")
    auth = (lambda _user, pw: pw == password) if password else None
    ui.launch(server_name=host, server_port=port, show_error=True, auth=auth,
              auth_message="Type any username and the team password (ask Justin)." if password else None)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    ap.add_argument("--adapters-dir", default=None, help="folder with age<N>/ adapter subfolders (the hosted Space)")
    ap.add_argument("--host", default="0.0.0.0", help="127.0.0.1 = this machine only (the desktop service)")
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto", help="auto = cuda if available")
    ap.add_argument("--require-password", action="store_true", help="refuse to start when DEMO_PASSWORD is empty")
    ap.add_argument("--selftest", action="store_true", help="run two invented lines through each model and exit")
    return ap.parse_args(argv)


def main() -> None:
    a = parse_args()
    load_env_file()  # MONGODB_URI / MONGODB_DATABASE / DEMO_PASSWORD from the repo's .env; shell variables win
    if not a.selftest:
        check_password(a.require_password)
    cfg = load_config(resolve(a.config))
    adapters = find_adapters(cfg, a.adapters_dir)
    device = pick_device(a.device)
    print(f"Demo: ages {sorted(adapters)} on {device}", flush=True)
    demo = Demo(cfg, adapters, device=device)
    if a.selftest:
        for age in sorted(demo.adapters):
            hist_b, hist_f = [], []
            for line in ["Hi! What are you building with those blocks?", "Wow. How tall is it going to be?"]:  # invented test lines
                t0 = time.time()
                b = demo.reply(hist_b, line, None, system_prompt(age))
                t1 = time.time()
                f = demo.reply(hist_f, line, age, system_prompt(age))
                t2 = time.time()
                hist_b += [{"role": "user", "content": line}, {"role": "assistant", "content": b}]
                hist_f += [{"role": "user", "content": line}, {"role": "assistant", "content": f}]
                print(f"[age {age}] ADULT:      {line}\n[age {age}] UNTRAINED:  {render(b)}  ({t1 - t0:.1f} s)\n"
                      f"[age {age}] FINE-TUNED: {render(f)}  ({t2 - t1:.1f} s)\n")
        if torch.cuda.is_available():
            print(f"VRAM peak {torch.cuda.max_memory_allocated() / 2**30:.2f} GiB")
        return
    store = DemoStore.from_env()
    print(f"Demo: saving {'on' if store.enabled else 'OFF (MONGODB_URI empty or MongoDB unreachable)'}; "
          f"serving http://{a.host}:{a.port}", flush=True)
    launch(build_ui(demo, store), a.port, host=a.host)


if __name__ == "__main__":
    main()
