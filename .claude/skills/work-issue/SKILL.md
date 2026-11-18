---
name: work-issue
description: Dispatch issue-worker subagents to complete GitHub issues in parallel worktrees. Use when the user says to work, start, or hand off issues to agents.
---

You are the coordinator. Workers do the work; you keep your own context small and relay results.

1. **Pick issues.** Use the numbers the user gave. With none, take open issues labelled `agent-ready` whose "Depends on" issues are all closed (`gh issue list --label agent-ready --json number,title,body,labels`). Skip anything labelled `needs-human`, `blocked`, `agent-working`.
2. **Check for clashes.** Two issues whose "Likely files" overlap run one after the other, never together. GPU jobs (training, evaluation, the local demo) run one at a time: the 12 GB card holds one job.
3. **Claim.** `gh issue edit <N> --remove-label agent-ready --add-label agent-working` for each.
4. **Dispatch.** One Agent call per issue, all in one message: `subagent_type: "issue-worker"`, `isolation: "worktree"`, prompt `Work issue #<N>: <title>`. Add any context from this conversation the issue text lacks.
5. **Relay.** As each worker returns, tell the user the PR link, or the question it left on the issue. Done when every dispatched issue is `in-review` or `needs-human`.
6. Remind the user that merging is theirs, and that `/sync-issues` afterwards updates `STATE.md` and cleans up.
