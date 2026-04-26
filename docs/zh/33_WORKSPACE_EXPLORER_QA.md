# Workspace Explorer Q&A

这篇解释一个常见困惑：终端里能看到某些文件或文件夹，但 Web 左侧 Explorer 或 Search 看不到。

## 1. Explorer 是否等于本地 quest 根目录？

不完全等于。

Explorer 的 `FILES` 视图展示的是后端当前认为的 active workspace root，而不是永远展示 `<home>/quests/<id>` 根目录。active workspace root 的优先级是：

1. `.ds/research_state.json` 里的 `current_workspace_root`
2. `.ds/research_state.json` 里的 `research_head_worktree_root`
3. quest 根目录

所以同一个 quest 在不同阶段可能会看到不同目录。例如 agent 正在 analysis 或 paper 分支工作时，active workspace root 可能是：

```text
<quest_root>/.ds/worktrees/<branch-worktree-name>
```

这时你在 `<quest_root>` 根目录手动新建的文件夹，不一定会出现在 Explorer 里。

## 2. 哪些文件夹会被 Explorer 跳过？

桌面端 `FILES` 视图会递归展示 active workspace root 下的真实文件和文件夹，但会跳过：

- `.git`
- 当 active root 是 quest 根目录时，`.ds/worktrees`
- `__pycache__`
- `.pytest_cache`

注意：如果 active workspace root 本身就是某个 `.ds/worktrees/<name>`，Explorer 会把这个 worktree 当作根目录展示；它不会因为绝对路径包含 `.ds/worktrees` 就隐藏整个 active worktree。

移动端会额外简化文件树，常见隐藏或截断项包括 `.ds`、`artifacts`、`tmp`、`userfiles` 和较深层目录。

## 3. `FILES`、`SCOPE`、`SNAPSHOT` 有什么区别？

- `FILES`：当前 active workspace root 的实时文件树。
- `SCOPE`：当前图节点、阶段、diff 或被 reveal 的文件范围，不代表完整文件树。
- `SNAPSHOT`：某个 git revision / commit 的只读快照，也不代表当前磁盘最新状态。

如果你想确认终端里新建的文件是否进入 Web 文件树，先切到 `FILES`，再点击刷新。

## 4. 手动在终端新建文件夹，Explorer 会自动出现吗？

不会自动出现。DeepScientist 当前没有监听本地文件系统变化。

手动创建后需要：

1. 确认你写入的是当前 active workspace root。
2. 在 Explorer 里切到 `FILES`。
3. 点击刷新按钮，或刷新页面。

空文件夹可以在 Explorer 里显示，但 Search 通常搜不到空文件夹，因为 Search 主要扫描文件路径和可读文本内容。

## 5. Search 为什么有时搜不到？

Search 搜的是 active workspace root 下的文件，不是所有 worktree 的全集。

Search 还会跳过过大的文件、二进制文件和被 Explorer 过滤掉的路径。它适合查文件名、路径和文本内容，不适合证明某个空目录是否存在。

普通查询应直接输入文本，例如：

```text
run_probe
experiments/analysis
```

不要把普通查询写成 shell glob。旧版前端曾经把普通查询包装成 `*term*`，这会让后端按字面量搜索 `*term*`。新版已兼容这种旧格式，但推荐直接输入关键词。

## 6. 如何确认当前 Explorer 看的到底是哪一个目录？

可以直接查 API：

```bash
curl -s "http://127.0.0.1:<port>/api/quests/<quest_id>/explorer" | jq -r '.quest_root'
```

也可以看 research state：

```bash
cat <quest_root>/.ds/research_state.json
```

重点看：

- `current_workspace_root`
- `research_head_worktree_root`
- `paper_parent_worktree_root`
- `analysis_parent_worktree_root`

如果你终端里的 `pwd` 和 Explorer API 返回的 `quest_root` 不一致，Web 里看不到该文件通常是正常行为。

## 7. 我应该怎么把文件交给 agent 或加入研究流程？

推荐两种方式。

第一，让 agent 在当前 active worktree 写文件：

```text
请在当前 active worktree 下创建 experiments/analysis/...，
把脚本、结果和报告都写入该目录，并记录 artifact / 更新 PLAN 和 CHECKLIST。
```

这样文件更容易被 Explorer、artifact、Canvas 和后续 agent 轮次识别。

第二，通过 Web 的新建文件、上传或编辑器保存。这样会通过后端 API 写入当前 Explorer 对应的 active workspace root。

## 8. 写入文件是否等于进入 Git？

不等于。

只要文件在 git worktree 里创建，它会出现在该 worktree 的 `git status` 中，通常是 untracked。真正进入 Git 历史需要：

- `git add` / `git commit`
- 或 DeepScientist 的 artifact / checkpoint 流程完成对应记录

同时要注意，`.ds/worktrees/<name>` 下的 git 状态属于那个 worktree，不一定体现在 quest 根目录的 `git status` 里。

## 9. 推荐排查顺序

1. 在 Web Explorer 切到 `FILES`。
2. 点击刷新。
3. 用 Explorer API 确认 `.quest_root`。
4. 在终端 `pwd`，确认手动写入目录是否等于 API 返回目录。
5. 如果写在另一个 worktree，切换流程或让 agent 把文件合并/复制到当前 active worktree。
6. 如果要长期保留，要求 agent 记录 artifact 或做 checkpoint。
