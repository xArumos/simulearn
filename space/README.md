---
title: SimuLearn Child Model Demo
emoji: 🧒
colorFrom: yellow
colorTo: blue
sdk: gradio
sdk_version: 6.30.0
python_version: "3.12"
app_file: app.py
pinned: false
license: cc-by-nc-sa-4.0
short_description: Untrained vs fine-tuned child-speech model, for team testing
---

# SimuLearn child model demo (team testing)

You play the adult and type a line. An untrained Qwen2.5-1.5B and our LoRA fine-tune both answer it, as a child of the age you pick.

This is for SimuLearn team testing only. Please don't type real names or personal details about real children.

The model is fine-tuned on CHILDES transcripts. MacWhinney, B. (2000). *The CHILDES Project: Tools for Analyzing Talk* (3rd ed.). Lawrence Erlbaum Associates. CC BY-NC-SA. No transcript text is included in this Space.

This Space is built from the SimuLearn repo by `scripts/build_space.py`. Edit the source there, not here.
