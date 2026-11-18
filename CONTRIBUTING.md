# Working on SimuLearn

All work is tracked as **GitHub Issues**: small tasks, each fitting one pull request. Anyone on the team can do an issue, or hand it to a Claude Code agent. `CLAUDE.md` is the project spec; this file is how the work flows.

## The rule that matters most

This repo is **public**. Issues, PRs, comments and commits never contain CHILDES transcript text, model replies that quote it, data files, adapters, tokens or passwords. Describe data with counts and metrics instead. (CHILDES is CC BY-NC-SA; our IRB covers analysis only. See `CLAUDE.md` §2.)

## Issue lifecycle

```
agent-ready ──> agent-working ──> in-review ──> closed (PR merged)
      │                │
      └── blocked      └── needs-human (a question or a human-only step; answer it, then relabel agent-ready)
```

| Label | Meaning |
|---|---|
| `agent-ready` | Fully specified; a person or an agent can start. |
| `agent-working` | Claimed. Someone (or an agent) is on it. |
| `in-review` | A PR is open and waiting for review and merge. |
| `needs-human` | Needs a login, an account, money, data, a rating, or a decision (CLAUDE.md §3 RED). |
| `blocked` | Waiting on another issue or an outside answer. |
| `area:data` `area:train` `area:eval` `area:demo` `area:hosting` `area:backend` `area:docs` | Which part of the code. |
| `size:S` / `size:M` | About an hour / a few hours. Bigger than M gets split. |

A good issue (the **Task** form fills these in): a goal in plain language, checkable acceptance criteria, likely files, what it depends on, its autonomy level (GREEN / YELLOW / RED, from `CLAUDE.md` §3) and its size. Two issues that touch the same files should depend on each other so they aren't worked on at the same time.

## Branches and pull requests

- Branch from `main`: `issue-<number>-<short-slug>`, e.g. `issue-12-age4-adapter`.
- The PR's first line is `Closes #<number>`, so merging closes the issue. Fill in the PR template.
- **CI** (`.github/workflows/tests.yml`) runs the test suite on every PR. It must be green before merging.
- A human merges. Agents never merge.
- Commit messages are plain: what changed and why. No co-author trailers.
- YELLOW changes add an entry to `DECISIONS.md`; training or eval runs add one to `experiments/EXPERIMENT_LOG.md`, in the same PR.
- `STATE.md` (the session handoff) is updated after merges by `/sync-issues`, not inside feature PRs. That keeps parallel PRs from conflicting.

## Running the tests

```bash
python -m pytest -q tests backend/tests
```

Tests that need the CHILDES data or a GPU skip themselves when it's missing. CI installs `requirements-ci.txt` (CPU-only); a full training environment uses `requirements.txt`.

## Working with Claude Code

The repo ships three skills and one agent in `.claude/`:

| You type | What happens |
|---|---|
| `/plan-issues <goal>` | Claude splits the goal into issues, shows you the drafts, and creates them on GitHub after you approve. |
| `/work-issue` or `/work-issue 12 14` | Claude starts one `issue-worker` agent per ready issue, each in its own git worktree, in parallel where safe. Each opens a PR, or leaves a question on the issue and labels it `needs-human`. |
| `/sync-issues` | After you merge PRs: pulls `main`, records the merges in `STATE.md`, deletes merged branches and worktrees, and lists what's ready next. |

A typical loop: `/plan-issues` once for a chunk of work, then `/work-issue`, review and merge the PRs, `/sync-issues`, and repeat. Answer `needs-human` questions on the issue itself, then relabel it `agent-ready`.

Agents run locally in your Claude Code session (no API key, no extra cost). They use your machine's GPU, so training and evaluation issues run one at a time.
