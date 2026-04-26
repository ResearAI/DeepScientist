# Workspace Explorer Q&A

This page explains a common surprise: a file or folder is visible in the terminal, but it does not appear in the Web Explorer or Search panel.

## 1. Is Explorer the same as the local quest root?

Not always.

The desktop `FILES` view shows the backend's active workspace root, not always `<home>/quests/<id>`. The active root resolves in this order:

1. `current_workspace_root` in `.ds/research_state.json`
2. `research_head_worktree_root` in `.ds/research_state.json`
3. the quest root

During an analysis or paper branch, the active root may be:

```text
<quest_root>/.ds/worktrees/<branch-worktree-name>
```

If you manually create a folder in the quest root while Explorer is pointed at a worktree, the folder may not appear in Explorer.

## 2. Which paths are hidden?

The desktop `FILES` view recursively lists the active workspace root, but skips:

- `.git`
- `.ds/worktrees` when the active root is the quest root
- `__pycache__`
- `.pytest_cache`

If the active workspace root itself is a `.ds/worktrees/<name>` directory, Explorer treats that worktree as the root and shows its contents.

Mobile uses a smaller profile and may hide or truncate `.ds`, `artifacts`, `tmp`, `userfiles`, and deep directories.

## 3. What is the difference between `FILES`, `SCOPE`, and `SNAPSHOT`?

- `FILES`: live tree for the current active workspace root.
- `SCOPE`: files related to the selected graph node, stage, diff, or reveal target.
- `SNAPSHOT`: a read-only git revision or commit view.

To check whether a terminal-created file is visible, switch to `FILES` and refresh.

## 4. Will a terminal-created folder appear automatically?

No. DeepScientist does not currently watch the local filesystem.

After creating files manually:

1. Make sure they are under the current active workspace root.
2. Switch Explorer to `FILES`.
3. Click refresh or reload the page.

Empty folders can appear in Explorer, but Search usually cannot find empty folders because it mainly scans file paths and readable text content.

## 5. Why can Search miss something?

Search scans files under the active workspace root. It does not search every worktree at once.

It also skips large files, binary files, and Explorer-filtered paths. Use plain text queries such as:

```text
run_probe
experiments/analysis
```

Do not use shell glob syntax for normal searches. Older frontend code wrapped queries as `*term*`; newer code tolerates that legacy shape, but plain keywords are preferred.

## 6. How do I check what Explorer is looking at?

Use the Explorer API:

```bash
curl -s "http://127.0.0.1:<port>/api/quests/<quest_id>/explorer" | jq -r '.quest_root'
```

Or inspect the research state:

```bash
cat <quest_root>/.ds/research_state.json
```

Check:

- `current_workspace_root`
- `research_head_worktree_root`
- `paper_parent_worktree_root`
- `analysis_parent_worktree_root`

If your terminal `pwd` differs from the Explorer API's `quest_root`, it is normal for Web Explorer not to show that file.

## 7. How should I hand files to the agent?

The most reliable option is to ask the agent to write them in the current active worktree:

```text
Create experiments/analysis/... under the current active worktree,
write the scripts, results, and report there, then record the artifact and update PLAN/CHECKLIST.
```

Files created through Web upload, new file, or editor save also go through backend APIs and are written to the active workspace root.

## 8. Does writing a file mean it is in Git?

No.

A file created inside a git worktree appears in that worktree's `git status`, often as untracked. It enters Git history only after:

- `git add` / `git commit`
- or a DeepScientist artifact / checkpoint flow records it

Also note that a `.ds/worktrees/<name>` worktree has its own git status; it may not appear in the quest root's `git status`.

## 9. Recommended checklist

1. Switch Web Explorer to `FILES`.
2. Refresh Explorer.
3. Check `.quest_root` from the Explorer API.
4. Compare that path with terminal `pwd`.
5. If the file is in another worktree, ask the agent to merge or copy it into the current active worktree.
6. If it should persist, ask the agent to record an artifact or checkpoint.
