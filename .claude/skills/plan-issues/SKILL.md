---
name: plan-issues
description: Split a goal into GitHub issues sized for one agent and one PR each. Use when the user wants work broken down, planned as issues, or added to the backlog.
---

The rules for a good issue (template fields, labels, sizes, public-repo data rules) live in `CONTRIBUTING.md`. Read it first.

1. **Understand the goal.** Read `STATE.md`, the relevant code, and `gh issue list --state open` so you neither duplicate an open issue nor contradict one. Ask the user only about choices that change the split.
2. **Slice.** Cut the goal into vertical slices, each one PR of size S or M that an agent can finish from the issue text alone. Each slice gets: goal, checkable acceptance criteria (always including "pytest passes"), likely files, depends-on, autonomy level (CLAUDE.md §3), size, area label. Slices that touch the same files get a dependency between them so they never run in parallel. Anything only a human can do (logins, HF/Atlas/HiPerGator setup, ratings, merges) becomes its own issue labelled `needs-human`.
3. **Show the drafts** to the user as a numbered list (title, size, labels, depends-on, one-line goal). Done when the user approves or edits them.
4. **Create.** For each approved draft, in dependency order, write the body to a scratch file in the task template's section order and run `gh issue create --title ... --body-file ... --label agent-ready,<area>,<size>` (`needs-human` instead of `agent-ready` where it applies). Replace draft numbers in "Depends on" with real issue numbers. For 3+ issues, also create a tracking issue whose body is a task list (`- [ ] #N`) of them.
5. **Report** the issue links and which ones are ready for `/work-issue` right now.
