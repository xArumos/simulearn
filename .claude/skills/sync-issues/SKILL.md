---
name: sync-issues
description: Sync main after PRs merge, record them in STATE.md, clean up issue branches and worktrees, and list what is ready next. Use at session start or after the user merges PRs.
---

1. **Pull.** `git switch main && git pull --ff-only`.
2. **Collect merges.** `gh pr list --state merged --search "merged:>=<date in STATE.md 'Last updated'>" --json number,title,closingIssuesReferences,headRefName`.
3. **Update `STATE.md`.** Add each merged PR to "Done so far" (one line: what changed, PR #), refresh "Best model so far" if a run beat it, move answered items out of "Waiting on user", bump "Last updated". The task list itself lives on GitHub: "Next planned actions" names issue numbers rather than restating them. Commit on `main` only if the user has said to; otherwise put the change on a `state-sync-<date>` branch and open a PR.
4. **Clean up.** For merged `issue-*` branches: `git worktree remove` their worktrees (check `git worktree list`), `git branch -d` locally, `git push origin --delete` remotely. Skip any branch with unmerged commits and say so.
5. **Next.** Report open issues by state: `needs-human` (with the question), `agent-ready` with dependencies met, and blocked. Done when the user can see what to merge, answer, or dispatch next.
