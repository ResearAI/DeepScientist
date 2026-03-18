import { ArrowUpRight, BookmarkPlus, Bot, CircleHelp, Lock, RotateCcw, Settings2, Sparkles } from 'lucide-react'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'

import { OverlayDialog } from '@/components/home/OverlayDialog'
import { connectorCatalog } from '@/components/settings/connectorCatalog'
import { AnimatedCheckbox } from '@/components/ui/animated-checkbox'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { client } from '@/lib/api'
import { connectorTargetLabel, normalizeConnectorTargets, recentConversationLabel } from '@/lib/connectors'
import { useI18n } from '@/lib/i18n'
import {
  applyStartResearchIntensityPreset,
  compileStartResearchPrompt,
  defaultStartResearchTemplate,
  detectStartResearchIntensity,
  loadStartResearchHistory,
  loadStartResearchTemplate,
  listReferenceStartResearchTemplates,
  listStartResearchIntensityPresets,
  resolveStartResearchContractFields,
  saveStartResearchDraft,
  saveStartResearchTemplate,
  slugifyQuestRepo,
  shouldRecommendStartResearchConnectorBinding,
  type CustomProfile,
  type DecisionPolicy,
  type LaunchMode,
  type ResearchIntensity,
  type StartResearchTemplate,
  type StartResearchTemplateEntry,
} from '@/lib/startResearch'
import { cn } from '@/lib/utils'
import type {
  BaselineRegistryEntry,
  ConnectorAvailabilitySnapshot,
  ConnectorSnapshot,
} from '@/types'

const copy = {
  en: {
    title: 'Start Research',
    body: 'Fill the brief, review the kickoff prompt, then create the project.',
    formTitle: 'Context Form',
    formHint: 'Each field adds concrete context for the first research round.',
    preview: 'Prompt preview',
    previewBody: 'This is the exact kickoff content that will be written into the new project.',
    manual: 'Manual edit active',
    manualTitle: 'Preview edited manually: form is now locked.',
    manualBody: 'Use “Restore form editing” to regenerate the prompt from the left form and unlock inputs.',
    restore: 'Restore form editing',
    template: 'Saved startup template',
    newTemplate: 'New blank form',
    templateHint: 'Reuse a previous startup template when the same research shape appears again.',
    noTemplates: 'No saved templates yet',
    useTemplate: 'Use template',
    latestDraft: 'latest draft',
    questTarget: 'Project target',
    targetHint: 'This launch creates a new project repository and seeds the first PI-facing request.',
    targetMode: 'Project repository',
    targetModeValue: 'Create new project',
    targetRunner: 'Runner',
    targetRunnerValue: 'Codex / local daemon',
    connectorDeliveryLabel: 'Connector delivery',
    connectorDeliveryHelp:
      'Optional. Each enabled connector can bind one target for this new project immediately. Leave a connector unchecked to keep it out of the initial binding set.',
    connectorDeliveryHint: 'Each connector can choose one target. If a target is already bound elsewhere, rebinding this project will replace the old quest binding.',
    connectorSettingsAction: 'Open connector settings',
    connectorEmptyTitle: 'No enabled connector yet',
    connectorEmptyBody:
      'If you want milestone updates outside the web workspace, configure at least one connector first. This is recommended before starting research.',
    connectorUnavailableTitle: 'No selectable connector target yet',
    connectorUnavailableBody:
      'Enabled connectors exist, but no active target is available yet. Send one message to that connector first, or set a default target in Settings.',
    connectorAutoModeLabel: 'No manual selection',
    connectorAutoModeBody: 'Keep the current automatic binding behavior during project creation.',
    connectorSummaryLabel: 'Connector',
    connectorSummaryAuto: 'Automatic',
    connectorSelectedHint: 'If a selected target is already bound to another quest, creating this project will rebind that target here.',
    connectorSourceDefault: 'Default target',
    connectorSourceRecent: 'Recent conversation',
    connectorSourceLast: 'Latest conversation',
    connectorSourceDiscovered: 'Discovered target',
    connectorSourceUnavailable: 'Waiting for first message',
    connectorSuggestTitle: 'Bind a connector first?',
    connectorSuggestBody:
      'For a smoother experience, it is recommended to configure at least one connector before starting research. Then milestones and progress can reach you outside the web workspace too.',
    connectorSuggestLater: 'Not now',
    connectorSuggestGo: 'Go',
    basics: 'Core research brief',
    references: 'Baseline & references',
    policy: 'Research contract',
    launchModeLabel: 'Launch mode',
    launchModeHelp:
      'Standard starts from the ordinary research loop. Custom is for continuing existing state, rebuttal / revision, or a user-defined brief.',
    customProfileLabel: 'Custom profile',
    customProfileHelp:
      'Only shown in custom mode. Use it to tell the agent whether this project should first audit existing state, handle rebuttal work, or follow a freeform brief.',
    entryStateSummaryLabel: 'Existing state summary',
    entryStateSummaryHelp:
      'Briefly describe what already exists, such as a trusted baseline, finished main runs, analysis results, or a paper draft.',
    entryStateSummaryPlaceholder:
      'Example: baseline is already trusted; one main experiment has finished; draft introduction and method sections already exist.',
    reviewSummaryLabel: 'Review / revision summary',
    reviewSummaryHelp:
      'Use this when the project is driven by reviewer comments, a revision request, or a meta-review.',
    reviewSummaryPlaceholder:
      'Example: reviewers asked for stronger ablations, one extra baseline, and a clearer limitation discussion.',
    customBriefLabel: 'Custom brief',
    customBriefHelp:
      'Any extra task-specific instruction that should override the standard full-research launch behavior.',
    customBriefPlaceholder:
      'Example: do not rerun the baseline; first normalize existing results, then decide whether supplementary analysis is still needed.',
    researchIntensityLabel: 'Research intensity',
    researchIntensityHelp:
      'Choose how much the first autonomous research round should attempt before reporting back.',
    decisionPolicyLabel: 'Decision mode',
    decisionPolicyHelp:
      'Autonomous means the agent should keep deciding and continue. User-gated means it may pause for a structured decision when continuation truly depends on you.',
    derivedPolicyTitle: 'Derived execution policy',
    derivedPolicyHint: 'These fields are inferred automatically from the selected intensity and baseline choice.',
    derivedPolicyBudgetLabel: 'Round budget',
    objectives: 'Goals',
    titleLabel: 'Project title',
    titlePlaceholder: 'A short human-readable research title',
    titleHelp: 'This is the display title shown in the workspace and project cards.',
    repoLabel: 'Project ID',
    repoPlaceholder: 'Default: next sequential id such as 001, 002, 003',
    repoHelp: 'By default runtime allocates the next sequential project id. You can override it manually when needed.',
    repoLoading: 'Loading next project id…',
    repoAutoAssigned: 'Assigned by runtime on create',
    goalLabel: 'Primary research request',
    goalPlaceholder: 'State the core scientific question, target paper, hypothesis, and what success would look like.',
    goalHelp: 'This should describe the actual problem to solve, not implementation details.',
    baselineRoot: 'Reusable baseline',
    baselineRootPlaceholder: 'Select a reusable baseline entry (optional)',
    baselineRootHelp:
      'Pick a previously confirmed reusable baseline entry from the global registry. Runtime will attach and confirm it before the new project starts.',
    baselineVariant: 'Baseline variant',
    baselineVariantHelp: 'Optional: choose a specific baseline variant when the entry contains multiple variants.',
    baselineUrls: 'Baseline links',
    baselineUrlsPlaceholder: 'One repository or artifact URL per line',
    baselineUrlsHelp: 'Provide source repositories or artifacts that help recover the baseline quickly.',
    paperUrls: 'Reference papers / repos',
    paperUrlsPlaceholder: 'Relevant papers, code, benchmarks, or leaderboards',
    paperUrlsHelp: 'These references help the agent scope the problem and compare against prior work.',
    runtimeConstraintsLabel: 'Runtime constraints',
    runtimeConstraintsPlaceholder: 'Budget, hardware, privacy, storage, data access, or deadline constraints',
    runtimeConstraintsHelp: 'Anything here becomes a hard operating rule for the first research round.',
    objectivesLabel: 'Goals',
    objectivesPlaceholder: 'Describe what this project should achieve in the first meaningful research cycle.',
    objectivesHelp: 'Use short bullet-like lines such as establish baseline, choose direction, or produce an analysis-ready result.',
    researchPaperLabel: 'Research paper',
    researchPaperHelp:
      'Default on. Keep this enabled when the project must continue into analysis, outline, drafting, and paper bundle work. Turn it off when the project should pursue the strongest justified algorithmic result only.',
    researchPaperEnabled: 'Paper required',
    researchPaperEnabledBody: 'Keep paper-oriented analysis and writing in scope. A strong run alone is not the endpoint.',
    researchPaperDisabled: 'Algorithm-first mode',
    researchPaperDisabledBody: 'Skip default paper drafting and keep iterating toward the strongest justified method.',
    deliveryModeLabel: 'Delivery mode',
    languageLabel: 'User language',
    languageHelp: 'The kickoff prompt and later communication should prefer this language by default.',
    promptRequired: 'Prompt preview cannot be empty.',
    goalRequired: 'Please provide a research request, or edit the preview manually.',
    footer: 'Create project immediately after review.',
    create: 'Create project',
    cancel: 'Cancel',
    intensityOptions: {
      light: {
        title: 'Light baseline pass',
        meta: 'Baseline only · Conservative · 8h',
        body: 'Keep the first round tight. Build or verify a trustworthy baseline and stop instead of overcommitting.',
      },
      balanced: {
        title: 'Balanced direction probe',
        meta: 'Baseline + direction · Balanced · 24h',
        body: 'Secure the baseline, then test one justified direction while still controlling cost and uncertainty.',
      },
      sprint: {
        title: 'Research sprint',
        meta: 'Full research · Aggressive · 48h',
        body: 'Use a larger first round to move through baseline, implementation, and analysis-ready evidence faster.',
      },
    },
    decisionPolicyOptions: {
      autonomous: {
        title: 'Autonomous',
        meta: 'Default',
        body: 'Do not hand ordinary route choices back to the user. Keep going, and report with threaded milestone/progress updates.',
      },
      user_gated: {
        title: 'User-gated',
        meta: 'Blocking decisions allowed',
        body: 'If continuation truly depends on preference or approval, the agent may raise a structured decision request and wait.',
      },
    },
    scopeOptions: {
      baseline_only: 'Baseline only — stop after a strong reusable baseline is established.',
      baseline_plus_direction: 'Baseline + direction — secure baseline and test one justified direction.',
      full_research: 'Full research — baseline, choice of direction, implementation, and analysis readiness.',
    },
    baselineModeOptions: {
      existing: 'Use existing baseline — trust the stored baseline first, then verify it.',
      restore_from_url: 'Restore from URL — rebuild the baseline from source repositories or artifacts.',
      allow_degraded_minimal_reproduction: 'Allow degraded reproduction — accept a weaker but measurable fallback when exact recovery fails.',
      stop_if_insufficient: 'Stop if insufficient — pause instead of pretending the baseline is valid.',
    },
    resourcePolicyOptions: {
      conservative: 'Conservative — keep the first round small, cheap, and low risk.',
      balanced: 'Balanced — move steadily while still controlling cost and uncertainty.',
      aggressive: 'Aggressive — spend more resources to search faster and broader.',
    },
    gitStrategyOptions: {
      branch_per_analysis_then_paper: 'Branch per analysis then paper — split main and analysis work before final integration.',
      semantic_head_plus_controlled_integration: 'Semantic head + controlled integration — keep a cleaner main line and merge more selectively.',
      manual_integration_only: 'Manual integration only — avoid automatic integration and require explicit merge decisions.',
    },
    launchModeOptions: {
      standard: 'Standard — start from the ordinary research graph.',
      custom: 'Custom — continue existing state, rebuttal/revision, or a user-defined brief.',
    },
    customProfileOptions: {
      continue_existing_state: 'Continue existing state — first audit baselines, results, drafts, and current project assets.',
      revision_rebuttal: 'Revision / rebuttal — first interpret reviews, then route extra experiments and writing updates.',
      freeform: 'Freeform — follow the custom brief and use only the skills actually needed.',
    },
  },
  zh: {
    title: 'Start Research',
    body: '填写研究简述，检查 kickoff prompt，然后创建项目。',
    formTitle: '上下文表单',
    formHint: '每一项都在为第一轮研究提供清晰、可执行的上下文。',
    preview: 'Prompt 预览',
    previewBody: '这里展示的是即将写入新项目的完整启动内容。',
    manual: '手工编辑已启用',
    manualTitle: '你已手工修改预览，左侧表单暂时锁定。',
    manualBody: '点击“恢复表单驱动”后，会重新根据左侧表单生成 prompt，并解除锁定。',
    restore: '恢复表单驱动',
    template: '已保存的启动模板',
    newTemplate: '新建空白表单',
    templateHint: '当研究形态相近时，可以快速复用过去的启动模板。',
    noTemplates: '还没有已保存模板',
    useTemplate: '使用模板',
    latestDraft: '最近草稿',
    questTarget: '项目目标',
    targetHint: '当前启动会创建一个新的项目仓库，并写入第一条面向 PI 的启动请求。',
    targetMode: '项目仓库',
    targetModeValue: '创建新项目',
    targetRunner: 'Runner',
    targetRunnerValue: 'Codex / 本地 daemon',
    connectorDeliveryLabel: '连接器投递',
    connectorDeliveryHelp:
      '可选。每个已启用的 connector 都可以为新项目选择 1 个目标会话；不勾选则表示这个 connector 暂不参与初始绑定。',
    connectorDeliveryHint: '每个 connector 最多选择 1 个目标；如果该目标已绑定到别的 quest，创建当前项目时会自动替换原绑定。',
    connectorSettingsAction: '打开 Connector 设置',
    connectorEmptyTitle: '还没有启用的 connector',
    connectorEmptyBody:
      '如果你希望在网页之外接收里程碑更新，建议先配置至少一个 connector，再启动研究。',
    connectorUnavailableTitle: '还没有可选的 connector 目标',
    connectorUnavailableBody:
      '已有启用的 connector，但当前还没有可用目标。请先给对应 connector 发一条消息，或在 Settings 中设置默认目标。',
    connectorAutoModeLabel: '不手动指定',
    connectorAutoModeBody: '创建项目时保持当前默认的自动绑定行为。',
    connectorSummaryLabel: '连接器',
    connectorSummaryAuto: '自动',
    connectorSelectedHint: '如果当前选中的目标已经绑定到别的 quest，创建后会自动重绑到当前项目。',
    connectorSourceDefault: '默认目标',
    connectorSourceRecent: '最近会话',
    connectorSourceLast: '最新会话',
    connectorSourceDiscovered: '已发现目标',
    connectorSourceUnavailable: '等待第一条消息',
    connectorSuggestTitle: '建议先绑定一个 Connector',
    connectorSuggestBody:
      '为了获得更顺滑的使用体验，建议你先配置至少一个 connector。这样开始研究后，里程碑和进展也能同步发到网页之外。',
    connectorSuggestLater: '暂不',
    connectorSuggestGo: '前往',
    basics: '核心研究简述',
    references: 'Baseline 与参考',
    policy: '研究合同',
    launchModeLabel: '启动模式',
    launchModeHelp:
      'Standard 表示按普通科研主线启动；Custom 用于继续已有状态、处理 rebuttal / revision，或执行自定义研究任务。',
    customProfileLabel: '自定义档位',
    customProfileHelp:
      '仅在 Custom 模式下显示。用来告诉 agent 这是继续已有状态、处理审稿回复，还是一个自由定制任务。',
    entryStateSummaryLabel: '已有状态摘要',
    entryStateSummaryHelp:
      '简要写清当前已经有什么，例如可信 baseline、主实验结果、分析结果、论文草稿等。',
    entryStateSummaryPlaceholder:
      '例如：baseline 已可信；一个主实验已完成；引言和方法草稿已存在。',
    reviewSummaryLabel: '审稿 / 修改摘要',
    reviewSummaryHelp:
      '当项目由 reviewer comments、revision request 或 meta-review 驱动时，在这里概括主要要求。',
    reviewSummaryPlaceholder:
      '例如：reviewer 要求补更强的 ablation、增加一个 baseline、并澄清 limitation。',
    customBriefLabel: '自定义说明',
    customBriefHelp:
      '任何需要覆盖标准 full research 启动方式的额外任务说明，都可以写在这里。',
    customBriefPlaceholder:
      '例如：不要重新跑 baseline；先整理现有结果，再决定是否需要额外分析实验。',
    researchIntensityLabel: '研究投入强度',
    researchIntensityHelp: '只需决定第一轮自治研究准备投入到什么程度，其余执行策略会自动推导。',
    decisionPolicyLabel: '决策模式',
    decisionPolicyHelp:
      'Autonomous 表示 agent 默认自行判断并继续推进；User-gated 表示只有确实依赖你的偏好或批准时，才允许暂停并发起结构化决策请求。',
    derivedPolicyTitle: '自动推导的执行策略',
    derivedPolicyHint: '这些字段会根据研究强度和是否选中已有 baseline 自动生成，无需手动逐项配置。',
    derivedPolicyBudgetLabel: '每轮预算',
    objectives: '目标',
    titleLabel: '课题标题',
    titlePlaceholder: '一个简洁易读的研究标题',
    titleHelp: '这是工作区和项目卡片中展示给用户看的标题。',
    repoLabel: '项目 ID',
    repoPlaceholder: '默认使用下一个顺序编号，例如 001、002、003',
    repoHelp: '默认由 runtime 分配下一个顺序项目 ID；如有需要你也可以手动覆盖。',
    repoLoading: '正在加载下一个项目 ID…',
    repoAutoAssigned: '创建时由 runtime 分配',
    goalLabel: '核心研究请求',
    goalPlaceholder: '清楚说明科学问题、目标论文、核心假设，以及什么结果算成功。',
    goalHelp: '这里应该描述真正要解决的问题，而不是过早写实现细节。',
    baselineRoot: '复用 Baseline',
    baselineRootPlaceholder: '选择一个可复用的 baseline 条目（可选）',
    baselineRootHelp: '选择全局 registry 中已经确认可复用的 baseline。运行时会在新项目创建前自动 attach 并 confirm；留空则从零开始建立 baseline。',
    baselineVariant: 'Baseline variant',
    baselineVariantHelp: '可选：当 baseline entry 里包含多个 variant 时，可以在这里指定。',
    baselineUrls: 'Baseline 链接',
    baselineUrlsPlaceholder: '每行一个仓库或 artifact 链接',
    baselineUrlsHelp: '这些链接用于帮助系统更快恢复或修复 baseline。',
    paperUrls: '参考论文 / 仓库',
    paperUrlsPlaceholder: '相关论文、代码、benchmark 或 leaderboard',
    paperUrlsHelp: '这些参考资料会帮助 agent 更好地界定问题和比较工作。',
    runtimeConstraintsLabel: '运行约束',
    runtimeConstraintsPlaceholder: '预算、硬件、隐私、存储、数据访问、截止时间等限制',
    runtimeConstraintsHelp: '写在这里的内容会被视为第一轮研究中的硬性运行约束。',
    objectivesLabel: '目标',
    objectivesPlaceholder: '描述这一轮研究需要达成什么，例如建立 baseline、筛选方向、得到可分析结果等。',
    objectivesHelp: '建议按短句逐行写明，例如“建立可信 baseline”“判断是否值得实现某方向”。',
    researchPaperLabel: '研究论文',
    researchPaperHelp:
      '默认开启。若本次项目必须继续推进到分析、写作大纲、草稿与 paper bundle，请保持开启；若只追求最强且有依据的算法结果，可关闭。',
    researchPaperEnabled: '需要研究论文',
    researchPaperEnabledBody: '保持论文导向的分析与写作流程。单次较强实验结果本身不构成终点。',
    researchPaperDisabled: '仅追求最佳算法',
    researchPaperDisabledBody: '默认不进入论文写作，重点持续迭代并追求更强、证据更扎实的方法结果。',
    deliveryModeLabel: '交付模式',
    languageLabel: '用户语言',
    languageHelp: '默认希望 kickoff prompt 与后续交流优先使用的语言。',
    promptRequired: 'Prompt 预览不能为空。',
    goalRequired: '请填写研究请求，或直接在右侧手工编辑 prompt。',
    footer: '确认后会立即创建项目。',
    create: '创建项目',
    cancel: '取消',
    intensityOptions: {
      light: {
        title: '轻量基线轮',
        meta: '仅 baseline · 保守 · 8 小时',
        body: '把第一轮收紧，优先建立或验证可信 baseline；证据不足时直接停止并汇报。',
      },
      balanced: {
        title: '平衡方向试探',
        meta: 'baseline + 方向 · 平衡 · 24 小时',
        body: '先建立可信 baseline，再在受控预算内验证一个有依据的改进方向。',
      },
      sprint: {
        title: '研究冲刺轮',
        meta: '完整研究 · 激进 · 48 小时',
        body: '给第一轮更大的预算，尽快推进到 baseline、实现与分析准备就绪。',
      },
    },
    decisionPolicyOptions: {
      autonomous: {
        title: 'Autonomous',
        meta: '默认',
        body: '普通路线选择不再交给用户，agent 需要自己判断并继续，只通过进度或里程碑持续汇报。',
      },
      user_gated: {
        title: 'User-gated',
        meta: '允许阻塞决策',
        body: '只有在继续推进确实依赖用户偏好或批准时，agent 才可以发起结构化决策请求并等待。',
      },
    },
    scopeOptions: {
      baseline_only: '仅 baseline —— 建立一个可信且可复用的 baseline 后即停止本轮。',
      baseline_plus_direction: 'baseline + 方向 —— 先建立 baseline，再验证一个有依据的改进方向。',
      full_research: '完整研究 —— baseline、方向选择、实现推进，以及进入分析准备阶段。',
    },
    baselineModeOptions: {
      existing: '使用现有 baseline —— 优先复用已存储的 baseline，并先验证其可信度。',
      restore_from_url: '从链接恢复 —— 根据仓库或 artifact 链接恢复 baseline。',
      allow_degraded_minimal_reproduction: '允许降级复现 —— 精确恢复失败时，可接受较弱但可测的替代 baseline。',
      stop_if_insufficient: '证据不足则停止 —— 宁可暂停，也不伪造一个不可信的 baseline。',
    },
    resourcePolicyOptions: {
      conservative: '保守 —— 第一轮尽量小步、低成本、低风险。',
      balanced: '平衡 —— 稳步推进，同时控制成本与不确定性。',
      aggressive: '激进 —— 愿意投入更多资源来更快、更广地探索。',
    },
    gitStrategyOptions: {
      branch_per_analysis_then_paper: '主实验 / 分析分支拆分 —— 先拆开主实验与分析实验，再统一汇总写作。',
      semantic_head_plus_controlled_integration: '语义主线 + 受控集成 —— 保持更干净的主线，只合并经过控制的结果。',
      manual_integration_only: '仅手动集成 —— 避免自动集成，所有合并都需要显式决策。',
    },
    launchModeOptions: {
      standard: 'Standard —— 按普通科研图谱启动。',
      custom: 'Custom —— 继续已有状态、处理 rebuttal/revision，或执行用户自定义任务。',
    },
    customProfileOptions: {
      continue_existing_state: '继续已有状态 —— 先审计 baseline、结果、草稿和现有项目资产。',
      revision_rebuttal: '审稿修改 / rebuttal —— 先解析 review，再决定补实验和改文。',
      freeform: '自由模式 —— 以自定义 brief 为主，只打开真正需要的 skills。',
    },
  },
} as const

const selectClassName =
  'h-9 rounded-[10px] border border-[rgba(45,42,38,0.1)] bg-white/78 px-3 text-xs text-[rgba(38,36,33,0.95)] outline-none transition focus:border-[rgba(45,42,38,0.18)] dark:border-[rgba(45,42,38,0.1)] dark:bg-white/82 dark:text-[rgba(38,36,33,0.95)] dark:focus:border-[rgba(45,42,38,0.18)]'

const panelClass =
  'rounded-xl border border-[rgba(45,42,38,0.09)] bg-[rgba(255,255,255,0.76)] shadow-[0_12px_30px_-24px_rgba(45,42,38,0.32)] backdrop-blur-xl dark:border-[rgba(45,42,38,0.09)] dark:bg-[rgba(255,255,255,0.82)]'

const connectorCatalogByName = new Map(connectorCatalog.map((entry) => [entry.name, entry]))

type StartConnectorChoice = {
  name: string
  label: string
  subtitle: string
  transport: string
  connectionState: string
  targets: Array<{
    conversationId: string
    targetLabel: string
    compactLabel: string
    detailLabel: string
    sourceKind: 'default' | 'recent' | 'last' | 'discovered'
    boundQuestId?: string | null
    boundQuestTitle?: string | null
    warning?: string | null
  }>
}

function titleCaseConnector(name: string) {
  const normalized = String(name || '').trim()
  if (!normalized) return 'Connector'
  if (normalized.toLowerCase() === 'qq') return 'QQ'
  return normalized.charAt(0).toUpperCase() + normalized.slice(1)
}

function parseConversationLabel(value?: string | null) {
  const raw = String(value || '').trim()
  if (!raw) return ''
  const parts = raw.split(':', 3)
  if (parts.length !== 3) return raw
  const [, chatType, chatId] = parts
  if (!chatType || !chatId) return raw
  return `${chatType} · ${chatId}`
}

function shortChatId(value?: string | null, keep = 8) {
  const normalized = String(value || '').trim()
  if (!normalized) return ''
  if (normalized.length <= keep) return normalized
  return normalized.slice(-keep)
}

function compactConnectorTargetOption(args: {
  profileLabel?: string | null
  chatType?: string | null
  chatId?: string | null
  fallbackLabel?: string | null
  duplicatedProfileLabel?: boolean
}) {
  const profileLabel = String(args.profileLabel || '').trim()
  const chatType = String(args.chatType || '').trim()
  const chatId = String(args.chatId || '').trim()
  if (profileLabel) {
    if (!args.duplicatedProfileLabel) {
      return profileLabel
    }
    return [profileLabel, chatType || 'direct', shortChatId(chatId)].filter(Boolean).join(' · ')
  }
  return clampText(String(args.fallbackLabel || '').trim() || [chatType, shortChatId(chatId)].filter(Boolean).join(' · '), 44)
}

function resolveStartConnectorChoice(snapshot: ConnectorSnapshot): StartConnectorChoice {
  const catalogEntry = connectorCatalogByName.get(snapshot.name as (typeof connectorCatalog)[number]['name'])
  const normalizedConnectorTargets = normalizeConnectorTargets(snapshot)
  const profileLabelCounts = normalizedConnectorTargets.reduce<Record<string, number>>((acc, target) => {
    const key = String(target.profile_label || '').trim()
    if (!key) return acc
    acc[key] = (acc[key] || 0) + 1
    return acc
  }, {})
  const normalizedTargets = normalizedConnectorTargets.map((target) => ({
      conversationId: target.conversation_id,
      targetLabel: connectorTargetLabel(target),
      compactLabel: compactConnectorTargetOption({
        profileLabel: target.profile_label,
        chatType: target.chat_type,
        chatId: target.chat_id,
        fallbackLabel: connectorTargetLabel(target),
        duplicatedProfileLabel: Boolean(target.profile_label && profileLabelCounts[String(target.profile_label).trim()] > 1),
      }),
      detailLabel: [target.chat_type, shortChatId(target.chat_id)].filter(Boolean).join(' · '),
      sourceKind: target.is_default
        ? ('default' as const)
        : target.source === 'recent_activity' || target.source === 'recent_inbound' || target.source === 'outbound_delivery'
          ? ('recent' as const)
          : target.source === 'recent_runtime_activity'
            ? ('last' as const)
            : ('discovered' as const),
      boundQuestId: target.bound_quest_id || null,
      boundQuestTitle: target.bound_quest_title || null,
      warning: target.warning || null,
    }))

  if (normalizedTargets.length === 0) {
    const recentConversation = Array.isArray(snapshot.recent_conversations) ? snapshot.recent_conversations[0] : null
    const lastConversationId = String(snapshot.last_conversation_id || '').trim() || null
    if (recentConversation?.conversation_id) {
      normalizedTargets.push({
        conversationId: recentConversation.conversation_id,
        targetLabel: recentConversationLabel(recentConversation),
        compactLabel: compactConnectorTargetOption({
          profileLabel: recentConversation.profile_label,
          chatType: recentConversation.chat_type,
          chatId: recentConversation.chat_id,
          fallbackLabel: recentConversationLabel(recentConversation),
        }),
        detailLabel: [recentConversation.chat_type, shortChatId(recentConversation.chat_id)].filter(Boolean).join(' · '),
        sourceKind: 'recent',
        boundQuestId: null,
        boundQuestTitle: null,
        warning: null,
      })
    } else if (lastConversationId) {
      normalizedTargets.push({
        conversationId: lastConversationId,
        targetLabel: parseConversationLabel(lastConversationId),
        compactLabel: clampText(parseConversationLabel(lastConversationId), 44),
        detailLabel: clampText(lastConversationId, 36),
        sourceKind: 'last',
        boundQuestId: null,
        boundQuestTitle: null,
        warning: null,
      })
    }
  }

  return {
    name: snapshot.name,
    label: catalogEntry?.label || titleCaseConnector(snapshot.name),
    subtitle: catalogEntry?.subtitle || '',
    transport: String(snapshot.transport || snapshot.display_mode || snapshot.mode || '').trim(),
    connectionState: String(snapshot.connection_state || '').trim(),
    targets: normalizedTargets,
  }
}

function FieldHelp({
  text,
}: {
  text: string
}) {
  return (
    <div className="group relative inline-flex">
      <button
        type="button"
        tabIndex={-1}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full text-[rgba(107,103,97,0.78)] transition hover:text-[rgba(45,42,38,0.95)] dark:text-[rgba(107,103,97,0.78)] dark:hover:text-[rgba(45,42,38,0.95)]"
        aria-label={text}
      >
        <CircleHelp className="h-3.5 w-3.5" />
      </button>
      <div className="pointer-events-none absolute left-1/2 top-[calc(100%+0.45rem)] z-20 hidden w-64 -translate-x-1/2 rounded-[14px] border border-[rgba(45,42,38,0.1)] bg-[rgba(255,255,255,0.97)] px-3 py-2 text-[11px] leading-5 text-[rgba(56,52,47,0.92)] shadow-[0_20px_40px_-28px_rgba(45,42,38,0.45)] group-hover:block dark:border-[rgba(45,42,38,0.1)] dark:bg-[rgba(255,255,255,0.97)] dark:text-[rgba(56,52,47,0.92)]">
        {text}
      </div>
    </div>
  )
}

function InlineField({
  label,
  help,
  hint,
  children,
}: {
  label: string
  help?: string
  hint?: string
  children: ReactNode
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1.5 text-[11px] font-medium text-[rgba(75,73,69,0.78)] dark:text-[rgba(75,73,69,0.78)]">
        <span>{label}</span>
        {help ? <FieldHelp text={help} /> : null}
      </div>
      {hint ? <div className="text-[11px] leading-5 text-[rgba(107,103,97,0.72)] dark:text-[rgba(107,103,97,0.72)]">{hint}</div> : null}
      {children}
    </div>
  )
}

type ChoiceItem<T extends string> = {
  value: T
  title: string
  description: string
  meta?: string
}

function ChoiceField<T extends string>({
  label,
  help,
  hint,
  value,
  items,
  onChange,
  disabled = false,
}: {
  label: string
  help?: string
  hint?: string
  value: T | null
  items: ChoiceItem<T>[]
  onChange: (value: T) => void
  disabled?: boolean
}) {
  return (
    <InlineField label={label} help={help} hint={hint}>
      <div role="radiogroup" aria-label={label} className="space-y-2">
        {items.map((item) => {
          const active = item.value === value
          return (
            <button
              key={item.value}
              type="button"
              role="radio"
              aria-checked={active}
              disabled={disabled}
              onClick={() => onChange(item.value)}
              className={cn(
                'flex w-full items-start gap-3 rounded-[14px] border px-3 py-3 text-left transition',
                'disabled:cursor-not-allowed disabled:opacity-60',
                active
                  ? 'border-[rgba(126,77,42,0.32)] bg-[rgba(126,77,42,0.08)] shadow-[0_14px_26px_-22px_rgba(90,56,35,0.55)] dark:border-[rgba(126,77,42,0.32)] dark:bg-[rgba(126,77,42,0.08)]'
                  : 'border-[rgba(45,42,38,0.08)] bg-white/60 hover:border-[rgba(45,42,38,0.14)] hover:bg-white/82 dark:border-[rgba(45,42,38,0.08)] dark:bg-white/70 dark:hover:border-[rgba(45,42,38,0.14)] dark:hover:bg-white/86'
              )}
            >
              <span
                aria-hidden
                className={cn(
                  'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition',
                  active
                    ? 'border-[rgba(126,77,42,0.78)] bg-[rgba(126,77,42,0.14)] dark:border-[rgba(126,77,42,0.78)] dark:bg-[rgba(126,77,42,0.14)]'
                    : 'border-[rgba(107,103,97,0.34)] bg-transparent dark:border-[rgba(107,103,97,0.34)]'
                )}
              >
                <span
                  className={cn(
                    'h-1.5 w-1.5 rounded-full transition',
                    active ? 'bg-[rgba(126,77,42,0.92)] dark:bg-[rgba(126,77,42,0.92)]' : 'bg-transparent'
                  )}
                />
              </span>
              <span className="min-w-0">
                <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="text-xs font-semibold text-[rgba(38,36,33,0.95)] dark:text-[rgba(38,36,33,0.95)]">
                    {item.title}
                  </span>
                  {item.meta ? (
                    <span className="text-[10px] uppercase tracking-[0.16em] text-[rgba(107,103,97,0.78)] dark:text-[rgba(107,103,97,0.78)]">
                      {item.meta}
                    </span>
                  ) : null}
                </span>
                <span className="mt-1 block text-[11px] leading-5 text-[rgba(86,82,77,0.82)] dark:text-[rgba(86,82,77,0.82)]">
                  {item.description}
                </span>
              </span>
            </button>
          )
        })}
      </div>
    </InlineField>
  )
}

function ConnectorChoiceField({
  label,
  help,
  hint,
  items,
  value,
  loading = false,
  error,
  emptyTitle,
  emptyBody,
  unavailableTitle,
  unavailableBody,
  settingsActionLabel,
  autoModeLabel,
  autoModeBody,
  selectedHint,
  sourceLabels,
  locale,
  onOpenSettings,
  onChange,
}: {
  label: string
  help?: string
  hint?: string
  items: StartConnectorChoice[]
  value: Record<string, string | null>
  loading?: boolean
  error?: string | null
  emptyTitle: string
  emptyBody: string
  unavailableTitle: string
  unavailableBody: string
  settingsActionLabel: string
  autoModeLabel: string
  autoModeBody: string
  selectedHint: string
  sourceLabels: Record<'default' | 'recent' | 'last' | 'discovered' | 'unavailable', string>
  locale: 'en' | 'zh'
  onOpenSettings: () => void
  onChange: (connectorName: string, next: string | null) => void
}) {
  const enabledItems = items
  const selectableItems = enabledItems.filter((item) => item.targets.length > 0)
  const hasUnavailable = enabledItems.some((item) => item.targets.length === 0)
  const selectedCount = Object.values(value).filter(Boolean).length

  return (
    <InlineField label={label} help={help} hint={hint}>
      {loading ? (
        <div className="rounded-[14px] border border-[rgba(45,42,38,0.08)] bg-white/60 px-3 py-3 text-[11px] leading-5 text-[rgba(86,82,77,0.82)] dark:border-[rgba(45,42,38,0.08)] dark:bg-white/70 dark:text-[rgba(86,82,77,0.82)]">
          Loading connectors…
        </div>
      ) : enabledItems.length === 0 ? (
        <div className="rounded-[16px] border border-dashed border-[rgba(45,42,38,0.12)] bg-white/52 px-4 py-4 dark:border-[rgba(45,42,38,0.12)] dark:bg-white/64">
          <div className="text-xs font-semibold text-[rgba(38,36,33,0.95)] dark:text-[rgba(38,36,33,0.95)]">
            {emptyTitle}
          </div>
          <div className="mt-1 text-[11px] leading-5 text-[rgba(86,82,77,0.82)] dark:text-[rgba(86,82,77,0.82)]">
            {emptyBody}
          </div>
          <button
            type="button"
            onClick={onOpenSettings}
            className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-[rgba(45,42,38,0.1)] bg-white/82 px-3 py-1.5 text-[11px] font-medium text-[rgba(38,36,33,0.95)] transition hover:bg-white dark:border-[rgba(45,42,38,0.1)] dark:bg-white/88"
          >
            <Settings2 className="h-3.5 w-3.5" />
            {settingsActionLabel}
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="divide-y divide-[rgba(45,42,38,0.08)] dark:divide-[rgba(45,42,38,0.08)]">
            {enabledItems.map((item) => {
              const selectedConversationId = value[item.name] || null
              const available = item.targets.length > 0
              const selectedTarget = item.targets.find((target) => target.conversationId === selectedConversationId) || null
              const catalogEntry = connectorCatalogByName.get(item.name as (typeof connectorCatalog)[number]['name'])
              const Icon = catalogEntry?.icon || Bot

              return (
                <div
                  key={item.name}
                  className="grid grid-cols-1 gap-3 py-3 first:pt-0 last:pb-0 sm:grid-cols-[minmax(0,210px)_minmax(0,1fr)] sm:items-start"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[12px] border border-[rgba(45,42,38,0.08)] bg-white/82 text-[rgba(56,52,47,0.9)] dark:border-[rgba(45,42,38,0.08)] dark:bg-white/88">
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <div className="truncate text-xs font-semibold text-[rgba(38,36,33,0.95)] dark:text-[rgba(38,36,33,0.95)]">
                        {item.label}
                      </div>
                      <div className="mt-0.5 text-[10px] uppercase tracking-[0.14em] text-[rgba(107,103,97,0.78)] dark:text-[rgba(107,103,97,0.78)]">
                        {item.connectionState || item.transport || 'connector'}
                      </div>
                    </div>
                  </div>

                  <div className="min-w-0 space-y-1.5">
                    <select
                      value={selectedConversationId || ''}
                      onChange={(event) => onChange(item.name, event.target.value || null)}
                      className={cn(selectClassName, 'w-full min-w-0')}
                      disabled={!available}
                    >
                      <option value="">{autoModeLabel}</option>
                      {item.targets.map((target) => (
                        <option key={target.conversationId} value={target.conversationId}>
                          {target.compactLabel}
                        </option>
                      ))}
                    </select>
                    <div className="text-[11px] leading-5 text-[rgba(107,103,97,0.78)] dark:text-[rgba(107,103,97,0.78)]">
                      {!available
                        ? unavailableBody
                        : selectedTarget
                          ? selectedTarget.boundQuestId
                            ? `${sourceLabels[selectedTarget.sourceKind]} · ${selectedTarget.boundQuestId}${selectedTarget.boundQuestTitle ? ` · ${clampText(selectedTarget.boundQuestTitle, 28)}` : ''}`
                            : `${sourceLabels[selectedTarget.sourceKind]} · ${selectedTarget.detailLabel}`
                          : autoModeBody}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          <div className="px-1 text-[11px] leading-5 text-[rgba(107,103,97,0.78)] dark:text-[rgba(107,103,97,0.78)]">
            {selectedCount > 0
              ? locale === 'zh'
                ? `已选择 ${selectedCount} 个 connector。${selectedHint}`
                : `${selectedCount} connector(s) selected. ${selectedHint}`
              : `${autoModeLabel}. ${autoModeBody}`}
          </div>

          {hasUnavailable && selectableItems.length === 0 ? (
            <div className="rounded-[14px] border border-dashed border-[rgba(45,42,38,0.12)] bg-white/52 px-4 py-4 dark:border-[rgba(45,42,38,0.12)] dark:bg-white/64">
              <div className="text-xs font-semibold text-[rgba(38,36,33,0.95)] dark:text-[rgba(38,36,33,0.95)]">
                {unavailableTitle}
              </div>
              <div className="mt-1 text-[11px] leading-5 text-[rgba(86,82,77,0.82)] dark:text-[rgba(86,82,77,0.82)]">
                {unavailableBody}
              </div>
              <button
                type="button"
                onClick={onOpenSettings}
                className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-[rgba(45,42,38,0.1)] bg-white/82 px-3 py-1.5 text-[11px] font-medium text-[rgba(38,36,33,0.95)] transition hover:bg-white dark:border-[rgba(45,42,38,0.1)] dark:bg-white/88"
              >
                <Settings2 className="h-3.5 w-3.5" />
                {settingsActionLabel}
              </button>
            </div>
          ) : null}

          {error ? <div className="text-[11px] leading-5 text-[#9a1b1b]">{error}</div> : null}
        </div>
      )}
    </InlineField>
  )
}

function SectionCard({
  title,
  children,
  muted = false,
}: {
  title: string
  children: ReactNode
  muted?: boolean
}) {
  return (
    <div
      className={cn(
        'rounded-[18px] border p-3 sm:rounded-xl',
        muted
          ? 'border-[rgba(45,42,38,0.08)] bg-[rgba(244,239,233,0.56)] dark:border-[rgba(45,42,38,0.08)] dark:bg-[rgba(244,239,233,0.66)] sm:bg-[rgba(244,239,233,0.62)] sm:dark:bg-[rgba(244,239,233,0.72)]'
          : 'border-[rgba(45,42,38,0.08)] bg-white/72 dark:border-[rgba(45,42,38,0.08)] dark:bg-white/82 sm:shadow-[0_12px_30px_-24px_rgba(45,42,38,0.32)] sm:backdrop-blur-xl'
      )}
    >
      <div className="text-sm font-semibold text-[rgba(38,36,33,0.95)] dark:text-[rgba(38,36,33,0.95)]">{title}</div>
      <div className="mt-3 space-y-3">{children}</div>
    </div>
  )
}

function compactTemplateLabel(item: StartResearchTemplateEntry, locale: 'en' | 'zh') {
  const goal = item.goal || (locale === 'zh' ? '未命名模板' : 'Untitled template')
  const title = item.title ? `${item.title} · ` : ''
  return `${title}${goal}`.slice(0, 72)
}

function splitOptionCopy(text: string) {
  const [title, ...rest] = text.split(/\s+[—-]{1,2}\s+/)
  return {
    title: title.trim(),
    description: rest.join(' — ').trim() || title.trim(),
  }
}

function sanitizeLines(value: string) {
  return String(value || '')
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

function clampText(value: string, limit = 48) {
  const normalized = String(value || '').replace(/\s+/g, ' ').trim()
  if (!normalized) return ''
  if (normalized.length <= limit) return normalized
  return `${normalized.slice(0, Math.max(0, limit - 1)).trimEnd()}…`
}

function resolveBaselineMetricLabel(entry: BaselineRegistryEntry | null, locale: 'en' | 'zh') {
  if (!entry) return locale === 'zh' ? '暂无主指标' : 'No primary metric'
  const primaryMetric = entry.primary_metric
  if (primaryMetric && typeof primaryMetric === 'object') {
    const metricKey = String(
      (primaryMetric as Record<string, unknown>).metric_id ||
        (primaryMetric as Record<string, unknown>).name ||
        ''
    ).trim()
    const metricValue = (primaryMetric as Record<string, unknown>).value
    if (metricKey && metricValue != null) {
      return `${metricKey}: ${String(metricValue)}`
    }
  }
  const metricsSummary = entry.metrics_summary
  if (metricsSummary && typeof metricsSummary === 'object') {
    const firstMetric = Object.entries(metricsSummary).find(([, value]) => value != null)
    if (firstMetric) {
      return `${firstMetric[0]}: ${String(firstMetric[1])}`
    }
  }
  return locale === 'zh' ? '暂无主指标' : 'No primary metric'
}

function formatBaselineTimestamp(value: string | null | undefined, locale: 'en' | 'zh') {
  if (!value) return locale === 'zh' ? '未知' : 'Unknown'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(locale === 'zh' ? 'zh-CN' : 'en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(date)
}

function formatBaselineStatus(value: string | null | undefined, locale: 'en' | 'zh') {
  const normalized = String(value || '').trim()
  if (!normalized) return locale === 'zh' ? '未知' : 'unknown'
  return normalized.replace(/_/g, ' ')
}

export function CreateProjectDialog({
  open,
  loading,
  error,
  initialGoal = '',
  onClose,
  onCreate,
}: {
  open: boolean
  loading?: boolean
  error?: string | null
  initialGoal?: string
  onClose: () => void
  onCreate: (payload: {
    title: string
    goal: string
    quest_id?: string
    requested_connector_bindings?: Array<{ connector: string; conversation_id?: string | null }>
    requested_baseline_ref?: { baseline_id: string; variant_id?: string | null } | null
    startup_contract?: Record<string, unknown> | null
  }) => Promise<void>
}) {
  const navigate = useNavigate()
  const { locale } = useI18n()
  const t = copy[locale]
  const [form, setForm] = useState<StartResearchTemplate>(defaultStartResearchTemplate(locale))
  const [promptDraft, setPromptDraft] = useState('')
  const [manualOverride, setManualOverride] = useState(false)
  const [questIdManualOverride, setQuestIdManualOverride] = useState(false)
  const [suggestedQuestId, setSuggestedQuestId] = useState('')
  const [suggestedQuestIdLoading, setSuggestedQuestIdLoading] = useState(false)
  const [templates, setTemplates] = useState<StartResearchTemplateEntry[]>([])
  const [selectedTemplateId, setSelectedTemplateId] = useState('__latest__')
  const [baselineEntries, setBaselineEntries] = useState<BaselineRegistryEntry[]>([])
  const [baselineEntriesLoading, setBaselineEntriesLoading] = useState(false)
  const [baselineEntriesError, setBaselineEntriesError] = useState<string | null>(null)
  const [connectors, setConnectors] = useState<ConnectorSnapshot[]>([])
  const [connectorsLoading, setConnectorsLoading] = useState(false)
  const [connectorsError, setConnectorsError] = useState<string | null>(null)
  const [connectorAvailability, setConnectorAvailability] = useState<ConnectorAvailabilitySnapshot | null>(null)
  const [connectorAvailabilityLoading, setConnectorAvailabilityLoading] = useState(false)
  const [connectorAvailabilityResolved, setConnectorAvailabilityResolved] = useState(false)
  const [connectorAvailabilityError, setConnectorAvailabilityError] = useState<string | null>(null)
  const [selectedConnectorBindings, setSelectedConnectorBindings] = useState<Record<string, string | null>>({})
  const [showConnectorRecommendation, setShowConnectorRecommendation] = useState(false)
  const [connectorRecommendationHandled, setConnectorRecommendationHandled] = useState(false)
  const referenceTemplates = useMemo(() => listReferenceStartResearchTemplates(), [])

  const activeResearchIntensity = useMemo(
    () => detectStartResearchIntensity(form),
    [form.baseline_id, form.research_intensity]
  )

  const intensityItems = useMemo(
    () =>
      listStartResearchIntensityPresets().map((preset) => ({
        value: preset.id,
        title: t.intensityOptions[preset.id].title,
        meta: t.intensityOptions[preset.id].meta,
        description: t.intensityOptions[preset.id].body,
      })),
    [t]
  )

  const decisionPolicyItems = useMemo(
    () =>
      (['autonomous', 'user_gated'] as const).map((value) => ({
        value,
        title: t.decisionPolicyOptions[value].title,
        meta: t.decisionPolicyOptions[value].meta,
        description: t.decisionPolicyOptions[value].body,
      })),
    [t]
  )

  const derivedContract = useMemo(
    () => resolveStartResearchContractFields(form),
    [form.baseline_id, form.research_intensity]
  )

  const derivedScopeCopy = useMemo(
    () => splitOptionCopy(t.scopeOptions[derivedContract.scope]),
    [derivedContract.scope, t]
  )
  const derivedBaselineModeCopy = useMemo(
    () => splitOptionCopy(t.baselineModeOptions[derivedContract.baseline_mode]),
    [derivedContract.baseline_mode, t]
  )
  const derivedResourcePolicyCopy = useMemo(
    () => splitOptionCopy(t.resourcePolicyOptions[derivedContract.resource_policy]),
    [derivedContract.resource_policy, t]
  )
  const derivedGitStrategyCopy = useMemo(
    () => splitOptionCopy(t.gitStrategyOptions[derivedContract.git_strategy]),
    [derivedContract.git_strategy, t]
  )
  const launchModeCopy = useMemo(
    () => splitOptionCopy(t.launchModeOptions[form.launch_mode]),
    [form.launch_mode, t]
  )

  useEffect(() => {
    if (!open) {
      return
    }
    const next = loadStartResearchTemplate(locale)
    const withSeed = {
      ...next,
      goal: initialGoal || next.goal,
      user_language: locale,
    }
    setForm({
      ...withSeed,
      quest_id: '',
    })
    setTemplates(loadStartResearchHistory())
    setSelectedTemplateId('__latest__')
    setManualOverride(false)
    setQuestIdManualOverride(false)
    setSuggestedQuestId('')
    setSelectedConnectorBindings({})
    setShowConnectorRecommendation(false)
    setConnectorRecommendationHandled(false)
    setConnectorAvailability(null)
    setConnectorAvailabilityResolved(false)
  }, [initialGoal, locale, open])

  const setField = <K extends keyof StartResearchTemplate>(
    key: K,
    value: StartResearchTemplate[K]
  ) => {
    setForm((current) => {
      const next = { ...current, [key]: value }
      saveStartResearchDraft(next)
      return next
    })
  }

  useEffect(() => {
    if (!open) return
    let active = true
    setSuggestedQuestIdLoading(true)
    void client
      .nextQuestId()
      .then((payload) => {
        if (!active) return
        const nextQuestId = String(payload?.quest_id || '').trim()
        setSuggestedQuestId(nextQuestId)
      })
      .catch(() => {
        if (!active) return
        setSuggestedQuestId('')
      })
      .finally(() => {
        if (active) setSuggestedQuestIdLoading(false)
      })
    return () => {
      active = false
    }
  }, [open])

  useEffect(() => {
    if (
      !shouldRecommendStartResearchConnectorBinding({
        open,
        availabilityResolved: connectorAvailabilityResolved,
        availabilityLoading: connectorAvailabilityLoading,
        availabilityError: connectorAvailabilityError,
        connectorRecommendationHandled,
        availability: connectorAvailability,
      })
    ) {
      return
    }
    setShowConnectorRecommendation(true)
    setConnectorRecommendationHandled(true)
  }, [
    connectorAvailability,
    connectorAvailabilityError,
    connectorAvailabilityLoading,
    connectorAvailabilityResolved,
    connectorRecommendationHandled,
    open,
  ])

  useEffect(() => {
    if (!open) return
    let active = true
    setConnectorsLoading(true)
    setConnectorsError(null)
    void client
      .connectors()
      .then((payload) => {
        if (!active) return
        const items = Array.isArray(payload) ? payload.filter((item) => item.name !== 'local' && item.enabled) : []
        setConnectors(items)
      })
      .catch((caught) => {
        if (!active) return
        setConnectors([])
        setConnectorsError(caught instanceof Error ? caught.message : 'Failed to load connectors.')
      })
      .finally(() => {
        if (active) {
          setConnectorsLoading(false)
        }
      })
    return () => {
      active = false
    }
  }, [open])

  useEffect(() => {
    if (!open) return
    let active = true
    setConnectorAvailabilityLoading(true)
    setConnectorAvailabilityResolved(false)
    setConnectorAvailabilityError(null)
    void client
      .connectorsAvailability()
      .then((payload) => {
        if (!active) return
        setConnectorAvailability(payload)
      })
      .catch((caught) => {
        if (!active) return
        setConnectorAvailability(null)
        setConnectorAvailabilityError(caught instanceof Error ? caught.message : 'Failed to load connector availability.')
      })
      .finally(() => {
        if (active) {
          setConnectorAvailabilityLoading(false)
          setConnectorAvailabilityResolved(true)
        }
      })
    return () => {
      active = false
    }
  }, [open])

  useEffect(() => {
    if (!open || questIdManualOverride) return
    if (!suggestedQuestId) return
    setForm((current) => {
      if (current.quest_id === suggestedQuestId) {
        return current
      }
      return {
        ...current,
        quest_id: suggestedQuestId,
      }
    })
  }, [open, questIdManualOverride, suggestedQuestId])

  useEffect(() => {
    if (!open) return
    let active = true
    setBaselineEntriesLoading(true)
    setBaselineEntriesError(null)
    void client
      .baselines()
      .then((payload) => {
        if (!active) return
        const entries = Array.isArray(payload) ? payload : []
        const sorted = [...entries].sort((left, right) =>
          String(right.updated_at || right.created_at || '').localeCompare(String(left.updated_at || left.created_at || ''))
        )
        setBaselineEntries(sorted)
      })
      .catch((caught) => {
        if (!active) return
        setBaselineEntries([])
        setBaselineEntriesError(caught instanceof Error ? caught.message : 'Failed to load baselines.')
      })
      .finally(() => {
        if (active) setBaselineEntriesLoading(false)
      })
    return () => {
      active = false
    }
  }, [open])

  const selectedBaselineEntry = useMemo(() => {
    const baselineId = form.baseline_id?.trim()
    if (!baselineId) return null
    return baselineEntries.find((entry) => entry.baseline_id === baselineId) ?? null
  }, [baselineEntries, form.baseline_id])

  const displayedQuestId = useMemo(() => {
    const current = String(form.quest_id || '').trim()
    if (current) return current
    return suggestedQuestId
  }, [form.quest_id, suggestedQuestId])

  const connectorChoices = useMemo(
    () =>
      connectors
        .map((item) => resolveStartConnectorChoice(item))
        .sort((left, right) => left.label.localeCompare(right.label)),
    [connectors]
  )

  const selectedConnectorTargets = useMemo(
    () =>
      connectorChoices.flatMap((item) => {
        const selectedConversationId = selectedConnectorBindings[item.name] || null
        if (!selectedConversationId) return []
        const target = item.targets.find((candidate) => candidate.conversationId === selectedConversationId)
        if (!target) return []
        return [{ connector: item.label, target }]
      }),
    [connectorChoices, selectedConnectorBindings]
  )

  const templateOptions = useMemo(
    () => [...referenceTemplates, ...templates],
    [referenceTemplates, templates]
  )

  useEffect(() => {
    setSelectedConnectorBindings((current) => {
      const next: Record<string, string | null> = {}
      let changed = false
      for (const item of connectorChoices) {
        const currentValue = current[item.name] || null
        const availableIds = new Set(item.targets.map((target) => target.conversationId))
        if (currentValue && availableIds.has(currentValue)) {
          next[item.name] = currentValue
          continue
        }
        next[item.name] = null
        if ((current[item.name] || null) !== null) {
          changed = true
        }
      }
      const currentKeys = Object.keys(current)
      if (!changed && currentKeys.length === Object.keys(next).length) {
        return current
      }
      return next
    })
  }, [connectorChoices])

  useEffect(() => {
    if (!open || manualOverride) return
    const baselineId = form.baseline_id?.trim()
    if (!baselineId) {
      if (form.baseline_variant_id) {
        setField('baseline_variant_id', '')
      }
      return
    }
    const entry = baselineEntries.find((item) => item.baseline_id === baselineId)
    if (!entry) return
    const variants = Array.isArray(entry.baseline_variants) ? entry.baseline_variants : []
    if (variants.length === 0) {
      if (form.baseline_variant_id) {
        setField('baseline_variant_id', '')
      }
      return
    }
    const currentVariant = form.baseline_variant_id?.trim()
    if (currentVariant && variants.some((variant) => variant.variant_id === currentVariant)) {
      return
    }
    const nextVariant = String(entry.default_variant_id || variants[0]?.variant_id || '').trim()
    if (nextVariant && nextVariant !== currentVariant) {
      setField('baseline_variant_id', nextVariant)
    }
  }, [
    baselineEntries,
    form.baseline_id,
    form.baseline_variant_id,
    manualOverride,
    open,
  ])

  const compiledPromptPreview = useMemo(() => compileStartResearchPrompt(form), [form])

  useEffect(() => {
    if (!open || manualOverride) {
      return
    }
    setPromptDraft(compiledPromptPreview)
  }, [compiledPromptPreview, manualOverride, open])

  const finalPrompt = promptDraft.trim() || (!manualOverride ? compiledPromptPreview.trim() : '')
  const promptRequired = open && !finalPrompt
  const goalRequired = open && !manualOverride && !form.goal.trim()

  const handlePromptChange = (value: string) => {
    if (!manualOverride && value !== compiledPromptPreview) {
      setManualOverride(true)
    }
    setPromptDraft(value)
  }

  const handleRestore = () => {
    setManualOverride(false)
    setPromptDraft(compiledPromptPreview)
  }

  const handleTemplateChange = (templateId: string) => {
    setSelectedTemplateId(templateId)
    if (templateId === '__new__') {
      const cleared = {
        ...defaultStartResearchTemplate(locale),
        quest_id: form.quest_id,
      }
      setManualOverride(false)
      saveStartResearchDraft(cleared)
      setForm(cleared)
      return
    }
    if (templateId === '__latest__') {
      const latest = loadStartResearchTemplate(locale)
      setManualOverride(false)
      setQuestIdManualOverride(false)
      setForm({
        ...latest,
        goal: initialGoal || latest.goal,
        user_language: locale,
        quest_id: suggestedQuestId || '',
      })
      return
    }
    const next = templateOptions.find((item) => item.id === templateId)
    if (!next) {
      return
    }
    setManualOverride(false)
    setQuestIdManualOverride(false)
    setForm({
      title: next.title,
      quest_id: suggestedQuestId || '',
      goal: next.goal,
      baseline_id: next.baseline_id,
      baseline_variant_id: next.baseline_variant_id || '',
      baseline_urls: next.baseline_urls,
      paper_urls: next.paper_urls,
      runtime_constraints: next.runtime_constraints,
      objectives: next.objectives,
      need_research_paper: next.need_research_paper,
      research_intensity: next.research_intensity,
      decision_policy: next.decision_policy,
      launch_mode: next.launch_mode,
      custom_profile: next.custom_profile,
      entry_state_summary: next.entry_state_summary,
      review_summary: next.review_summary,
      custom_brief: next.custom_brief,
      user_language: next.user_language,
    })
  }

  const applyResearchIntensity = (presetId: ResearchIntensity) => {
    setForm((current) => {
      const next = applyStartResearchIntensityPreset(current, presetId)
      saveStartResearchDraft(next)
      return next
    })
  }

  const handleQuestIdChange = (value: string) => {
    const nextQuestId = slugifyQuestRepo(value)
    setQuestIdManualOverride(Boolean(nextQuestId) && nextQuestId !== suggestedQuestId)
    setField('quest_id', nextQuestId)
  }

  const handleOpenConnectorSettings = () => {
    setShowConnectorRecommendation(false)
    onClose()
    navigate('/settings/connector', { state: { configName: 'connectors' } })
  }

  const handleCreate = async () => {
    if (!manualOverride && !form.goal.trim()) {
      return
    }
    if (!finalPrompt) {
      return
    }
    const saved = saveStartResearchTemplate(form)
    const baselineId = saved.baseline_id.trim()
    const baselineVariantId = saved.baseline_variant_id.trim()
    const requestedBaselineRef = baselineId
      ? {
          baseline_id: baselineId,
          variant_id: baselineVariantId || null,
        }
      : null
    const derivedFields = resolveStartResearchContractFields(saved)
    const timeBudget = Number(derivedFields.time_budget_hours)
    const requestedConnectorBindings = connectorChoices
      .map((item) => ({
        connector: item.name,
        conversation_id: selectedConnectorBindings[item.name] || null,
      }))
      .filter((item) => Boolean(item.conversation_id))
    const startupContract = {
      schema_version: 3,
      user_language: saved.user_language,
      need_research_paper: saved.need_research_paper,
      research_intensity: saved.research_intensity,
      decision_policy: saved.decision_policy,
      launch_mode: saved.launch_mode,
      custom_profile: saved.custom_profile,
      scope: derivedFields.scope,
      baseline_mode: derivedFields.baseline_mode,
      resource_policy: derivedFields.resource_policy,
      time_budget_hours: Number.isFinite(timeBudget) && timeBudget > 0 ? timeBudget : null,
      git_strategy: derivedFields.git_strategy,
      runtime_constraints: saved.runtime_constraints,
      objectives: sanitizeLines(saved.objectives),
      baseline_urls: sanitizeLines(saved.baseline_urls),
      paper_urls: sanitizeLines(saved.paper_urls),
      entry_state_summary: saved.entry_state_summary,
      review_summary: saved.review_summary,
      custom_brief: saved.custom_brief,
    }
    await onCreate({
      title: saved.title,
      goal: finalPrompt,
      quest_id: questIdManualOverride ? saved.quest_id || undefined : undefined,
      requested_connector_bindings: requestedConnectorBindings,
      requested_baseline_ref: requestedBaselineRef,
      startup_contract: startupContract,
    })
  }

  return (
    <>
      <OverlayDialog
        open={open}
        title={t.title}
        description={t.body}
        onClose={onClose}
        className="h-[94svh] max-w-[96vw] rounded-[26px] sm:h-[92vh] sm:max-w-[92vw] sm:rounded-[30px]"
      >
        <div className="feed-scrollbar flex h-full min-h-0 flex-col gap-3 overflow-y-auto p-3 sm:gap-4 sm:p-4 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] lg:overflow-hidden lg:p-5">
        <div
          className={cn(
            'flex flex-none flex-col overflow-visible lg:min-h-0 lg:flex-auto lg:overflow-hidden lg:rounded-xl lg:border lg:border-[rgba(45,42,38,0.09)] lg:bg-[rgba(255,255,255,0.76)] lg:shadow-[0_10px_26px_-22px_rgba(45,42,38,0.26)] lg:backdrop-blur-xl dark:lg:border-[rgba(45,42,38,0.09)] dark:lg:bg-[rgba(255,255,255,0.82)]'
          )}
        >
          <div className="shrink-0 px-1 py-1 lg:border-b lg:border-[rgba(45,42,38,0.08)] lg:px-4 lg:py-4 dark:lg:border-[rgba(45,42,38,0.08)]">
            <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[rgba(107,103,97,0.8)] dark:text-[rgba(107,103,97,0.8)] lg:text-sm lg:normal-case lg:tracking-normal lg:text-[rgba(38,36,33,0.95)]">
              {t.formTitle}
            </div>
            <div className="mt-1 text-[11px] leading-5 text-[rgba(107,103,97,0.72)] dark:text-[rgba(107,103,97,0.72)] lg:text-xs">
              {t.formHint}
            </div>
          </div>

          <div className="px-0 py-1 sm:px-0 sm:py-1 lg:feed-scrollbar lg:min-h-0 lg:flex-1 lg:overflow-y-auto lg:overscroll-contain lg:p-4">
            <div className="flex min-h-full flex-col gap-4">
              {manualOverride ? (
                <div className="rounded-lg border border-[#c4a066]/50 bg-[#c4a066]/10 px-3 py-2 text-xs text-[rgba(56,49,35,0.92)]">
                  <div className="flex items-center gap-2 font-semibold">
                    <Lock className="h-3.5 w-3.5" />
                    {t.manualTitle}
                  </div>
                  <div className="mt-1">{t.manualBody}</div>
                </div>
              ) : null}

              <SectionCard title={t.template} muted>
                <InlineField label={t.template} help={t.templateHint} hint={t.templateHint}>
                  <div className="flex gap-2">
                    <select
                      value={selectedTemplateId}
                      onChange={(event) => handleTemplateChange(event.target.value)}
                      className={cn(selectClassName, 'min-w-0 flex-1')}
                      disabled={manualOverride}
                    >
                      <option value="__new__">{t.newTemplate}</option>
                      <option value="__latest__">{t.useTemplate}: {t.latestDraft}</option>
                      {templateOptions.length === 0 ? <option value="__empty__">{t.noTemplates}</option> : null}
                      {templateOptions.map((item) => (
                        <option key={item.id} value={item.id}>
                          {compactTemplateLabel(item, locale)}
                        </option>
                      ))}
                    </select>
                    <div className="inline-flex h-9 items-center rounded-[10px] border border-[rgba(45,42,38,0.09)] bg-white/65 px-3 text-[11px] text-[rgba(75,73,69,0.72)] dark:border-[rgba(45,42,38,0.09)] dark:bg-white/72 dark:text-[rgba(75,73,69,0.72)]">
                      {templateOptions.length}
                    </div>
                  </div>
                </InlineField>
              </SectionCard>

              <SectionCard title={t.questTarget} muted>
                <div className="text-[11px] leading-5 text-[rgba(107,103,97,0.72)] dark:text-[rgba(107,103,97,0.72)]">{t.targetHint}</div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="rounded-lg border border-[rgba(45,42,38,0.08)] bg-white/70 px-3 py-3 dark:border-[rgba(45,42,38,0.08)] dark:bg-white/76">
                    <div className="text-[11px] text-[rgba(107,103,97,0.72)] dark:text-[rgba(107,103,97,0.72)]">{t.targetMode}</div>
                    <div className="mt-1 text-sm font-semibold text-[rgba(38,36,33,0.95)] dark:text-[rgba(38,36,33,0.95)]">{t.targetModeValue}</div>
                  </div>
                  <div className="rounded-lg border border-[rgba(45,42,38,0.08)] bg-white/70 px-3 py-3 dark:border-[rgba(45,42,38,0.08)] dark:bg-white/76">
                    <div className="text-[11px] text-[rgba(107,103,97,0.72)] dark:text-[rgba(107,103,97,0.72)]">{t.targetRunner}</div>
                    <div className="mt-1 text-sm font-semibold text-[rgba(38,36,33,0.95)] dark:text-[rgba(38,36,33,0.95)]">{t.targetRunnerValue}</div>
                  </div>
                </div>
                <ConnectorChoiceField
                  label={t.connectorDeliveryLabel}
                  help={t.connectorDeliveryHelp}
                  hint={t.connectorDeliveryHint}
                  items={connectorChoices}
                  value={selectedConnectorBindings}
                  loading={connectorsLoading}
                  error={connectorsError}
                  emptyTitle={t.connectorEmptyTitle}
                  emptyBody={t.connectorEmptyBody}
                  unavailableTitle={t.connectorUnavailableTitle}
                  unavailableBody={t.connectorUnavailableBody}
                  settingsActionLabel={t.connectorSettingsAction}
                  autoModeLabel={t.connectorAutoModeLabel}
                  autoModeBody={t.connectorAutoModeBody}
                  selectedHint={t.connectorSelectedHint}
                  sourceLabels={{
                    default: t.connectorSourceDefault,
                    recent: t.connectorSourceRecent,
                    last: t.connectorSourceLast,
                    discovered: t.connectorSourceDiscovered,
                    unavailable: t.connectorSourceUnavailable,
                  }}
                  locale={locale}
                  onOpenSettings={handleOpenConnectorSettings}
                  onChange={(connectorName, next) =>
                    setSelectedConnectorBindings((current) => ({ ...current, [connectorName]: next }))
                  }
                />
              </SectionCard>

              <SectionCard title={t.basics}>
                <InlineField label={t.titleLabel} help={t.titleHelp}>
                  <Input
                    value={form.title}
                    onChange={(event) => setField('title', event.target.value)}
                    placeholder={t.titlePlaceholder}
                    className="rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78"
                    disabled={manualOverride}
                  />
                </InlineField>

                <InlineField label={t.repoLabel} help={t.repoHelp}>
                  <Input
                    value={displayedQuestId}
                    onChange={(event) => handleQuestIdChange(event.target.value)}
                    placeholder={suggestedQuestIdLoading ? t.repoLoading : suggestedQuestId || t.repoPlaceholder}
                    className="rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78"
                    disabled={manualOverride}
                  />
                </InlineField>

                <InlineField label={t.goalLabel} help={t.goalHelp}>
                  <Textarea
                    value={form.goal}
                    onChange={(event) => setField('goal', event.target.value)}
                    placeholder={t.goalPlaceholder}
                    className="min-h-[150px] rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs leading-5 dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78"
                    disabled={manualOverride}
                  />
                </InlineField>
                {goalRequired ? <div className="text-xs text-[#9a1b1b]">{t.goalRequired}</div> : null}
              </SectionCard>

              <SectionCard title={t.references}>
                <div className="grid grid-cols-1 gap-3">
                  <InlineField label={t.baselineRoot} help={t.baselineRootHelp}>
                    <div className="space-y-2">
                      <select
                        value={form.baseline_id}
                        onChange={(event) => setField('baseline_id', event.target.value)}
                        className={selectClassName}
                        disabled={manualOverride}
                      >
                        <option value="">
                          {baselineEntriesLoading
                            ? locale === 'zh'
                              ? '正在加载 baselines…'
                              : 'Loading baselines…'
                            : t.baselineRootPlaceholder}
                        </option>
                        {form.baseline_id &&
                        !baselineEntries.some((entry) => entry.baseline_id === form.baseline_id.trim()) ? (
                          <option value={form.baseline_id}>{form.baseline_id} (custom)</option>
                        ) : null}
                        {baselineEntries.map((entry) => {
                          const status = formatBaselineStatus(entry.status, locale)
                          const sourceQuest = String(entry.source_quest_id || '').trim()
                          const label = [entry.baseline_id, status, sourceQuest].filter(Boolean).join(' · ')
                          return (
                            <option key={entry.baseline_id} value={entry.baseline_id}>
                              {clampText(label, 88)}
                            </option>
                          )
                        })}
                      </select>

                      {selectedBaselineEntry?.baseline_variants?.length ? (
                        <div className="space-y-1">
                          <div className="flex items-center gap-1.5 text-[11px] font-medium text-[rgba(75,73,69,0.78)] dark:text-[rgba(75,73,69,0.78)]">
                            <span>{t.baselineVariant}</span>
                            <FieldHelp text={t.baselineVariantHelp} />
                          </div>
                          <select
                            value={form.baseline_variant_id}
                            onChange={(event) => setField('baseline_variant_id', event.target.value)}
                            className={selectClassName}
                            disabled={manualOverride}
                          >
                            {selectedBaselineEntry.baseline_variants.map((variant) => (
                              <option key={variant.variant_id} value={variant.variant_id}>
                                {variant.label ? `${variant.variant_id} · ${variant.label}` : variant.variant_id}
                              </option>
                            ))}
                          </select>
                        </div>
                      ) : null}

                      {selectedBaselineEntry ? (
                        <div className="rounded-lg border border-[rgba(45,42,38,0.08)] bg-white/70 px-3 py-2.5 text-[11px] leading-5 text-[rgba(75,73,69,0.82)] dark:border-[rgba(45,42,38,0.08)] dark:bg-white/76 dark:text-[rgba(75,73,69,0.82)]">
                          <div>{selectedBaselineEntry.summary ? clampText(String(selectedBaselineEntry.summary), 120) : (locale === 'zh' ? '未提供概要。' : 'No summary provided.')}</div>
                          <div className="mt-2 grid grid-cols-1 gap-x-3 gap-y-1 sm:grid-cols-2">
                            <div>{locale === 'zh' ? '状态' : 'Status'}: {formatBaselineStatus(selectedBaselineEntry.status, locale)}</div>
                            <div className="truncate" title={selectedBaselineEntry.source_quest_id || undefined}>
                              {locale === 'zh' ? '来源项目' : 'Source project'}: {selectedBaselineEntry.source_quest_id || (locale === 'zh' ? '未知' : 'unknown')}
                            </div>
                            <div>{locale === 'zh' ? '主指标' : 'Primary metric'}: {resolveBaselineMetricLabel(selectedBaselineEntry, locale)}</div>
                            <div>{locale === 'zh' ? '确认时间' : 'Confirmed'}: {formatBaselineTimestamp(selectedBaselineEntry.confirmed_at || selectedBaselineEntry.updated_at, locale)}</div>
                          </div>
                        </div>
                      ) : baselineEntriesError ? (
                        <div className="text-[11px] leading-5 text-[#9a1b1b]">{baselineEntriesError}</div>
                      ) : null}
                    </div>
                  </InlineField>
                </div>
                <InlineField label={t.languageLabel} help={t.languageHelp}>
                  <select
                    value={form.user_language}
                    onChange={(event) => setField('user_language', event.target.value as StartResearchTemplate['user_language'])}
                    className={selectClassName}
                    disabled={manualOverride}
                  >
                    <option value="zh">中文</option>
                    <option value="en">English</option>
                  </select>
                </InlineField>
                <InlineField label={t.baselineUrls} help={t.baselineUrlsHelp}>
                  <Textarea
                    value={form.baseline_urls}
                    onChange={(event) => setField('baseline_urls', event.target.value)}
                    placeholder={t.baselineUrlsPlaceholder}
                    className="min-h-[92px] rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs leading-5 dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78"
                    disabled={manualOverride || Boolean(form.baseline_id?.trim())}
                  />
                </InlineField>
                <InlineField label={t.paperUrls} help={t.paperUrlsHelp}>
                  <Textarea
                    value={form.paper_urls}
                    onChange={(event) => setField('paper_urls', event.target.value)}
                    placeholder={t.paperUrlsPlaceholder}
                    className="min-h-[92px] rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs leading-5 dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78"
                    disabled={manualOverride}
                  />
                </InlineField>
              </SectionCard>

              <SectionCard title={t.policy}>
                <InlineField label={t.launchModeLabel} help={t.launchModeHelp} hint={t.launchModeHelp}>
                  <select
                    value={form.launch_mode}
                    onChange={(event) => setField('launch_mode', event.target.value as LaunchMode)}
                    className={selectClassName}
                    disabled={manualOverride}
                  >
                    <option value="standard">{t.launchModeOptions.standard}</option>
                    <option value="custom">{t.launchModeOptions.custom}</option>
                  </select>
                </InlineField>
                {form.launch_mode === 'custom' ? (
                  <>
                    <InlineField label={t.customProfileLabel} help={t.customProfileHelp} hint={t.customProfileHelp}>
                      <select
                        value={form.custom_profile}
                        onChange={(event) => setField('custom_profile', event.target.value as CustomProfile)}
                        className={selectClassName}
                        disabled={manualOverride}
                      >
                        <option value="continue_existing_state">{t.customProfileOptions.continue_existing_state}</option>
                        <option value="revision_rebuttal">{t.customProfileOptions.revision_rebuttal}</option>
                        <option value="freeform">{t.customProfileOptions.freeform}</option>
                      </select>
                    </InlineField>
                    <InlineField label={t.entryStateSummaryLabel} help={t.entryStateSummaryHelp}>
                      <Textarea
                        value={form.entry_state_summary}
                        onChange={(event) => setField('entry_state_summary', event.target.value)}
                        placeholder={t.entryStateSummaryPlaceholder}
                        className="min-h-[92px] rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs leading-5 dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78"
                        disabled={manualOverride}
                      />
                    </InlineField>
                    {form.custom_profile === 'revision_rebuttal' ? (
                      <InlineField label={t.reviewSummaryLabel} help={t.reviewSummaryHelp}>
                        <Textarea
                          value={form.review_summary}
                          onChange={(event) => setField('review_summary', event.target.value)}
                          placeholder={t.reviewSummaryPlaceholder}
                          className="min-h-[92px] rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs leading-5 dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78"
                          disabled={manualOverride}
                        />
                      </InlineField>
                    ) : null}
                    <InlineField label={t.customBriefLabel} help={t.customBriefHelp}>
                      <Textarea
                        value={form.custom_brief}
                        onChange={(event) => setField('custom_brief', event.target.value)}
                        placeholder={t.customBriefPlaceholder}
                        className="min-h-[92px] rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs leading-5 dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78"
                        disabled={manualOverride}
                      />
                    </InlineField>
                  </>
                ) : null}
                <ChoiceField
                  label={t.researchIntensityLabel}
                  help={t.researchIntensityHelp}
                  hint={t.researchIntensityHelp}
                  value={activeResearchIntensity}
                  items={intensityItems}
                  onChange={applyResearchIntensity}
                  disabled={manualOverride}
                />
                <ChoiceField
                  label={t.decisionPolicyLabel}
                  help={t.decisionPolicyHelp}
                  hint={t.decisionPolicyHelp}
                  value={form.decision_policy}
                  items={decisionPolicyItems}
                  onChange={(value) => setField('decision_policy', value as DecisionPolicy)}
                  disabled={manualOverride}
                />
                <InlineField label={t.researchPaperLabel} help={t.researchPaperHelp} hint={t.researchPaperHelp}>
                  <div className="rounded-[14px] border border-[rgba(45,42,38,0.08)] bg-white/70 px-3 py-3 dark:border-[rgba(45,42,38,0.08)] dark:bg-white/76">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-xs font-semibold text-[rgba(38,36,33,0.95)] dark:text-[rgba(38,36,33,0.95)]">
                          {form.need_research_paper ? t.researchPaperEnabled : t.researchPaperDisabled}
                        </div>
                        <div className="mt-1 text-[11px] leading-5 text-[rgba(86,82,77,0.82)] dark:text-[rgba(86,82,77,0.82)]">
                          {form.need_research_paper ? t.researchPaperEnabledBody : t.researchPaperDisabledBody}
                        </div>
                      </div>
                      <AnimatedCheckbox
                        checked={form.need_research_paper}
                        onChange={(checked) => setField('need_research_paper', checked)}
                        disabled={manualOverride}
                        size="md"
                        className="shrink-0"
                      />
                    </div>
                  </div>
                </InlineField>
                <div className="rounded-[14px] border border-[rgba(45,42,38,0.08)] bg-[rgba(244,239,233,0.52)] px-3 py-3 dark:border-[rgba(45,42,38,0.08)] dark:bg-[rgba(244,239,233,0.62)]">
                  <div className="text-[11px] font-medium text-[rgba(75,73,69,0.78)] dark:text-[rgba(75,73,69,0.78)]">
                    {t.derivedPolicyTitle}
                  </div>
                  <div className="mt-1 text-[11px] leading-5 text-[rgba(107,103,97,0.72)] dark:text-[rgba(107,103,97,0.72)]">
                    {t.derivedPolicyHint}
                  </div>
                  <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                    <div className="rounded-[12px] border border-[rgba(45,42,38,0.08)] bg-white/70 px-3 py-2 dark:border-[rgba(45,42,38,0.08)] dark:bg-white/76">
                      <div className="text-[10px] uppercase tracking-[0.14em] text-[rgba(107,103,97,0.72)] dark:text-[rgba(107,103,97,0.72)]">
                        {derivedScopeCopy.title}
                      </div>
                      <div className="mt-1 text-[11px] leading-5 text-[rgba(56,52,47,0.9)] dark:text-[rgba(56,52,47,0.9)]">
                        {derivedScopeCopy.description}
                      </div>
                    </div>
                    <div className="rounded-[12px] border border-[rgba(45,42,38,0.08)] bg-white/70 px-3 py-2 dark:border-[rgba(45,42,38,0.08)] dark:bg-white/76">
                      <div className="text-[10px] uppercase tracking-[0.14em] text-[rgba(107,103,97,0.72)] dark:text-[rgba(107,103,97,0.72)]">
                        {derivedBaselineModeCopy.title}
                      </div>
                      <div className="mt-1 text-[11px] leading-5 text-[rgba(56,52,47,0.9)] dark:text-[rgba(56,52,47,0.9)]">
                        {derivedBaselineModeCopy.description}
                      </div>
                    </div>
                    <div className="rounded-[12px] border border-[rgba(45,42,38,0.08)] bg-white/70 px-3 py-2 dark:border-[rgba(45,42,38,0.08)] dark:bg-white/76">
                      <div className="text-[10px] uppercase tracking-[0.14em] text-[rgba(107,103,97,0.72)] dark:text-[rgba(107,103,97,0.72)]">
                        {derivedResourcePolicyCopy.title}
                      </div>
                      <div className="mt-1 text-[11px] leading-5 text-[rgba(56,52,47,0.9)] dark:text-[rgba(56,52,47,0.9)]">
                        {derivedResourcePolicyCopy.description}
                      </div>
                    </div>
                    <div className="rounded-[12px] border border-[rgba(45,42,38,0.08)] bg-white/70 px-3 py-2 dark:border-[rgba(45,42,38,0.08)] dark:bg-white/76">
                      <div className="text-[10px] uppercase tracking-[0.14em] text-[rgba(107,103,97,0.72)] dark:text-[rgba(107,103,97,0.72)]">
                        {t.derivedPolicyBudgetLabel}
                      </div>
                      <div className="mt-1 text-[11px] leading-5 text-[rgba(56,52,47,0.9)] dark:text-[rgba(56,52,47,0.9)]">
                        {derivedContract.time_budget_hours}h · {derivedGitStrategyCopy.title}
                      </div>
                      <div className="mt-1 text-[11px] leading-5 text-[rgba(107,103,97,0.78)] dark:text-[rgba(107,103,97,0.78)]">
                        {derivedGitStrategyCopy.description}
                      </div>
                    </div>
                  </div>
                </div>
                <InlineField label={t.runtimeConstraintsLabel} help={t.runtimeConstraintsHelp}>
                  <Textarea
                    value={form.runtime_constraints}
                    onChange={(event) => setField('runtime_constraints', event.target.value)}
                    placeholder={t.runtimeConstraintsPlaceholder}
                    className="min-h-[92px] rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs leading-5 dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78"
                    disabled={manualOverride}
                  />
                </InlineField>
              </SectionCard>

              <SectionCard title={t.objectives}>
                <InlineField label={t.objectivesLabel} help={t.objectivesHelp}>
                  <Textarea
                    value={form.objectives}
                    onChange={(event) => setField('objectives', event.target.value)}
                    placeholder={t.objectivesPlaceholder}
                    className="min-h-[120px] rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs leading-5 dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78"
                    disabled={manualOverride}
                  />
                </InlineField>
              </SectionCard>
            </div>
          </div>
        </div>

        <div
          className={cn(
            'flex flex-none flex-col overflow-visible p-0 sm:p-0 lg:min-h-0 lg:flex-auto lg:overflow-hidden lg:rounded-xl lg:border lg:border-[rgba(45,42,38,0.09)] lg:bg-[rgba(255,255,255,0.76)] lg:p-4 lg:shadow-[0_10px_26px_-22px_rgba(45,42,38,0.26)] lg:backdrop-blur-xl dark:lg:border-[rgba(45,42,38,0.09)] dark:lg:bg-[rgba(255,255,255,0.82)]'
          )}
        >
          <div className="mb-2 flex shrink-0 flex-wrap items-start justify-between gap-2 px-1 lg:mb-3 lg:px-0">
            <div>
              <div className="text-xs font-semibold uppercase tracking-[0.18em] text-[rgba(107,103,97,0.8)] dark:text-[rgba(107,103,97,0.8)] lg:text-sm lg:normal-case lg:tracking-normal lg:text-[rgba(38,36,33,0.95)]">
                {t.preview}
              </div>
              <div className="mt-1 text-[11px] leading-5 text-[rgba(107,103,97,0.72)] dark:text-[rgba(107,103,97,0.72)] lg:text-xs">
                {t.previewBody}
              </div>
            </div>
            {manualOverride ? (
              <Badge className="rounded-full px-2.5 py-1 text-[10px] uppercase tracking-wide">{t.manual}</Badge>
            ) : null}
          </div>

          <div className="mb-3 shrink-0 grid grid-cols-2 gap-2 px-1 sm:grid-cols-3 lg:px-0 xl:grid-cols-6">
            <div className="rounded-lg border border-[rgba(45,42,38,0.09)] bg-[rgba(244,239,233,0.55)] px-3 py-2 text-[11px] dark:border-[rgba(45,42,38,0.09)] dark:bg-[rgba(244,239,233,0.65)]">
              <div className="text-[rgba(107,103,97,0.72)] dark:text-[rgba(107,103,97,0.72)]">{t.repoLabel}</div>
              <div
                className="mt-1 truncate font-semibold text-[rgba(38,36,33,0.95)] dark:text-[rgba(38,36,33,0.95)]"
                title={displayedQuestId || (suggestedQuestIdLoading ? t.repoLoading : t.repoAutoAssigned)}
              >
                {displayedQuestId || (suggestedQuestIdLoading ? t.repoLoading : t.repoAutoAssigned)}
              </div>
            </div>
            <div className="rounded-lg border border-[rgba(45,42,38,0.09)] bg-[rgba(244,239,233,0.55)] px-3 py-2 text-[11px] dark:border-[rgba(45,42,38,0.09)] dark:bg-[rgba(244,239,233,0.65)]">
              <div className="text-[rgba(107,103,97,0.72)] dark:text-[rgba(107,103,97,0.72)]">{t.researchIntensityLabel}</div>
              <div className="mt-1 font-semibold text-[rgba(38,36,33,0.95)] dark:text-[rgba(38,36,33,0.95)]">
                {t.intensityOptions[activeResearchIntensity].title}
              </div>
            </div>
            <div className="rounded-lg border border-[rgba(45,42,38,0.09)] bg-[rgba(244,239,233,0.55)] px-3 py-2 text-[11px] dark:border-[rgba(45,42,38,0.09)] dark:bg-[rgba(244,239,233,0.65)]">
              <div className="text-[rgba(107,103,97,0.72)] dark:text-[rgba(107,103,97,0.72)]">{t.connectorSummaryLabel}</div>
              <div className="mt-1 font-semibold text-[rgba(38,36,33,0.95)] dark:text-[rgba(38,36,33,0.95)]">
                {selectedConnectorTargets.length > 0
                  ? locale === 'zh'
                    ? `已选 ${selectedConnectorTargets.length} 个`
                    : `${selectedConnectorTargets.length} selected`
                  : t.connectorSummaryAuto}
              </div>
              <div
                className="mt-1 truncate text-[10px] leading-4 text-[rgba(107,103,97,0.78)] dark:text-[rgba(107,103,97,0.78)]"
                title={
                  selectedConnectorTargets.length > 0
                    ? selectedConnectorTargets
                        .map((item) => `${item.connector} · ${item.target.compactLabel}`)
                        .join(' / ')
                    : t.connectorAutoModeBody
                }
              >
                {selectedConnectorTargets.length > 0
                  ? selectedConnectorTargets
                      .slice(0, 2)
                      .map((item) => `${item.connector} · ${item.target.compactLabel}`)
                      .join(' / ')
                  : t.connectorAutoModeBody}
              </div>
            </div>
            <div className="hidden rounded-lg border border-[rgba(45,42,38,0.09)] bg-[rgba(244,239,233,0.55)] px-3 py-2 text-[11px] sm:block dark:border-[rgba(45,42,38,0.09)] dark:bg-[rgba(244,239,233,0.65)]">
              <div className="text-[rgba(107,103,97,0.72)] dark:text-[rgba(107,103,97,0.72)]">{t.decisionPolicyLabel}</div>
              <div className="mt-1 font-semibold text-[rgba(38,36,33,0.95)] dark:text-[rgba(38,36,33,0.95)]">
                {t.decisionPolicyOptions[form.decision_policy].title}
              </div>
            </div>
            <div className="hidden rounded-lg border border-[rgba(45,42,38,0.09)] bg-[rgba(244,239,233,0.55)] px-3 py-2 text-[11px] sm:block dark:border-[rgba(45,42,38,0.09)] dark:bg-[rgba(244,239,233,0.65)]">
              <div className="text-[rgba(107,103,97,0.72)] dark:text-[rgba(107,103,97,0.72)]">{t.deliveryModeLabel}</div>
              <div className="mt-1 font-semibold text-[rgba(38,36,33,0.95)] dark:text-[rgba(38,36,33,0.95)]">
                {form.need_research_paper ? t.researchPaperEnabled : t.researchPaperDisabled}
              </div>
            </div>
            <div className="hidden rounded-lg border border-[rgba(45,42,38,0.09)] bg-[rgba(244,239,233,0.55)] px-3 py-2 text-[11px] sm:block dark:border-[rgba(45,42,38,0.09)] dark:bg-[rgba(244,239,233,0.65)]">
              <div className="text-[rgba(107,103,97,0.72)] dark:text-[rgba(107,103,97,0.72)]">{t.launchModeLabel}</div>
              <div className="mt-1 font-semibold text-[rgba(38,36,33,0.95)] dark:text-[rgba(38,36,33,0.95)]">
                {launchModeCopy.title}
              </div>
            </div>
          </div>

          <textarea
            aria-label={t.preview}
            value={promptDraft}
            onChange={(event) => handlePromptChange(event.target.value)}
            className="feed-scrollbar min-h-[28svh] flex-1 overflow-y-auto overscroll-contain resize-none rounded-[18px] border border-[rgba(45,42,38,0.09)] bg-white/72 p-3 font-mono text-xs leading-5 text-[rgba(38,36,33,0.95)] outline-none dark:border-[rgba(45,42,38,0.09)] dark:bg-white/82 dark:text-[rgba(38,36,33,0.95)] sm:min-h-[34svh] lg:min-h-0"
          />

          <div className="mt-2 flex shrink-0 flex-col items-start justify-between gap-1 px-1 text-[11px] text-[rgba(107,103,97,0.72)] dark:text-[rgba(107,103,97,0.72)] sm:flex-row sm:items-center sm:gap-2 lg:px-0">
            <span>{t.footer}</span>
            <span>{promptDraft.length}</span>
          </div>

          {promptRequired ? <div className="mt-2 shrink-0 px-1 text-xs text-[#9a1b1b] lg:px-0">{t.promptRequired}</div> : null}
          {error ? <div className="mt-2 shrink-0 px-1 text-xs text-[#9a1b1b] lg:px-0">{error}</div> : null}

          <div className="mt-3 flex shrink-0 flex-col gap-3 px-1 sm:flex-row sm:items-center sm:justify-between lg:px-0">
            <div className="inline-flex items-center gap-2 text-[11px] text-[rgba(107,103,97,0.72)] dark:text-[rgba(107,103,97,0.72)]">
              <BookmarkPlus className="h-3.5 w-3.5" />
              <span>{templateOptions.length} template(s)</span>
            </div>
            <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center sm:gap-3">
              <Button
                variant="secondary"
                disabled={!manualOverride || loading}
                onClick={handleRestore}
                className="w-full sm:w-auto"
              >
                <RotateCcw className="h-4 w-4" />
                {t.restore}
              </Button>
              <Button variant="ghost" onClick={onClose} className="w-full sm:w-auto">
                {t.cancel}
              </Button>
              <Button
                onClick={() => void handleCreate()}
                disabled={loading || goalRequired || promptRequired}
                className="w-full sm:w-auto"
              >
                <Sparkles className="h-4 w-4" />
                {loading ? '…' : t.create}
              </Button>
            </div>
          </div>
        </div>
        </div>
      </OverlayDialog>
      <Dialog
        open={open && showConnectorRecommendation}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) {
            setShowConnectorRecommendation(false)
          }
        }}
      >
        <DialogContent
          showCloseButton={false}
          className="max-w-[92vw] rounded-[24px] border border-[rgba(45,42,38,0.09)] bg-[rgba(255,255,255,0.92)] p-0 shadow-[0_30px_90px_-48px_rgba(45,42,38,0.38)] backdrop-blur-2xl sm:max-w-md dark:border-[rgba(255,255,255,0.08)] dark:bg-[rgba(28,28,30,0.86)]"
        >
          <div className="p-5 sm:p-6">
            <DialogHeader className="space-y-2 text-left">
              <DialogTitle className="text-[18px] font-semibold text-[rgba(38,36,33,0.96)] dark:text-white">
                {t.connectorSuggestTitle}
              </DialogTitle>
              <DialogDescription className="text-sm leading-6 text-[rgba(86,82,77,0.82)] dark:text-white/68">
                {t.connectorSuggestBody}
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className="mt-5 flex-row justify-end gap-2 sm:space-x-0">
              <Button
                type="button"
                variant="ghost"
                className="min-w-[88px]"
                onClick={() => setShowConnectorRecommendation(false)}
              >
                {t.connectorSuggestLater}
              </Button>
              <Button
                type="button"
                className="min-w-[88px]"
                onClick={handleOpenConnectorSettings}
              >
                {t.connectorSuggestGo}
              </Button>
            </DialogFooter>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
