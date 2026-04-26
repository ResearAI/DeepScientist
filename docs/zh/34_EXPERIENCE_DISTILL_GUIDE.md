# 34 经验蒸馏指南（Experience Distillation）

这篇文档解释跨 quest 的经验蒸馏管线（opt-in）：一个 quest 如何 review 自己的 completed run、把可复用的 knowledge card 写入全局记忆，并在后续 quest 里把这些卡片作为先验暴露出来。

适合这些场景：

- 你希望一个 quest 学到的硬核教训能被后续 quest 看到，而不是锁在单个 repo 里
- 你希望 `submit_paper_bundle` / `complete_quest` 在 run 没有被蒸馏前不要让 quest 关闭
- 你正在调试一个被 finalize gate 引导到 `distill` 技能的 quest，想知道这个门到底在看什么

如果你需要的是 memory 与 MCP 的整体布局，先看 [07 Memory 与 MCP](./07_MEMORY_AND_MCP.md)。整体的 prompt / skill / MCP 架构在 [14 Prompt、Skills 与 MCP 指南](./14_PROMPT_SKILLS_AND_MCP_GUIDE.md)。

## 1. 一句话总结

启用 `experience_distill` 后，quest 必须把每个 completed run 转化成一条 `distill_review` 制品（以及它引用的 knowledge card），`submit_paper_bundle` 和 quest 关闭才会成功。启用 `recall_priors` 后，stage prompt 会提示 agent 在选 idea / 设计实验前先翻一翻其他 quest 留下的卡片。

## 2. 你是在哪里启用它的

两个开关都在创建项目表单的高级区，最终落到 `quest.yaml.startup_contract`：

- `experience_distill` —— 接受 `on` / `off`，或结构化形式 `{mode: on|off}`。默认 off。
- `recall_priors` —— 接受 `on` / `off`。默认 off。

不带这两个字段的 quest 不会受到本页内容的影响。

## 3. 跨 quest 的知识闭环

端到端形态：

1. quest 跑实验。每一个 `main_experiment` / `experiment` / `analysis.slice` 在 `status: completed` 后都是蒸馏候选。
2. 实验完成后，agent 调用 `decision(action='write'|'finalize')` 时，**finalize gate** 会拦截：如果还有 completed run 没有被任何 `distill_review` 覆盖，guidance 会被改写到 `distill` 技能上。
3. `distill` 技能 review 这一批候选，决定是写一张新的全局 knowledge card 还是给已有的卡 patch，并记录一条 `distill_review` 制品，在其中显式列出 run id 以及对相邻已有卡的 `neighbor_decisions`。
4. 卡片落到 `~/DeepScientist/memory/knowledge/`，作为全局记忆。
5. 下一个 quest 如果开了 `recall_priors`，会在 stage prompt 里看到一条提示，并能用 `memory.list_knowledge_summaries` 这个 MCP 工具浏览前面这些卡。

## 4. Finalize 终结门

终结门挂在 `artifact.record(kind='decision', action='write'|'finalize')` 上。它调用 `evaluate_distill_gate_for_quest(quest_root)`，扫描以下目录：

- `quest_root/artifacts/`
- 每个 `quest_root/.ds/worktrees/*/artifacts/`

候选和 review 通过 `artifact_id` 去重。只要还有任何一个 completed run 没有 `distill_review` 覆盖，门就会：

- 把 `guidance_vm.recommended_skill` 切到 `distill`
- 从 `alternative_routes` 里把 `write` / `finalize` 移除（不留 fallback）
- 在 guidance payload 里暴露 `pending_distill_count` 和 `pending_distill_ids[:5]`

当门已经清空（没有 pending 候选），`guidance_vm` 原样返回，原本的 `write` 推荐自动放行。

## 5. 闭关入口的硬门

除了上面的"软"路由，关闭 quest 的几个入口也强制做同样的多 worktree 检查，防止 runner 跳过 `decision` 直接闭关：

- `artifact.submit_paper_bundle` —— 抛 `ValueError`，错误信息形如 `submit_paper_bundle blocked: experience_distill is on and N completed run(s) lack a distill_review (pending: ...)`。
- `artifact.complete_quest` —— 不再返回 `ok: true`，而是返回 `{ok: false, status: "distill_required", pending_distill_count, pending_distill_ids, message}`。

`experience_distill` 关、没有候选、或 quest 已经处于终结状态时，这两道门都是 no-op。

## 6. `distill` 技能与 `distill_review` 制品

`distill` 技能采取批级 summary-scan 模式：

1. 调用 `artifact.list_distill_candidates` 列出当前活跃工作区下未蒸馏的 completed run。
2. 对每个候选做 summary-scan：打开 run 记录，找出可固化的教训，决定写一张新的全局卡（`memory.write`）还是给已有卡 patch（`memory.patch`）。
3. 对每张被触动的卡，在已有同主题的全局卡上记录一个 `neighbor_decision`：
   - `merge` —— 候选教训和已有卡是同一件事，原地合并
   - `neighbor_but_separate` —— 相关但机制 / 方向不同，两张卡都保留
   - `skip` —— 候选没有补上已有卡未覆盖的内容
4. 最后为整批记录一条 `distill_review` 制品：

```yaml
kind: distill_review
reviewed_run_ids: [run-..., ...]
cards_written:
  - {card_id: knowledge-..., scope: global, action: new|patch, target_run_id: run-...}
neighbor_decisions:
  - {candidate_card_id: knowledge-..., scope: global, decision: merge|neighbor_but_separate|skip,
     target_run_id: run-..., reason: "..."}
notes: "free-form summary"
```

`record(distill_review)` 会校验：`cards_written` / `neighbor_decisions` 里的每个 `target_run_id` 必须出现在 `reviewed_run_ids` 中；`reviewed_run_ids` 里的每个 id 必须在 quest 的某个 workspace 目录下（含 worktree）有对应的 run 制品。卡片 frontmatter 校验额外要求 `subtype: experience` 以及 `lineage` 字段引用 `quest:<id>` 和 `run:<id>`，方便跨 quest 审计。

## 7. 跨 quest 检索（recall_priors）

`recall_priors: on` 时：

- 在 stage skill 的 prompt 里注入一条 `recall_priors_rule` 提示，告诉 agent 在选 idea / 设计实验前先去翻已有的全局 knowledge card。
- `memory` 命名空间下暴露 `memory.list_knowledge_summaries` 工具，支持按 keyword 和 scope 过滤，返回卡片摘要（id、title、scope、tags、excerpt）的排序列表，避免 agent 必须把每张卡通读一遍。

提示和工具是独立的：可以只对一个 quest 开 `recall_priors` 而不开 `experience_distill`，反之亦然。

## 8. MCP 工具

挂在已有 `artifact` / `memory` 命名空间下，没有新增公共命名空间：

- `artifact.list_distill_candidates` —— 当前活跃工作区下未被任何 `distill_review` 覆盖的 completed run。
- `memory.list_knowledge_summaries` —— 跨 quest 的 keyword/scope 过滤式摘要列表。

Codex 自动 approve；Claude 通过 `--allowedTools mcp__memory,mcp__artifact`（命名空间级 allowlist）放行；OpenCode 在默认 `permission_mode: allow` 下放行。

## 9. 重新蒸馏 CLI

对于在终结门上线之前就已经完成的 quest，可以离线重发蒸馏 draft：

```bash
ds distill-quest <quest_id>
```

会在 `~/DeepScientist/drafts/experiences/<quest_id>/` 下为每个未覆盖的 completed run 写一份 draft。agent（或者用户）随后可以 review 这些 draft，再走正常 MCP 路径记录 `distill_review`。如果 quest 不存在，CLI 会向 stderr 打 `Quest not found: <id>` 并以 1 退出。

## 10. 运维注意事项

- **默认 off。** 两个开关默认都关；不动现有 quest。
- **多 worktree 聚合。** 终结门、validator、`list_distill_candidates` 都扫 `quest_root/artifacts` 加上每个 `.ds/worktrees/*/artifacts/`。一个 run 即使只待在 idea worktree 里，也会触发门。
- **语义等价 record 不会重置门。** 重复记录 semantically equivalent 的 `decision` 会复用已有 artifact id；门是按规范化记录评估的，不会被重复 record 绕过。
- **不会自动合并卡片。** 两个 quest 在相似主题上的卡默认保持独立，agent 会用 `neighbor_decision` 显式说明关系；要合并必须 `action: patch`。
- **quest 011 → 012 实例。** 011 写了一张 safety masking（负结果）的卡，012 在 distill_review 中对它选了 `neighbor_but_separate`，理由是 012 的卡描述的是同一概念在推理时 vs 训练时的反向放置，正负结果对照需要保留。

## 11. 失败模式 / 排查

- **提交被拒，错误里写 `lack a distill_review`。** 跑一遍 `distill` 技能、写出 `distill_review` 后重试。若错误里出现的 run id 看上去存在但仍被拒，确认它在某个 workspace 目录下的 run 制品文件确实存在。
- **`distill_review references unknown run artifact_ids`。** validator 已经跨所有 workspace 目录扫描；如果 run 真实存在但仍报错，多半是该 run 的 worktree `_index.jsonl` 没有这条索引，需要修复索引。
- **后续 quest 看不到先验卡。** 先看 `~/DeepScientist/memory/knowledge/_index.jsonl` 是否有对应 `quest_id` 的条目；再确认下一个 quest 是否开了 `recall_priors`、stage prompt 中是否出现 `recall_priors_rule`。
- **`ds doctor`** 当前不显式暴露蒸馏状态；如需排查直接看 `quest_root/artifacts/distill_reviews/` 和规范化 `_index.jsonl`。

## 12. 相关阅读

- [07 Memory 与 MCP](./07_MEMORY_AND_MCP.md) —— memory card 的存储、scope、可见性
- [14 Prompt、Skills 与 MCP 指南](./14_PROMPT_SKILLS_AND_MCP_GUIDE.md) —— stage skill 的拼装、MCP 工具的批准链路
- [02 Start Research 指南](./02_START_RESEARCH_GUIDE.md) —— 创建表单字段如何流入 `startup_contract`
