import { ArrowLeft, ArrowUpRight, BookmarkPlus, CheckCircle2, CircleHelp, Lock, MessageSquareText, RotateCcw, Sparkles, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'

import { AutonomousSetupIntakeSurface } from '@/components/projects/AutonomousSetupIntakeSurface'
import { ConnectorTargetRadioGroup, type ConnectorTargetRadioItem } from '@/components/connectors/ConnectorTargetRadioGroup'
import { OverlayDialog } from '@/components/home/OverlayDialog'
import { LAUNCH_DIALOG_SHELL_CLASS } from '@/components/projects/LaunchModeVisuals'
import { AnimatedMarkdownPlan } from '@/components/projects/AnimatedMarkdownPlan'
import { PlanningStepsPulse } from '@/components/projects/PlanningStepsPulse'
import { SetupAgentRail } from '@/components/projects/SetupAgentRail'
import { SetupAgentQuestPanel } from '@/components/projects/SetupAgentQuestPanel'
import { connectorCatalog } from '@/components/settings/connectorCatalog'
import { DeepXivSetupDialog } from '@/components/settings/DeepXivSetupDialog'
import { AnimatedCheckbox } from '@/components/ui/animated-checkbox'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { useQuestWorkspace } from '@/lib/acp'
import { client } from '@/lib/api'
import { assetUrl } from '@/lib/assets'
import { connectorInstanceMode, connectorTargetLabel, normalizeConnectorTargets, parseConversationId, recentConversationLabel } from '@/lib/connectors'
import { useI18n } from '@/lib/i18n'
import { normalizeZhUiCopy } from '@/lib/i18n/normalizeZhUiCopy'
import type { QuestMessageAttachmentDraft } from '@/lib/hooks/useQuestMessageAttachments'
import { useOnboardingStore } from '@/lib/stores/onboarding'
import { resetDemoRuntime } from '@/demo/runtime'
import { normalizeBuiltinRunnerName, runnerLabel } from '@/lib/runnerBranding'
import {
  applyStartResearchIntensityPreset,
  buildStartResearchLaunchSnapshot,
  type BaselineAcceptanceTarget,
  type BaselineSourceMode,
  compileStartResearchPrompt,
  defaultStartResearchTemplate,
  detectStartResearchIntensity,
  type ExecutionStartMode,
  loadStartResearchHistory,
  loadStartResearchTemplate,
  listReferenceStartResearchTemplates,
  listStartResearchIntensityPresets,
  resolveStartResearchContractFields,
  resolveStartResearchConnectorBindings,
  saveStartResearchDraft,
  saveStartResearchTemplate,
  slugifyQuestRepo,
  type BaselineExecutionPolicy,
  type CustomProfile,
  type DecisionPolicy,
  type LaunchMode,
  type ManuscriptEditMode,
  type ResearchIntensity,
  type ReviewFollowupPolicy,
  type StandardProfile,
  type StartResearchTemplate,
  type StartResearchTemplateEntry,
} from '@/lib/startResearch'
import { cn } from '@/lib/utils'
import type {
  BaselineRegistryEntry,
  ConnectorSnapshot,
} from '@/types'
import type { BenchSetupPacket } from '@/lib/types/benchstore'

const copy = {
  en: {
    title: 'Start Research',
    body: 'Create and start.',
    formTitle: 'Context Form',
    formHint: 'Use the left side to fill the launch form. The right side can switch between assistant help and the generated launch preview.',
    setupAgentPanel: 'SetupAgent',
    setupAgentToggle: 'Assist',
    previewPanel: 'Kickoff Preview',
    essentialsTitle: 'Essentials',
    essentialsHint: 'Title, goal, references.',
    advancedTitle: 'Advanced options',
    advancedHint: 'Template, connector, contract.',
    advancedShow: 'Show advanced options',
    advancedHide: 'Hide advanced options',
    preview: 'Launch preview',
    previewBody: 'This preview is generated from the current form. When you create the project, the current form contents are still the final source of truth.',
    manual: 'Manual edit active',
    manualTitle: 'Preview edited manually: form is now locked.',
    manualBody: 'Use “Restore form editing” to regenerate the prompt from the left form and unlock inputs.',
    restore: 'Restore form editing',
    template: 'Saved startup template',
    newTemplate: 'New blank form',
    templateHint:
      'Reuse a previous startup template when the same research shape appears again. Tutorial/reference examples are examples only; always replace endpoint, API key, and model with your actual setup.',
    noTemplates: 'No saved templates yet',
    useTemplate: 'Use template',
    latestDraft: 'latest draft',
    questTarget: 'Project target',
    targetHint: 'This will create a new project and write the first launch request for it.',
    targetMode: 'Project repository',
    targetModeValue: 'Create new project',
    targetRunner: 'Runner',
    targetRunnerValue: 'Codex / local daemon',
    connectorDeliveryLabel: 'Connector delivery',
    connectorDeliveryHelp:
      'Select at most one external connector target for this new project. The dialog preselects the first available option, but you can switch it or keep the project local-only.',
    connectorDeliveryHint: 'A project can keep local access and bind at most one external connector. If the selected target is already bound elsewhere, it will be rebound to this project.',
    connectorSettingsAction: 'Open connector settings',
    connectorEmptyTitle: 'No enabled connector yet',
    connectorEmptyBody:
      'If you want milestone updates outside the web workspace, configure at least one connector first. This is recommended before starting research.',
    connectorUnavailableTitle: 'No selectable connector target yet',
    connectorUnavailableBody:
      'Enabled connectors exist, but no active target is available yet. Send one message to that connector first, or set a default target in Settings.',
    connectorAutoModeLabel: 'Default preselection',
    connectorAutoModeBody: 'The first available connector target is preselected. You can switch it or turn it off before creating the project.',
    connectorSummaryLabel: 'Connector',
    connectorSummaryAuto: 'Local only',
    connectorSummaryLocalBody: 'Project starts in local-only mode. You can bind a connector later if needed.',
    connectorSelectedHint: 'Only one external connector can be bound to a project. If the selected target is already bound elsewhere, creating this project will rebind it here.',
    connectorSourceDefault: 'Default target',
    connectorSourceRecent: 'Recent conversation',
    connectorSourceLast: 'Latest conversation',
    connectorSourceDiscovered: 'Discovered target',
    connectorSourceUnavailable: 'Waiting for first message',
    connectorModeSingle: 'Single endpoint',
    connectorModeMulti: 'Multi-instance',
    connectorSelectPlaceholder: 'Local only',
    connectorSuggestTitle: 'Bind a connector first?',
    connectorSuggestBody:
      'For a smoother experience, it is recommended to configure at least one connector before starting research. Then milestones and progress can reach you outside the web workspace too.',
    connectorSuggestLater: 'Not now',
    connectorSuggestGo: 'Go',
    basics: 'Core research brief',
    references: 'Reference starting point & sources',
    policy: 'Research contract',
    launchModeLabel: 'Launch path',
    launchModeHelp:
      'First choose whether this project should follow the ordinary research workflow or enter through a custom task type.',
    standardProfileLabel: 'Entry type',
    standardProfileHelp:
      'Choose whether Standard mode should follow the paper-oriented research path or the optimization-only path.',
    customProfileLabel: 'Entry type',
    customProfileHelp:
      'In Custom mode, choose what kind of entry this is: continue existing state, run a review audit, handle rebuttal / revision, or follow a freeform brief.',
    reviewFollowupPolicyLabel: 'Review follow-up',
    reviewFollowupPolicyHelp:
      'Only meaningful for the Review task type. Use this to decide whether the system should stop after the audit, continue automatically into experiments and manuscript updates, or pause for approval after the audit.',
    baselineExecutionPolicyLabel: 'Baseline handling',
    baselineExecutionPolicyHelp:
      'Only shown in custom mode. Use this to tell the agent whether it should verify/reproduce a baseline first, reuse current evidence only, or skip baseline reruns unless a reviewer-linked issue truly blocks on them.',
    baselineSourceModeLabel: 'Baseline source preference',
    baselineSourceModeHelp:
      'Choose whether baseline work should prefer verifying an existing local system, attaching a reusable baseline, reproducing from source, repairing a stale baseline, or staying out of the way until baseline work truly blocks progress.',
    executionStartModeLabel: 'Execution start',
    executionStartModeHelp:
      'This only controls the startup baseline route. Choose whether the project should first produce a bounded startup plan and wait for approval, or execute immediately once the startup baseline route is already clear.',
    baselineAcceptanceTargetLabel: 'Baseline acceptance target',
    baselineAcceptanceTargetHelp:
      'Choose how strong the baseline must be before the quest should move into idea selection and experiments.',
    manuscriptEditModeLabel: 'Manuscript update mode',
    manuscriptEditModeHelp:
      'Use this to control whether the system should only give review/rebuttal planning artifacts, produce copy-ready revision text, or require LaTeX-ready revision text and edits.',
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
    reviewMaterialsLabel: 'Reviewer / revision materials',
    reviewMaterialsHelp:
      'Use one URL or one absolute local file/folder path per line for reviewer comments, a decision letter, meta-review notes, or a revision packet.',
    reviewMaterialsPlaceholder:
      'Example: /data/rebuttal/review_comments.md or https://openreview.net/forum?id=demo',
    customBriefLabel: 'Custom brief',
    customBriefHelp:
      'Any extra task-specific instruction that should override the standard full-research launch behavior.',
    customBriefPlaceholder:
      'Example: do not rerun the baseline; first normalize existing results, then decide whether supplementary analysis is still needed.',
    manuscriptEditModeNote:
      'If `LaTeX required` is selected, provide the LaTeX source tree or a local LaTeX folder path in the manuscript/reference inputs when possible.',
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
    tutorialExample: 'Use reference example',
    tutorialExampleHelp:
      'Fill a worked example for reference only. Do not treat its runtime endpoint, API key, or model as a product default.',
    repoLabel: 'Project ID',
    repoPlaceholder: 'Default: next sequential id such as 001, 002, 003',
    repoHelp: 'By default runtime allocates the next sequential project id. You can override it manually when needed.',
    repoLoading: 'Loading next project id…',
    repoAutoAssigned: 'Assigned by runtime on create',
    goalLabel: 'Primary research request',
    goalPlaceholder: 'State the core scientific question, target paper, hypothesis, and what success would look like.',
    goalHelp: 'This should describe the actual problem to solve, not implementation details.',
    baselineRoot: 'Reference starting point',
    baselineRootPlaceholder: 'Select a reusable reference starting point (optional)',
    baselineRootHelp:
      'This is the comparator starting point for this project, not necessarily an industry baseline. It can be a previously confirmed run, an official implementation, or a local existing system that you want DeepScientist to reuse first.',
    baselineVariant: 'Reference variant',
    baselineVariantHelp: 'Optional: choose a specific variant when the reference entry contains multiple variants.',
    baselineUrls: 'Reference implementation links / local paths',
    baselineUrlsPlaceholder: 'One URL or one absolute local file/folder path per line',
    baselineUrlsHelp:
      'Provide repositories, artifacts, or local file/folder paths for the implementation you want to use as the starting comparator or reference implementation.',
    paperUrls: 'Paper / reference sources',
    paperUrlsPlaceholder: 'Papers, repos, or absolute local file/folder paths',
    paperUrlsHelp:
      'These references can be web links or local file/folder paths. Use them for manuscripts, code, benchmarks, or leaderboards.',
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
    languageHelp: 'The launch instructions and later communication will prefer this language by default.',
    promptRequired: 'Prompt preview cannot be empty.',
    goalRequired: 'Please provide a clear research request first.',
    validationTitle: 'Missing required fields',
    validationBody: 'Complete the highlighted field before creating the project.',
    benchAutoAssistPending:
      'SetupAgent is still checking whether the launch form is ready. The Create button unlocks automatically once SetupAgent stops running, even if it replied without writing back the form.',
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
      standard: 'Standard workflow — follow the ordinary research graph.',
      custom: 'Custom entry — continue existing state, review, rebuttal/revision, or a user-defined brief.',
    },
    standardProfileChoiceOption: {
      title: 'Canonical research workflow',
      meta: 'Standard path',
      body: 'Stay on the normal full-research route: baseline, idea, experiment, analysis, and then paper work when justified.',
    },
    standardOptimizationChoiceOption: {
      title: 'Optimization task',
      meta: 'Non-paper path',
      body: 'Skip default paper writing and default analysis-campaign routing. Focus on many justified attempts to reach the strongest durable result.',
    },
    standardOptimizationPaperLock:
      'Optimization task forces non-paper mode for this launch. If you later need paper writing, switch back to the canonical entry type or use a custom entry.',
    customProfileOptions: {
      continue_existing_state: 'Continue existing state — first audit baselines, results, drafts, and current project assets.',
      review_audit: 'Review — run an independent skeptical audit on the current draft or paper package.',
      revision_rebuttal: 'Revision / rebuttal — first interpret reviews, then route extra experiments and writing updates.',
      freeform: 'Other / freeform — follow the custom brief and use only the skills actually needed.',
    },
    customProfileChoiceOptions: {
      continue_existing_state: {
        title: 'Continue existing state',
        meta: 'Reuse-first',
        body: 'Audit existing baselines, results, drafts, and mixed project assets before deciding whether anything expensive must be rerun.',
      },
      review_audit: {
        title: 'Review',
        meta: 'Skeptical audit',
        body: 'Use the current draft or paper package as the active contract and run an independent skeptical review before more writing or finalization.',
      },
      revision_rebuttal: {
        title: 'Rebuttal / revision',
        meta: 'Reviewer-driven',
        body: 'Treat reviewer comments, a revision packet, or a decision letter as the active contract. First map comments to actions, then run only the necessary supplementary work.',
      },
      freeform: {
        title: 'Other / freeform',
        meta: 'User-defined',
        body: 'Follow the custom brief and open only the skills actually needed. Use this when the task does not match the standard custom entry types.',
      },
    },
    baselineExecutionPolicyOptions: {
      auto: {
        title: 'Automatic',
        meta: 'Recommended',
        body: 'Let the startup contract and current evidence decide whether rebuttal work should verify, reuse, or skip baseline reruns.',
      },
      must_reproduce_or_verify: {
        title: 'Verify / reproduce first',
        meta: 'Baseline-first',
        body: 'Before reviewer-linked follow-up work, recover or verify the baseline/comparator that the rebuttal depends on.',
      },
      reuse_existing_only: {
        title: 'Reuse existing only',
        meta: 'No fresh rerun',
        body: 'Trust the current baseline evidence and do not rerun it unless stored results look inconsistent or unusable.',
      },
      skip_unless_blocking: {
        title: 'Skip unless blocking',
        meta: 'Rebuttal-first',
        body: 'Do not spend time rerunning baselines by default. Only do it if a named reviewer-linked issue truly requires a missing comparator.',
      },
    },
    baselineSourceModeOptions: {
      auto: {
        title: 'Automatic',
        meta: 'Recommended',
        body: 'Choose the lightest trustworthy comparator route from the current local evidence, baseline registry, and provided links.',
      },
      verify_local_existing: {
        title: 'Verify local existing',
        meta: 'Local-first',
        body: 'If local code or a local service already exists, verify it as the comparator before reproducing from scratch.',
      },
      attach_registry_baseline: {
        title: 'Attach reusable baseline',
        meta: 'Registry-first',
        body: 'Prefer attaching a reusable registered baseline entry when it already exists.',
      },
      reproduce_from_source: {
        title: 'Reproduce from source',
        meta: 'Full restore',
        body: 'Treat source reproduction as the expected route unless a stronger local shortcut is clearly valid.',
      },
      repair_existing_baseline: {
        title: 'Repair existing baseline',
        meta: 'Repair-first',
        body: 'Prefer repairing the current stale local baseline over rebuilding it from zero.',
      },
      skip_until_blocking: {
        title: 'Skip until blocking',
        meta: 'Research-first',
        body: 'Do not front-load baseline work unless the missing comparator is actually blocking the next research step.',
      },
    },
    executionStartModeOptions: {
      plan_then_execute: {
        title: 'Plan first',
        meta: 'Approval gate',
        body: 'Write a bounded execution plan first, then wait for explicit user approval before heavy reproduction or expensive setup.',
      },
      execute_immediately: {
        title: 'Execute immediately',
        meta: 'Fast start',
        body: 'If the route is already concrete, begin with the smallest useful validating action instead of stopping for a separate planning round.',
      },
    },
    baselineAcceptanceTargetOptions: {
      comparison_ready: {
        title: 'Comparison ready',
        meta: 'Fastest',
        body: 'Once the comparator is trustworthy enough for downstream idea and experiment comparison, continue instead of polishing it indefinitely.',
      },
      paper_repro_ready: {
        title: 'Paper-grade reproduction',
        meta: 'Stricter',
        body: 'Do not treat the baseline as complete until the reproduction is strong enough for paper-facing claims.',
      },
      registry_publishable: {
        title: 'Registry publishable',
        meta: 'Strictest',
        body: 'Treat the baseline as complete only when it is reusable and clean enough to publish as a durable baseline package.',
      },
    },
    reviewFollowupPolicyOptions: {
      audit_only: {
        title: 'Audit only',
        meta: 'Stop after review',
        body: 'Finish the skeptical audit artifacts and stop with a route recommendation instead of running follow-up experiments or manuscript edits automatically.',
      },
      auto_execute_followups: {
        title: 'Auto execute',
        meta: 'Run and revise',
        body: 'After the audit artifacts are durable, continue automatically into the necessary experiments, manuscript deltas, and review-closure work.',
      },
      user_gated_followups: {
        title: 'Ask after audit',
        meta: 'Approval gate',
        body: 'Finish the audit first, then raise a structured decision before expensive experiments or manuscript revisions continue.',
      },
    },
    manuscriptEditModeOptions: {
      none: {
        title: 'No manuscript edits',
        meta: 'Planning only',
        body: 'Limit output to audit / rebuttal planning artifacts and route recommendations.',
      },
      copy_ready_text: {
        title: 'Copy-ready text',
        meta: 'Section deltas',
        body: 'Produce manuscript-facing revision text and section-level replacement wording, without requiring LaTeX-specific delivery.',
      },
      latex_required: {
        title: 'LaTeX required',
        meta: 'LaTeX-ready',
        body: 'When manuscript revision is needed, prefer the provided LaTeX tree as the writing surface and produce LaTeX-ready replacement text; if LaTeX source is missing, make that blocker explicit.',
      },
    },
  },
  zh: {
    title: 'Start Research',
    body: '创建后立即开始。',
    formTitle: '上下文表单',
    formHint: '左侧用于填写启动表单，右侧可在助手协助和启动预览之间切换。',
    setupAgentPanel: 'SetupAgent',
    setupAgentToggle: '协助',
    previewPanel: '启动预览',
    essentialsTitle: '必要信息',
    essentialsHint: '标题、目标、参考资料。',
    advancedTitle: '高级设置',
    advancedHint: '模板、连接器、研究合同。',
    advancedShow: '展开高级设置',
    advancedHide: '收起高级设置',
    preview: '启动预览',
    previewBody: '这里的文本会根据当前表单自动生成。真正创建项目时，仍然以表单里的内容为准。',
    manual: '手工编辑已启用',
    manualTitle: '你已手工修改预览，左侧表单暂时锁定。',
    manualBody: '点击“恢复表单驱动”后，会重新根据左侧表单生成 prompt，并解除锁定。',
    restore: '恢复表单驱动',
    template: '已保存的启动模板',
    newTemplate: '新建空白表单',
    templateHint:
      '当研究形态相近时，可以快速复用过去的启动模板。教程/参考示例只用于参考，里面的端点、API key、模型都必须替换成你的真实配置。',
    noTemplates: '还没有已保存模板',
    useTemplate: '使用模板',
    latestDraft: '最近草稿',
    questTarget: '项目目标',
    targetHint: '这一步会创建一个新的项目，并写入第一条启动请求。',
    targetMode: '项目仓库',
    targetModeValue: '创建新项目',
    targetRunner: 'Runner',
    targetRunnerValue: 'Codex / 本地 daemon',
    connectorDeliveryLabel: '连接器投递',
    connectorDeliveryHelp:
      '给这个新项目最多选择 1 个外部 connector 目标；弹窗会先默认勾选第一个可用项，但你可以改成别的，或者保持仅本地。',
    connectorDeliveryHint: '一个项目会保留本地访问，并且最多只绑定 1 个外部 connector；如果该目标已绑定到别的项目，创建当前项目时会自动替换原绑定。',
    connectorSettingsAction: '打开 Connector 设置',
    connectorEmptyTitle: '还没有启用的 connector',
    connectorEmptyBody:
      '如果你希望在网页之外接收里程碑更新，建议先配置至少一个 connector，再启动研究。',
    connectorUnavailableTitle: '还没有可选的 connector 目标',
    connectorUnavailableBody:
      '已有启用的 connector，但当前还没有可用目标。请先给对应 connector 发一条消息，或在 Settings 中设置默认目标。',
    connectorAutoModeLabel: '默认预选',
    connectorAutoModeBody: '系统会先默认勾选第一个可用 connector 目标；创建前你可以切换，也可以关闭外部绑定。',
    connectorSummaryLabel: '连接器',
    connectorSummaryAuto: '仅本地',
    connectorSummaryLocalBody: '项目将以仅本地模式启动；如果之后需要，你也可以稍后再绑定 connector。',
    connectorSelectedHint: '一个项目最多只能绑定 1 个外部 connector；如果当前选中的目标已经绑定到别的 quest，创建后会自动重绑到当前项目。',
    connectorSourceDefault: '默认目标',
    connectorSourceRecent: '最近会话',
    connectorSourceLast: '最新会话',
    connectorSourceDiscovered: '已发现目标',
    connectorSourceUnavailable: '等待第一条消息',
    connectorModeSingle: '单实例',
    connectorModeMulti: '多实例',
    connectorSelectPlaceholder: '仅本地',
    connectorSuggestTitle: '建议先绑定一个 Connector',
    connectorSuggestBody:
      '为了获得更顺滑的使用体验，建议你先配置至少一个 connector。这样开始研究后，里程碑和进展也能同步发到网页之外。',
    connectorSuggestLater: '暂不',
    connectorSuggestGo: '前往',
    basics: '核心研究简述',
    references: 'Baseline 与参考',
    policy: '研究合同',
    launchModeLabel: '启动路径',
    launchModeHelp:
      '先选择这次项目是走普通科研工作流，还是通过自定义任务入口启动。',
    standardProfileLabel: '入口类型',
    standardProfileHelp:
      '选择 Standard 模式是走论文导向的普通科研路径，还是走只追求最优结果的优化任务路径。',
    customProfileLabel: '入口类型',
    customProfileHelp:
      '在 Custom 模式下，选择这次启动属于哪一种入口：继续已有状态、Review、Rebuttal / Revision，还是自由任务。',
    reviewFollowupPolicyLabel: 'Review 后续动作',
    reviewFollowupPolicyHelp:
      '仅对 Review 任务类型有意义。用来决定系统是在审计后停止，还是自动继续补实验和改稿，还是先审计再等待你的批准。',
    baselineExecutionPolicyLabel: 'Baseline 处理方式',
    baselineExecutionPolicyHelp:
      '仅在 Custom 模式下显示。用来明确告诉 agent：是先验证/复现 baseline，还是只复用现有证据，还是除非 reviewer-linked 问题卡住否则先跳过 baseline 重跑。',
    baselineSourceModeLabel: 'Baseline 来源偏好',
    baselineSourceModeHelp:
      '选择 baseline 更应优先走哪条路：验证本地已有系统、附着可复用 baseline、从源码复现、修复已有 baseline，还是除非真正卡住否则先别让 baseline 变成主线。',
    executionStartModeLabel: '执行启动方式',
    executionStartModeHelp:
      '这只控制启动时的 baseline 路线。选择先输出一个有边界的启动计划并等待你确认，还是在 baseline 启动路线已经足够清楚时直接开始执行。',
    baselineAcceptanceTargetLabel: 'Baseline 验收目标',
    baselineAcceptanceTargetHelp:
      '选择 baseline 至少要达到什么强度，quest 才应该继续进入 idea 和 experiment。',
    manuscriptEditModeLabel: '论文修改模式',
    manuscriptEditModeHelp:
      '用来控制系统是只输出 review/rebuttal 规划产物，还是给出可直接使用的修改文本，还是要求 LaTeX-ready 的修改文本和编辑结果。',
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
    reviewMaterialsLabel: '审稿 / 修改材料',
    reviewMaterialsHelp:
      '每行填写一个 URL，或一个绝对本地文件/文件夹路径，用于 reviewer comments、decision letter、meta-review 或 revision packet。',
    reviewMaterialsPlaceholder:
      '例如：/data/rebuttal/review_comments.md 或 https://openreview.net/forum?id=demo',
    customBriefLabel: '自定义说明',
    customBriefHelp:
      '任何需要覆盖标准 full research 启动方式的额外任务说明，都可以写在这里。',
    customBriefPlaceholder:
      '例如：不要重新跑 baseline；先整理现有结果，再决定是否需要额外分析实验。',
    manuscriptEditModeNote:
      '如果选择了 `LaTeX required`，尽量在论文/参考输入里提供 LaTeX 源目录或本地 LaTeX 文件夹路径。',
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
    tutorialExample: '填入参考示例',
    tutorialExampleHelp:
      '填入一个仅供参考的示例；不要把其中的运行时端点、密钥或模型当作产品默认值。',
    repoLabel: '项目 ID',
    repoPlaceholder: '默认使用下一个顺序编号，例如 001、002、003',
    repoHelp: '默认由 runtime 分配下一个顺序项目 ID；如有需要你也可以手动覆盖。',
    repoLoading: '正在加载下一个项目 ID…',
    repoAutoAssigned: '创建时由 runtime 分配',
    goalLabel: '核心研究请求',
    goalPlaceholder: '清楚说明科学问题、目标论文、核心假设，以及什么结果算成功。',
    goalHelp: '这里应该描述真正要解决的问题，而不是过早写实现细节。',
    baselineRoot: '参考起点',
    baselineRootPlaceholder: '选择一个可复用的参考起点（可选）',
    baselineRootHelp:
      '这里的“参考起点”不是特指业界公开基线，而是这次研究准备先复用、恢复或验证的对照起点。它可以是你之前确认过的方案、论文官方实现，或本地已有版本。运行时会在新项目创建前自动 attach 并 confirm；留空则从零开始建立起点。',
    baselineVariant: '参考实现版本',
    baselineVariantHelp: '可选：当参考实现条目里包含多个版本时，可以在这里指定。',
    baselineUrls: '参考实现链接 / 本地路径',
    baselineUrlsPlaceholder: '每行一个 URL，或一个绝对本地文件/文件夹路径',
    baselineUrlsHelp:
      '这些来源既可以是仓库、artifact，也可以是本地文件或文件夹路径，用于帮助系统更快恢复你想作为对照起点的参考实现。',
    paperUrls: '论文 / 参考来源',
    paperUrlsPlaceholder: '论文、仓库，或绝对本地文件/文件夹路径',
    paperUrlsHelp:
      '这些参考来源既可以是网络链接，也可以是本地文件或文件夹路径，可用于论文、代码、benchmark 或 leaderboard。',
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
    languageHelp: '默认希望启动说明和后续交流优先使用的语言。',
    promptRequired: 'Prompt 预览不能为空。',
    goalRequired: '请先填写清楚研究请求。',
    validationTitle: '还有必填项未填写',
    validationBody: '请先补齐高亮字段，然后再创建项目。',
    benchAutoAssistPending:
      'SetupAgent 仍在确认这次 BenchStore 启动表单是否已经足够可创建。只要 SetupAgent 停止运行，创建按钮就会自动解锁，即使它回复时没有直接回写表单。',
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
      standard: '标准工作流 —— 按普通科研图谱推进。',
      custom: '自定义入口 —— 继续已有状态、做 Review、处理 rebuttal/revision，或执行自定义任务。',
    },
    standardProfileChoiceOption: {
      title: '普通科研工作流',
      meta: '标准主线',
      body: '沿用常规 full research 路线：baseline、方向选择、主实验、补充分析，以及在证据足够后进入论文工作。',
    },
    standardOptimizationChoiceOption: {
      title: '优化任务',
      meta: '非论文路径',
      body: '默认不做论文写作，也不走常规 analysis-campaign 主线，重点是做大量有依据的尝试，尽快逼近最优且可信的结果。',
    },
    standardOptimizationPaperLock:
      '当前选择的是优化任务，本次启动会强制关闭论文模式。如果后续需要写论文，请切回普通科研工作流，或改用 custom 入口。',
    customProfileOptions: {
      continue_existing_state: '继续已有状态 —— 先审计 baseline、结果、草稿和现有项目资产。',
      review_audit: 'Review —— 先对当前 draft / paper package 做一次独立、skeptical 的审计。',
      revision_rebuttal: '审稿修改 / rebuttal —— 先解析 review，再决定补实验和改文。',
      freeform: '其它 / 自由模式 —— 以自定义 brief 为主，只打开真正需要的 skills。',
    },
    customProfileChoiceOptions: {
      continue_existing_state: {
        title: '继续已有状态',
        meta: '先复用',
        body: '先审计现有 baseline、结果、草稿和混合资产，再决定是否真的需要重跑任何昂贵步骤。',
      },
      review_audit: {
        title: 'Review',
        meta: '独立审计',
        body: '把当前 draft / paper package 当作主动合同，先做一次独立、skeptical 的审阅，再决定是否继续写作或收尾。',
      },
      revision_rebuttal: {
        title: 'Rebuttal / Revision',
        meta: '审稿驱动',
        body: '把 reviewer comments、revision packet 或 decision letter 当作主动合同。先拆评论，再只补真正必要的实验和改文。',
      },
      freeform: {
        title: '其它 / 自定义',
        meta: '用户自定义',
        body: '以 custom brief 为主，只打开真正需要的 skills。适合不完全属于标准 custom 入口类型的任务。',
      },
    },
    baselineExecutionPolicyOptions: {
      auto: {
        title: '自动',
        meta: '推荐',
        body: '让启动合同和当前证据自己决定 rebuttal 阶段应该验证、复用还是跳过 baseline 重跑。',
      },
      must_reproduce_or_verify: {
        title: '先验证 / 复现',
        meta: 'Baseline 优先',
        body: '在 reviewer-linked 的后续工作之前，先恢复或验证 rebuttal 真正依赖的 baseline / comparator。',
      },
      reuse_existing_only: {
        title: '只复用现有',
        meta: '不新跑',
        body: '默认信任当前已有 baseline 证据；除非现有结果不一致或不可用，否则不重新跑。',
      },
      skip_unless_blocking: {
        title: '除非卡住否则跳过',
        meta: 'Rebuttal 优先',
        body: '默认先不花时间重跑 baseline；只有当某个 reviewer-linked 问题明确依赖缺失 comparator 时才补跑。',
      },
    },
    baselineSourceModeOptions: {
      auto: {
        title: '自动',
        meta: '推荐',
        body: '根据当前本地证据、baseline registry 与提供的链接，自动选择最轻量但可信的 comparator 路线。',
      },
      verify_local_existing: {
        title: '验证本地已有系统',
        meta: '本地优先',
        body: '如果本地代码或本地服务已经存在，就先把它验证成 comparator，而不是默认从零复现。',
      },
      attach_registry_baseline: {
        title: '附着可复用 baseline',
        meta: 'Registry 优先',
        body: '如果已经存在可复用的 baseline 条目，就优先附着并验证它。',
      },
      reproduce_from_source: {
        title: '从源码复现',
        meta: '完整恢复',
        body: '默认按源码/仓库恢复 baseline，除非后续发现更强的本地捷径。',
      },
      repair_existing_baseline: {
        title: '修复已有 baseline',
        meta: '先修复',
        body: '优先修复当前已有但陈旧或损坏的本地 baseline，而不是从零重建。',
      },
      skip_until_blocking: {
        title: '除非卡住否则跳过',
        meta: '研究优先',
        body: '不要一开始就把 baseline 当主线；只有当缺少 comparator 真正卡住下一步研究时才补。',
      },
    },
    executionStartModeOptions: {
      plan_then_execute: {
        title: '先出计划',
        meta: '需确认',
        body: '先输出一个有边界的执行计划，再等待你的确认后进入重型复现或昂贵 setup。',
      },
      execute_immediately: {
        title: '直接执行',
        meta: '快速启动',
        body: '如果路线已经足够清楚，就直接从最小有用验证动作开始，而不是先单独停下来写计划。',
      },
    },
    baselineAcceptanceTargetOptions: {
      comparison_ready: {
        title: '比较可用即可',
        meta: '最快',
        body: '只要 comparator 已经足够可信，能支撑后续 idea 与 experiment 对比，就继续往前走。',
      },
      paper_repro_ready: {
        title: '论文级复现',
        meta: '更严格',
        body: '在 baseline 足够强、足够稳定、能支撑 paper-facing 结论前，不要轻易视为完成。',
      },
      registry_publishable: {
        title: '可发布到 registry',
        meta: '最严格',
        body: '只有当 baseline 已经足够干净、可复用、可发布成 durable baseline package 时才算完成。',
      },
    },
    reviewFollowupPolicyOptions: {
      audit_only: {
        title: '只做审计',
        meta: '审后停止',
        body: '完成 skeptical 审计产物后就停止，只给出路由建议，不自动补实验或改稿。',
      },
      auto_execute_followups: {
        title: '自动继续执行',
        meta: '补实验并改稿',
        body: '当审计产物落盘后，自动继续进入必要的实验、论文修改和 review closure 工作。',
      },
      user_gated_followups: {
        title: '审后再问我',
        meta: '批准门',
        body: '先完成审计，再把昂贵实验或改稿动作整理成结构化决策，等待你的批准后继续。',
      },
    },
    manuscriptEditModeOptions: {
      none: {
        title: '不改论文',
        meta: '只做规划',
        body: '只输出审计 / rebuttal 规划产物和路由建议，不要求进一步生成可直接替换的论文文本。',
      },
      copy_ready_text: {
        title: '可直接改写文本',
        meta: '段落替换',
        body: '输出面向论文的修改文本和 section-level 替换建议，但不强制要求 LaTeX 格式。',
      },
      latex_required: {
        title: 'LaTeX required',
        meta: 'LaTeX-ready',
        body: '当需要修改论文时，优先把提供的 LaTeX 树当作写作表面，并输出 LaTeX-ready 的替换文本；如果缺少 LaTeX 源，要明确说明阻塞。',
      },
    },
  },
} as const

const selectClassName =
  'h-9 rounded-[10px] border border-[rgba(45,42,38,0.1)] bg-white/78 px-3 text-xs text-[rgba(38,36,33,0.95)] outline-none transition focus:border-[rgba(45,42,38,0.18)] dark:border-[rgba(45,42,38,0.1)] dark:bg-white/82 dark:text-[rgba(38,36,33,0.95)] dark:focus:border-[rgba(45,42,38,0.18)]'

const fieldToneClassName =
  'text-[rgba(38,36,33,0.95)] placeholder:text-[rgba(107,103,97,0.72)] dark:text-[rgba(38,36,33,0.95)] dark:placeholder:text-[rgba(107,103,97,0.72)]'

const panelClass =
  'rounded-xl border border-[rgba(45,42,38,0.09)] bg-[rgba(255,255,255,0.76)] shadow-[0_12px_30px_-24px_rgba(45,42,38,0.32)] backdrop-blur-xl dark:border-[rgba(45,42,38,0.09)] dark:bg-[rgba(255,255,255,0.82)]'

const connectorCatalogByName = new Map(connectorCatalog.map((entry) => [entry.name, entry]))

type StartConnectorChoice = {
  name: string
  label: string
  subtitle: string
  transport: string
  connectionState: string
  instanceMode: 'single_instance' | 'multi_instance'
  targets: Array<{
    conversationId: string
    cardId: string
    targetLabel: string
    compactLabel: string
    detailLabel: string
    sourceKind: 'default' | 'recent' | 'last' | 'discovered'
    boundQuestId?: string | null
    boundQuestTitle?: string | null
    warning?: string | null
  }>
}

type StartSetupFitAssessment = {
  verdict?: string | null
  summary?: string | null
  reason?: string | null
  confidence?: string | null
  is_autonomous_fit?: boolean | null
  reasons?: string[]
  risk_notes?: string[]
}

type StartSetupPreviewPlanStage = {
  title?: string | null
  goal?: string | null
  deliverable?: string | null
  depends_on?: string | null
  switch_condition?: string | null
}

type StartSetupPreviewPlan = {
  summary?: string | null
  stages?: StartSetupPreviewPlanStage[]
  markdown?: string | null
  phases?: StartSetupPreviewPlanStage[]
  risks?: string[]
}

type StartSetupSessionState = {
  suggestedForm: Partial<StartResearchTemplate> | null
  fitAssessment: StartSetupFitAssessment | null
  recommendedWorkspaceMode?: string | null
  launchReadiness?: string | null
  missingConfirmations: string[]
  previewPlan: StartSetupPreviewPlan | null
}

type StartSetupSessionPatch = {
  suggested_form?: Partial<StartResearchTemplate> | null
  fit_assessment?: StartSetupFitAssessment | null
  recommended_workspace_mode?: string | null
  launch_readiness?: string | null
  missing_confirmations?: string[] | null
  preview_plan?: StartSetupPreviewPlan | null
}

const START_SETUP_FORM_META_KEYS = new Set(['form_patch', 'session_patch'])

function cleanStartSetupSuggestedForm(value: unknown): Partial<StartResearchTemplate> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const raw = value as Record<string, unknown>
  const nestedFormPatch = raw.form_patch && typeof raw.form_patch === 'object' && !Array.isArray(raw.form_patch)
    ? (raw.form_patch as Record<string, unknown>)
    : null
  const source = nestedFormPatch || raw
  const cleaned = Object.fromEntries(
    Object.entries(source).filter(([key]) => !START_SETUP_FORM_META_KEYS.has(key))
  ) as Partial<StartResearchTemplate>
  return Object.keys(cleaned).length > 0 ? cleaned : null
}

function nestedStartSetupSessionPatch(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const raw = value as Record<string, unknown>
  if (raw.session_patch && typeof raw.session_patch === 'object' && !Array.isArray(raw.session_patch)) {
    return raw.session_patch as Record<string, unknown>
  }
  if (raw.suggested_form && typeof raw.suggested_form === 'object' && !Array.isArray(raw.suggested_form)) {
    const suggested = raw.suggested_form as Record<string, unknown>
    if (suggested.session_patch && typeof suggested.session_patch === 'object' && !Array.isArray(suggested.session_patch)) {
      return suggested.session_patch as Record<string, unknown>
    }
  }
  return null
}

type SetupPlanDecision = 'autonomous' | 'copilot' | 'provisional'

type LaunchMaterialAttachment = {
  id: string
  label: string
  contentType?: string | null
  kind?: string | null
  location?: string | null
  questRelativePath?: string | null
  path?: string | null
  extractedTextPath?: string | null
  status?: string | null
  source: 'setup' | 'manual'
}

const START_RESEARCH_MAX_ATTACHMENTS = 10
const START_RESEARCH_MAX_ATTACHMENT_SIZE_BYTES = 20 * 1024 * 1024
const SETUP_PLANNING_NOTICE_TOTAL_MS = 28_000
const SETUP_PLANNING_NOTICE_SETTLED_MS = 23_000

function makeLocalAttachmentDraftId() {
  return `launch-draft-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function isImageAttachmentMime(value?: string | null) {
  return String(value || '').trim().toLowerCase().startsWith('image/')
}

const normalizedCopy = {
  en: copy.en,
  zh: normalizeZhUiCopy(copy.zh),
} as const

const deepxivCopy = {
  en: {
    title: 'DeepXiv literature',
    body: 'If configured, `idea` and `scout` can use DeepXiv-first paper discovery and paper triage. Without a token, the prompt should stay on the legacy route.',
    openSetup: 'Open setup',
    openSettings: 'Settings',
  },
  zh: {
    title: 'DeepXiv 文献能力',
    body: '如果已配置 token，`idea` 和 `scout` 可以优先走 DeepXiv 的论文发现与速读路径；如果没有 token，系统提示词应继续使用旧路线。',
    openSetup: '打开配置引导',
    openSettings: '前往设置',
  },
} as const

function buildBenchstoreAutoAssistMessage(setupPacket: BenchSetupPacket, locale: 'en' | 'zh') {
  const startupContract =
    setupPacket.launch_payload?.startup_contract &&
    typeof setupPacket.launch_payload.startup_contract === 'object'
      ? (setupPacket.launch_payload.startup_contract as Record<string, unknown>)
      : null
  const benchmarkContext =
    startupContract?.benchstore_context &&
    typeof startupContract.benchstore_context === 'object'
      ? (startupContract.benchstore_context as Record<string, unknown>)
      : null
  const entryId = String(benchmarkContext?.entry_id || setupPacket.entry_id || '').trim()
  const entryName = String(benchmarkContext?.entry_name || setupPacket.project_title || '').trim()
  const taskDescription =
    String(benchmarkContext?.task_description || setupPacket.benchmark_goal || '').trim() || 'none'
  const sourceFile = String(benchmarkContext?.catalog_source_file || '').trim() || 'unknown'
  const benchmarkLocalPath = String(setupPacket.benchmark_local_path || '').trim() || 'not available'
  const latexPath = String(setupPacket.latex_markdown_path || '').trim() || 'not available'
  const datasetPaths =
    (setupPacket.local_dataset_paths || []).filter((item) => String(item || '').trim().length > 0)
  const constraints = (setupPacket.constraints || []).filter((item) => String(item || '').trim().length > 0)

  if (locale === 'zh') {
    return [
      '这是一次来自 BenchStore Start 的自动启动协助。',
      '当前选中的 benchmark 已经通过上下文完整注入，请把它当成这次 setup 会话的主要事实来源。',
      '',
      '当前 benchmark 信息：',
      `- entry_id: ${entryId || 'unknown'}`,
      `- entry_name: ${entryName || 'unknown'}`,
      `- source_file: ${sourceFile}`,
      `- benchmark_local_path: ${benchmarkLocalPath}`,
      `- local_dataset_paths: ${datasetPaths.length > 0 ? datasetPaths.join(', ') : 'none'}`,
      `- latex_markdown_path: ${latexPath}`,
      `- device_summary: ${setupPacket.device_summary || 'unknown'}`,
      `- device_fit: ${setupPacket.device_fit || 'unknown'}`,
      `- task_description: ${taskDescription}`,
      '',
      '重要规则：',
      '- 完整 benchmark 描述文件已经在 benchmark_context 里注入，尤其是 raw_payload、task_description、paper、resources、environment、download、dataset_download、credential_requirements。不要只看标题或一行摘要。',
      '- 先结合完整 benchmark 描述、当前机器硬件、任务要求和左侧已预填表单，判断哪些信息还缺失。',
      '- 如果这次任务不是 baseline-only，而是要做完整研究，请把主线整理清楚：baseline 只是起点，之后要继续自主优化、争取稳健超越强基线 / SoTA，并确认是否要求方法具备新颖性。',
      '- 如果目标是在主结果成立后继续做分析实验和论文协作，也要主动和用户确认，并把这条链写进表单：优化超越 -> 分析实验 -> 文献搜索 / 图片制作 / 论文撰写。',
      '- 如果 GPU 使用范围、外部 LLM/API Key、付费调用、下载体量、隐私边界这些关键信息还不明确，必须先向用户确认，不能自己假设。',
      '- 如果仍有会实质影响启动路线的缺口，请主动向用户提出 1 到 3 个最关键的问题，问题要短、具体、可直接回答。',
      '- 如果当前信息已经足够，不要为了问问题而问问题，直接使用 artifact.prepare_start_setup_form(form_patch={...}) 提交完整表单。',
      '- 第一轮优先 faithful、小步、保守启动，不要扩展到 benchmark 之外。',
      '- 如果你已经给出结论但还没有提交表单 patch，创建按钮也不应该被永久卡死；一旦 setup quest 停止运行，前端会自动解锁。',
      '',
      constraints.length > 0 ? '当前硬性约束：' : '',
      constraints.length > 0 ? constraints.join('\n') : '',
    ]
      .filter(Boolean)
      .join('\n')
  }

  return [
    'This is an automatic setup-assist session triggered from BenchStore Start.',
    'The selected benchmark is already injected into context and should be treated as the main source of truth for this setup session.',
    '',
    'Current benchmark facts:',
    `- entry_id: ${entryId || 'unknown'}`,
    `- entry_name: ${entryName || 'unknown'}`,
    `- source_file: ${sourceFile}`,
    `- benchmark_local_path: ${benchmarkLocalPath}`,
    `- local_dataset_paths: ${datasetPaths.length > 0 ? datasetPaths.join(', ') : 'none'}`,
    `- latex_markdown_path: ${latexPath}`,
    `- device_summary: ${setupPacket.device_summary || 'unknown'}`,
    `- device_fit: ${setupPacket.device_fit || 'unknown'}`,
    `- task_description: ${taskDescription}`,
    '',
    'Important rules:',
    '- The full benchmark description file is already injected through benchmark_context, especially raw_payload, task_description, paper, resources, environment, download, dataset_download, and credential_requirements. Do not rely on the title or one-line summary alone.',
    '- First combine the full benchmark description, the current machine boundary, the task requirements, and the prefilled form on the left to judge what information is still missing.',
    '- If this is not a baseline-only task but a full research task, make the mainline explicit: baseline is only the starting point, then autonomous optimization, then robust improvement beyond strong baselines / SoTA, and confirm whether novelty is required.',
    '- If the goal is to continue into analysis experiments and later paper-facing collaboration, confirm that explicitly and write the chain into the form: optimization beyond the baseline -> analysis experiments -> literature / figures / writing.',
    '- If GPU scope, external LLM/API keys, paid calls, download volume, or privacy boundaries are still unclear, you must ask the user to confirm them instead of assuming defaults.',
    '- If material gaps remain, proactively ask the user only 1 to 3 short questions that would meaningfully affect the launch path.',
    '- If the current information is already sufficient, do not ask extra questions. Call artifact.prepare_start_setup_form(form_patch={...}) directly and submit the completed form.',
    '- Keep the first launch faithful, conservative, and benchmark-bounded.',
    '- If you answered but did not submit a form patch, the create button must not stay blocked forever; the frontend unlocks automatically once the setup quest is no longer running.',
    '',
    constraints.length > 0 ? 'Current hard constraints:' : '',
    constraints.length > 0 ? constraints.join('\n') : '',
  ]
    .filter(Boolean)
    .join('\n')
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
  if (chatType === 'passive') {
    return `Passive · ${chatId}`
  }
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

function connectorTargetCardId(conversationId: string, profileLabel?: string | null) {
  const parsed = parseConversationId(conversationId)
  const profile = String(profileLabel || parsed?.profile_id || '').trim()
  const chatId =
    parsed?.chat_type === 'passive'
      ? `Passive · ${String(parsed?.chat_id || conversationId || '').trim()}`
      : String(parsed?.chat_id || conversationId || '').trim()
  return [profile, chatId].filter(Boolean).join(' · ') || conversationId
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
      cardId: connectorTargetCardId(target.conversation_id, target.profile_label),
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
        cardId: connectorTargetCardId(recentConversation.conversation_id, recentConversation.profile_label),
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
        cardId: connectorTargetCardId(lastConversationId),
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
    instanceMode: connectorInstanceMode(snapshot),
    targets: normalizedTargets,
  }
}

type StartResearchRightPaneMode = 'assistant' | 'preview'

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
  dataOnboardingId,
  children,
}: {
  label: string
  help?: string
  hint?: string
  dataOnboardingId?: string
  children: ReactNode
}) {
  return (
    <div className="space-y-1" data-onboarding-id={dataOnboardingId}>
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
  localOnlyLabel,
  onChange,
}: {
  label: string
  help?: string
  hint?: string
  items: StartConnectorChoice[]
  value: Record<string, string | null>
  loading?: boolean
  error?: string | null
  localOnlyLabel: string
  onChange: (connectorName: string, next: string | null) => void
}) {
  const enabledItems = items
  const selectableItems = enabledItems.filter((item) => item.targets.length > 0)
  const selectedConnectorName = enabledItems.find((item) => Boolean(value[item.name]))?.name || null
  const flattenedOptions = selectableItems.flatMap((item) =>
    item.targets.map((target) => ({
      key: `${item.name}::${target.conversationId}`,
      connectorName: item.name,
      connectorLabel: item.label,
      target,
    }))
  )
  const selectedConversationId = selectedConnectorName ? value[selectedConnectorName] || null : null
  const selectedOption =
    flattenedOptions.find(
      (item) => item.connectorName === selectedConnectorName && item.target.conversationId === selectedConversationId
    ) || null
  const selectedValue = selectedOption?.key || '__local__'
  const cardItems: ConnectorTargetRadioItem[] = [
    {
      value: '__local__',
      connectorName: 'local',
      connectorLabel: localOnlyLabel,
      targetId: localOnlyLabel,
      boundQuestLabel: '',
      localOnly: true,
    },
    ...flattenedOptions.map((item) => ({
      value: item.key,
      connectorName: item.connectorName,
      connectorLabel: item.connectorLabel,
      targetId: item.target.cardId,
      boundQuestLabel: item.target.boundQuestId ? `Quest ${item.target.boundQuestId}` : 'Unbound',
    })),
  ]

  return (
    <InlineField label={label} help={help} hint={hint}>
      {loading ? (
        <div className="rounded-[14px] border border-[rgba(45,42,38,0.08)] bg-white/60 px-3 py-3 text-[11px] leading-5 text-[rgba(86,82,77,0.82)] dark:border-[rgba(45,42,38,0.08)] dark:bg-white/70 dark:text-[rgba(86,82,77,0.82)]">
          Loading connectors…
        </div>
      ) : (
        <div className="space-y-3">
          <ConnectorTargetRadioGroup
            ariaLabel={label}
            items={cardItems}
            value={selectedValue}
            onChange={(nextValue) => {
              if (!nextValue || nextValue === '__local__') {
                if (selectedConnectorName) {
                  onChange(selectedConnectorName, null)
                }
                return
              }
              const separatorIndex = nextValue.indexOf('::')
              if (separatorIndex < 0) {
                return
              }
              const connectorName = nextValue.slice(0, separatorIndex)
              const conversationId = nextValue.slice(separatorIndex + 2)
              if (!connectorName || !conversationId) {
                return
              }
              onChange(connectorName, conversationId)
            }}
          />

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
  dataOnboardingId,
}: {
  title: string
  children: ReactNode
  muted?: boolean
  dataOnboardingId?: string
}) {
  return (
    <div
      data-onboarding-id={dataOnboardingId}
      className={cn(
        'overflow-x-hidden rounded-[18px] border p-3 sm:rounded-xl',
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

function StartSetupPlanningReviewDialog({
  open,
  locale,
  session,
  hasSuggestedForm = false,
  loading = false,
  onClose,
  onAcceptAutonomous,
  onReviewForm,
  onSwitchToCopilot,
}: {
  open: boolean
  locale: 'en' | 'zh'
  session: StartSetupSessionState
  hasSuggestedForm?: boolean
  loading?: boolean
  onClose: () => void
  onAcceptAutonomous?: (() => void) | undefined
  onReviewForm?: (() => void) | undefined
  onSwitchToCopilot?: (() => void) | undefined
}) {
  if (!open) return null

  const decision = resolveSetupPlanDecision(session)
  const showCopilotAction = decision === 'copilot' && Boolean(onSwitchToCopilot)
  const fitSummary = String(session.fitAssessment?.summary || session.fitAssessment?.reason || '').trim()
  const planSummary = String(session.previewPlan?.summary || '').trim()
  const planMarkdown = String(session.previewPlan?.markdown || '').replace(/\\n/g, '\n').trim()
  const launchReadiness = String(session.launchReadiness || '').trim()
  const recommendedMode = String(session.recommendedWorkspaceMode || session.fitAssessment?.verdict || '').trim()
  const modeLabel = decision === 'copilot'
    ? locale === 'zh' ? '建议协作模式' : 'Copilot recommended'
    : decision === 'provisional'
      ? locale === 'zh' ? '暂可全自动，需确认' : 'Autonomous with confirmations'
      : locale === 'zh' ? '建议全自动' : 'Autonomous recommended'
  const readinessLabel = launchReadiness
    ? launchReadiness.replace(/_/g, ' ')
    : decision === 'autonomous'
      ? 'ready'
      : decision === 'copilot'
        ? 'recommend_copilot'
        : 'needs_confirmation'

  return (
    <div
      className="absolute inset-0 z-[80] flex items-center justify-center bg-black/18 p-[3%] backdrop-blur-[3px]"
      data-onboarding-id="start-research-planning-review-dialog"
    >
      <div className="flex h-[92%] w-[92%] max-w-[1120px] flex-col overflow-hidden rounded-[32px] border border-[rgba(45,42,38,0.10)] bg-[linear-gradient(180deg,rgba(255,252,247,0.98),rgba(248,243,236,0.98))] shadow-[0_44px_140px_-58px_rgba(15,23,42,0.68)] backdrop-blur-2xl">
        <div className="flex shrink-0 items-start justify-between gap-4 border-b border-[rgba(45,42,38,0.08)] px-5 py-4 sm:px-6">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <div className="text-lg font-semibold tracking-[-0.03em] text-[rgba(38,36,33,0.96)]">
                {locale === 'zh' ? '启动规划' : 'Launch plan'}
              </div>
              <span className={cn(
                'rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em]',
                decision === 'copilot'
                  ? 'border-[rgba(154,96,68,0.20)] bg-[rgba(252,244,239,0.9)] text-[rgba(126,77,42,0.95)]'
                  : decision === 'provisional'
                    ? 'border-[rgba(122,148,159,0.22)] bg-[rgba(236,242,245,0.95)] text-[rgba(73,103,117,0.95)]'
                    : 'border-[rgba(88,122,94,0.18)] bg-[rgba(88,122,94,0.10)] text-[rgba(57,96,65,0.95)]'
              )}>
                {modeLabel}
              </span>
            </div>
            <div className="mt-1 text-sm leading-6 text-[rgba(86,82,77,0.78)]">
              {locale === 'zh'
                ? 'SetupAgent 已整理出一份可审阅的启动方案。你可以继续商讨、切到协作模式，或确认直接开始。'
                : 'SetupAgent prepared a reviewable launch plan. You can keep discussing, switch to Copilot, or start directly.'}
            </div>
          </div>
          <button
            type="button"
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[rgba(107,103,97,0.72)] transition hover:bg-black/[0.05] hover:text-[rgba(45,42,38,0.94)]"
            onClick={onClose}
            aria-label={locale === 'zh' ? '关闭启动规划' : 'Close launch plan'}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="grid shrink-0 gap-2 border-b border-[rgba(45,42,38,0.08)] px-5 py-3 sm:grid-cols-3 sm:px-6">
          <div className="rounded-[16px] border border-[rgba(45,42,38,0.08)] bg-white/72 px-3.5 py-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[rgba(107,103,97,0.70)]">{locale === 'zh' ? '推荐模式' : 'Mode'}</div>
            <div className="mt-1 text-sm font-semibold text-[rgba(45,42,38,0.92)]">{recommendedMode || modeLabel}</div>
          </div>
          <div className="rounded-[16px] border border-[rgba(45,42,38,0.08)] bg-white/72 px-3.5 py-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[rgba(107,103,97,0.70)]">{locale === 'zh' ? '启动状态' : 'Readiness'}</div>
            <div className="mt-1 text-sm font-semibold text-[rgba(45,42,38,0.92)]">{readinessLabel}</div>
          </div>
          <div className="rounded-[16px] border border-[rgba(45,42,38,0.08)] bg-white/72 px-3.5 py-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[rgba(107,103,97,0.70)]">{locale === 'zh' ? '待确认' : 'Confirmations'}</div>
            <div className="mt-1 text-sm font-semibold text-[rgba(45,42,38,0.92)]">
              {session.missingConfirmations.length > 0
                ? locale === 'zh' ? `${session.missingConfirmations.length} 项` : `${session.missingConfirmations.length} item(s)`
                : locale === 'zh' ? '暂无' : 'None'}
            </div>
          </div>
        </div>

        <div className="feed-scrollbar min-h-0 flex-1 overflow-y-auto px-5 py-4 sm:px-6">
          {fitSummary || planSummary || session.missingConfirmations.length > 0 ? (
            <div className="mb-4 grid gap-3 lg:grid-cols-[minmax(0,1.2fr)_minmax(260px,0.8fr)]">
              {(fitSummary || planSummary) ? (
                <div className="rounded-[20px] border border-[rgba(45,42,38,0.08)] bg-white/72 px-4 py-3 text-sm leading-6 text-[rgba(56,52,47,0.88)]">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[rgba(107,103,97,0.72)]">
                    {locale === 'zh' ? '判断摘要' : 'Assessment'}
                  </div>
                  <div className="mt-2">{fitSummary || planSummary}</div>
                </div>
              ) : null}
              {session.missingConfirmations.length > 0 ? (
                <div className="rounded-[20px] border border-[rgba(154,96,68,0.16)] bg-[rgba(252,244,239,0.72)] px-4 py-3 text-sm leading-6 text-[rgba(86,82,77,0.9)]">
                  <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[rgba(126,77,42,0.82)]">
                    {locale === 'zh' ? '仍需确认' : 'Still missing'}
                  </div>
                  <ul className="mt-2 list-disc space-y-1 pl-4">
                    {session.missingConfirmations.slice(0, 5).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}

          <div className="rounded-[22px] border border-[rgba(45,42,38,0.08)] bg-white/78 px-4 py-4 shadow-[0_18px_52px_-44px_rgba(45,42,38,0.34)]">
            {planMarkdown ? (
              <AnimatedMarkdownPlan
                content={planMarkdown}
                animateKey={`review:${recommendedMode}:${launchReadiness}`}
                lineDelayMs={60}
                maxAnimatedLines={18}
              />
            ) : (
              <div className="text-sm leading-6 text-[rgba(86,82,77,0.78)]">
                {locale === 'zh' ? 'SetupAgent 已提交判断，但还没有写入可展示的 Markdown 规划。你可以继续商讨，让它补全启动规划。' : 'SetupAgent submitted an assessment but did not provide a displayable Markdown plan yet. Keep discussing to ask for a complete launch plan.'}
              </div>
            )}
          </div>
        </div>

        <div className="flex shrink-0 flex-col gap-2 border-t border-[rgba(45,42,38,0.08)] px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div className="text-xs leading-5 text-[rgba(107,103,97,0.76)]">
            {locale === 'zh' ? '关闭后可继续在 SetupAgent 对话中补充要求。' : 'Close this to keep discussing with SetupAgent.'}
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" variant="outline" className="rounded-full" onClick={onClose} disabled={loading}>
              <MessageSquareText className="mr-1.5 h-4 w-4" />
              {locale === 'zh' ? '还需要商讨' : 'Keep discussing'}
            </Button>
            {hasSuggestedForm && onReviewForm ? (
              <Button type="button" variant="outline" className="rounded-full" onClick={onReviewForm} disabled={loading}>
                {locale === 'zh' ? '查看/编辑表单' : 'Review form'}
              </Button>
            ) : null}
            {showCopilotAction ? (
              <Button type="button" variant="outline" className="rounded-full" onClick={onSwitchToCopilot} disabled={loading}>
                <ArrowUpRight className="mr-1.5 h-4 w-4" />
                {locale === 'zh' ? '转到协作模式' : 'Switch to Copilot'}
              </Button>
            ) : null}
            {hasSuggestedForm && onAcceptAutonomous ? (
              <Button type="button" className="rounded-full bg-[#2D2A26] text-white hover:bg-[#3B3731]" onClick={onAcceptAutonomous} disabled={loading}>
                {decision === 'provisional'
                  ? locale === 'zh' ? '确认风险并启动' : 'Start with confirmations'
                  : locale === 'zh' ? '确认并启动全自动' : 'Start autonomous'}
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  )
}

export function StartSetupAssessmentCard({
  locale,
  session,
  hasSuggestedForm = false,
  loading = false,
  onAcceptAutonomous,
  onReviewForm,
  onSwitchToCopilot,
  onContinueDiscuss,
  onDismiss,
}: {
  locale: 'en' | 'zh'
  session: StartSetupSessionState
  hasSuggestedForm?: boolean
  loading?: boolean
  onAcceptAutonomous?: (() => void) | undefined
  onReviewForm?: (() => void) | undefined
  onSwitchToCopilot?: (() => void) | undefined
  onContinueDiscuss?: (() => void) | undefined
  onDismiss?: (() => void) | undefined
}) {
  const [planCompletePulseKey, setPlanCompletePulseKey] = useState(0)
  const fitSummary = String(session.fitAssessment?.summary || session.fitAssessment?.reason || '').trim()
  const fitVerdict = String(session.fitAssessment?.verdict || '').trim()
  const planSummary = String(session.previewPlan?.summary || '').trim()
  const planMarkdown = String(session.previewPlan?.markdown || '').replace(/\\n/g, '\n').trim()
  const stages = (Array.isArray(session.previewPlan?.phases)
    ? session.previewPlan?.phases
    : Array.isArray(session.previewPlan?.stages)
      ? session.previewPlan?.stages
      : []
  ).slice(0, 4)
  const launchReadiness = String(session.launchReadiness || '').trim()
  const hasContent =
    Boolean(fitSummary) ||
    Boolean(planSummary) ||
    Boolean(planMarkdown) ||
    Boolean(launchReadiness) ||
    session.missingConfirmations.length > 0 ||
    stages.length > 0
  if (!hasContent) return null

  const decision = resolveSetupPlanDecision(session)
  const tone = decision === 'copilot' ? 'warning' : decision === 'provisional' ? 'soft' : fitAssessmentTone(session.recommendedWorkspaceMode || fitVerdict)
  const toneClassName =
    tone === 'warning'
      ? 'border-[rgba(154,96,68,0.18)] bg-[linear-gradient(145deg,rgba(252,244,239,0.96),rgba(244,233,225,0.94))]'
      : tone === 'soft'
        ? 'border-[rgba(122,148,159,0.18)] bg-[linear-gradient(145deg,rgba(248,250,251,0.96),rgba(236,242,245,0.94))]'
        : 'border-[rgba(126,77,42,0.16)] bg-[linear-gradient(145deg,rgba(251,247,241,0.96),rgba(241,233,223,0.94))]'
  const badgeText =
    decision === 'copilot'
      ? locale === 'zh'
        ? 'Recommended mode · 协作模式'
        : 'Copilot recommended'
      : decision === 'provisional'
        ? locale === 'zh'
          ? 'Recommended mode · 需确认'
          : 'Launchable with confirmation'
        : locale === 'zh'
          ? 'Recommended mode · 全自动'
          : 'Good autonomous fit'
  const statusBody =
    decision === 'copilot'
      ? locale === 'zh'
        ? 'SetupAgent 判断这个任务更适合多轮协作。你仍然可以继续全自动，但建议先进入协作模式。'
        : 'SetupAgent thinks this is better handled in Copilot. You can still continue autonomously if you prefer.'
      : decision === 'provisional'
        ? locale === 'zh'
          ? 'SetupAgent 已经准备了规划，但还有少量关键确认项会影响启动路线。'
          : 'SetupAgent prepared a plan, but a few confirmations may still affect launch.'
        : locale === 'zh'
          ? 'SetupAgent 判断这个任务适合在计算机内长时间闭环推进。确认后会把建议表单用于启动。'
          : 'SetupAgent thinks this fits long-running autonomous computer-side work. Confirm to use the proposed form.'

  return (
    <div className={cn('mb-3 flex max-h-[min(74svh,820px)] min-h-0 flex-col overflow-hidden rounded-[24px] border px-4 py-4 shadow-[0_18px_52px_-38px_rgba(45,42,38,0.32)] backdrop-blur-xl', toneClassName)}>
      <div
        key={`setup-mode-bar-${planCompletePulseKey}`}
        className={cn(
          'rounded-[20px] border border-[rgba(45,42,38,0.08)] bg-white/72 px-3.5 py-3',
          planCompletePulseKey > 0 && 'motion-safe:animate-[setup-mode-ready_900ms_cubic-bezier(0.22,1,0.36,1)]'
        )}
      >
        <div className="flex min-w-0 flex-col gap-3">
          <div className="flex min-w-0 items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="inline-flex max-w-full items-center gap-2 rounded-full border border-[rgba(45,42,38,0.08)] bg-white/82 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-[rgba(45,42,38,0.82)]">
                <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
                <span className="min-w-0 truncate">{badgeText}</span>
              </div>
            </div>
            {onDismiss ? (
              <button
                type="button"
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[rgba(107,103,97,0.72)] transition hover:bg-black/[0.04] hover:text-[rgba(45,42,38,0.94)]"
                onClick={onDismiss}
                aria-label={locale === 'zh' ? '关闭建议卡' : 'Dismiss recommendation'}
              >
                <X className="h-4 w-4" />
              </button>
            ) : null}
          </div>
          <div className="min-w-0">
            <div className="text-[12px] leading-6 text-[rgba(86,82,77,0.82)]">{statusBody}</div>
          </div>
          <div className="flex min-w-0 flex-wrap gap-2">
            {onContinueDiscuss ? (
              <Button type="button" variant="outline" className="rounded-full" onClick={onContinueDiscuss} disabled={loading}>
                <MessageSquareText className="mr-1.5 h-4 w-4" />
                {locale === 'zh' ? '继续询问 SetupAgent' : 'Keep discussing'}
              </Button>
            ) : null}
            {decision === 'copilot' && onSwitchToCopilot ? (
              <Button type="button" className="rounded-full bg-[#2D2A26] text-white hover:bg-[#3B3731]" onClick={onSwitchToCopilot} disabled={loading}>
                <ArrowUpRight className="mr-1.5 h-4 w-4" />
                {locale === 'zh' ? '按建议创建协作模式' : 'Create Copilot'}
              </Button>
            ) : null}
            {hasSuggestedForm && onAcceptAutonomous ? (
              <Button type="button" variant={decision === 'copilot' ? 'outline' : 'default'} className="rounded-full" onClick={onAcceptAutonomous} disabled={loading}>
                {decision === 'copilot'
                  ? locale === 'zh'
                    ? '仍继续全自动'
                    : 'Continue autonomous'
                  : locale === 'zh'
                    ? '确认并启动全自动'
                    : 'Confirm autonomous'}
              </Button>
            ) : null}
            {hasSuggestedForm && onReviewForm ? (
              <Button type="button" variant="outline" className="rounded-full" onClick={onReviewForm} disabled={loading}>
                {locale === 'zh' ? '查看/编辑表单' : 'Review form'}
              </Button>
            ) : null}
          </div>
        </div>
      </div>

      <div className="feed-scrollbar mt-3 min-h-0 flex-1 overflow-y-auto pr-1">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          {(fitSummary || launchReadiness) ? (
            <div className="mt-3 text-sm leading-6 text-[rgba(56,52,47,0.92)]">
              {fitSummary || launchReadiness}
            </div>
          ) : null}
          {session.missingConfirmations.length > 0 ? (
            <div className="mt-3 text-[12px] leading-6 text-[rgba(86,82,77,0.82)]">
              <span className="font-semibold">
                {locale === 'zh' ? '仍待确认' : 'Still missing'}:
              </span>{' '}
              {session.missingConfirmations.slice(0, 3).join(locale === 'zh' ? '；' : '; ')}
            </div>
          ) : null}
        </div>
        {tone === 'warning' && onSwitchToCopilot && decision !== 'copilot' ? (
          <Button type="button" variant="outline" className="rounded-full" onClick={onSwitchToCopilot}>
            <ArrowUpRight className="mr-1.5 h-4 w-4" />
            {locale === 'zh' ? '改走协作模式' : 'Switch to Copilot'}
          </Button>
        ) : null}
      </div>

      {planSummary ? (
        <div className="mt-4 rounded-[18px] border border-[rgba(45,42,38,0.08)] bg-white/70 px-3.5 py-3 text-[12px] leading-6 text-[rgba(75,73,69,0.84)]">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[rgba(107,103,97,0.72)]">
            {locale === 'zh' ? '启动预览规划' : 'Launch preview'}
          </div>
          <div className="mt-1.5">{planSummary}</div>
        </div>
      ) : null}

      {planMarkdown ? (
        <div className="mt-4 rounded-[18px] border border-[rgba(45,42,38,0.08)] bg-white/76 px-4 py-3 text-[12px] leading-6 text-[rgba(75,73,69,0.86)]">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[rgba(107,103,97,0.72)]">
            {locale === 'zh' ? '启动规划' : 'Launch plan'}
          </div>
          <div className="feed-scrollbar max-h-[min(54svh,620px)] overflow-y-auto rounded-[14px] bg-[rgba(248,245,240,0.74)] px-3 py-3">
            <AnimatedMarkdownPlan
              content={planMarkdown}
              animateKey={`${session.recommendedWorkspaceMode || ''}:${session.launchReadiness || ''}`}
              lineDelayMs={90}
              onComplete={() => setPlanCompletePulseKey((current) => current + 1)}
            />
          </div>
        </div>
      ) : null}

      {stages.length > 0 ? (
        <div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
          {stages.map((stage, index) => {
            const title = String(stage.title || '').trim() || (locale === 'zh' ? `阶段 ${index + 1}` : `Stage ${index + 1}`)
            const goal = String(stage.goal || '').trim()
            const deliverable = String(stage.deliverable || '').trim()
            const dependsOn = String(stage.depends_on || '').trim()
            const switchCondition = String(stage.switch_condition || '').trim()
            return (
              <div
                key={`${title}-${index}`}
                className="rounded-[18px] border border-[rgba(45,42,38,0.08)] bg-white/74 px-3.5 py-3 text-[12px] leading-6 text-[rgba(75,73,69,0.84)]"
              >
                <div className="text-sm font-semibold text-[rgba(38,36,33,0.94)]">{title}</div>
                {goal ? <div className="mt-1">{goal}</div> : null}
                {deliverable ? (
                  <div className="mt-2 text-[11px] text-[rgba(107,103,97,0.78)]">
                    {locale === 'zh' ? '预期产出' : 'Deliverable'}: {deliverable}
                  </div>
                ) : null}
                {dependsOn ? (
                  <div className="text-[11px] text-[rgba(107,103,97,0.78)]">
                    {locale === 'zh' ? '依赖' : 'Depends on'}: {dependsOn}
                  </div>
                ) : null}
                {switchCondition ? (
                  <div className="text-[11px] text-[rgba(107,103,97,0.78)]">
                    {locale === 'zh' ? '切换条件' : 'Switch condition'}: {switchCondition}
                  </div>
                ) : null}
              </div>
            )
          })}
        </div>
      ) : null}
      </div>
    </div>
  )
}

function LaunchMaterialsCard({
  locale,
  setupAttachments,
  localAttachments,
  onQueueFiles,
  onRemoveAttachment,
}: {
  locale: 'en' | 'zh'
  setupAttachments: LaunchMaterialAttachment[]
  localAttachments: QuestMessageAttachmentDraft[]
  onQueueFiles: (files: File[]) => void
  onRemoveAttachment: (draftId: string) => void
}) {
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  return (
    <SectionCard title={locale === 'zh' ? '启动材料 / 附件' : 'Launch materials / attachments'}>
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(event) => {
          const files = Array.from(event.target.files || [])
          if (files.length > 0) {
            onQueueFiles(files)
          }
          event.target.value = ''
        }}
      />
      <div className="text-[11px] leading-5 text-[rgba(107,103,97,0.72)]">
        {locale === 'zh'
          ? '这里的文件会一起进入最终启动 prompt，并在创建 quest 时自动复制到新 quest 的默认附件目录。'
          : 'These files are injected into the final launch prompt and copied into the new quest when it is created.'}
      </div>

      {setupAttachments.length > 0 ? (
        <div className="rounded-[14px] border border-[rgba(45,42,38,0.08)] bg-white/70 px-3 py-3">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[rgba(107,103,97,0.72)]">
            {locale === 'zh' ? '已从 SetupAgent 会话继承' : 'Inherited from SetupAgent'}
          </div>
          <div className="mt-2 space-y-2">
            {setupAttachments.map((attachment) => (
              <div key={attachment.id} className="rounded-[12px] border border-[rgba(45,42,38,0.08)] bg-[rgba(252,250,246,0.92)] px-3 py-2">
                <div className="truncate text-[12px] font-medium text-[rgba(38,36,33,0.94)]">{attachment.label}</div>
                <div className="mt-0.5 truncate text-[11px] text-[rgba(107,103,97,0.76)]">
                  {attachment.location || (locale === 'zh' ? '位置将在创建时解析' : 'Location will be resolved at launch')}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="rounded-[14px] border border-[rgba(45,42,38,0.08)] bg-white/70 px-3 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[rgba(107,103,97,0.72)]">
              {locale === 'zh' ? '在表单页补充' : 'Add from this form'}
            </div>
            <div className="mt-1 text-[11px] leading-5 text-[rgba(107,103,97,0.76)]">
              {locale === 'zh'
                ? '适合补充数据文件、PDF、说明文档或本地参考材料。'
                : 'Useful for extra datasets, PDFs, notes, or local reference materials.'}
            </div>
          </div>
          <Button type="button" variant="outline" className="rounded-full" onClick={() => fileInputRef.current?.click()}>
            {locale === 'zh' ? '上传附件' : 'Upload files'}
          </Button>
        </div>

        {localAttachments.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {localAttachments.map((attachment) => (
              <div
                key={attachment.draftId}
                className="inline-flex max-w-full items-center gap-2 rounded-full border border-[rgba(45,42,38,0.08)] bg-[rgba(252,250,246,0.92)] px-3 py-1.5 text-[12px] text-[rgba(56,52,47,0.9)]"
              >
                <span className="truncate">{attachment.name}</span>
                <button
                  type="button"
                  className="text-[rgba(107,103,97,0.72)] transition hover:text-[rgba(45,42,38,0.94)]"
                  onClick={() => onRemoveAttachment(attachment.draftId)}
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </SectionCard>
  )
}

function compactTemplateLabel(item: StartResearchTemplateEntry, locale: 'en' | 'zh') {
  const goal = item.goal || (locale === 'zh' ? '未命名模板' : 'Untitled template')
  const title = item.title ? `${item.title} · ` : ''
  return `${title}${goal}`.slice(0, 72)
}

function splitOptionCopy(text: unknown, fallback = 'Unknown option') {
  const normalized = typeof text === 'string' && text.trim() ? text : fallback
  const [title, ...rest] = normalized.split(/\s+[—-]{1,2}\s+/)
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

function buildTutorialStartResearchExample(language: 'en' | 'zh'): Partial<StartResearchTemplate> {
  if (language === 'zh') {
    return {
      title: '复现公开 baseline，并验证一个可计算改进方向',
      goal: [
        '请先复现目标 baseline，确认主指标和运行脚本稳定可用；然后基于误差分析提出一个更高效的改进方向，并执行一轮可比较实验。',
        '',
        '成功标准是 baseline 可信、至少有一组可比较 metric，并形成简短结论与下一步建议。',
      ].join('\\n'),
      baseline_id: '',
      baseline_variant_id: '',
      baseline_source_mode: 'reproduce_from_source',
      execution_start_mode: 'plan_then_execute',
      baseline_acceptance_target: 'paper_repro_ready',
      baseline_urls: '',
      paper_urls: '',
      runtime_constraints: [
        '- 优先控制计算成本。',
        '- 保留日志和关键中间结果。',
        '- 如果证据不足，不要提前下结论。',
      ].join('\\n'),
      objectives: [
        '1. 建立可信 baseline。',
        '2. 跑通一个改进分支。',
        '3. 输出 metric、日志和简短分析。',
      ].join('\\n'),
      need_research_paper: true,
      research_intensity: 'balanced',
      decision_policy: 'autonomous',
      launch_mode: 'standard',
      standard_profile: 'canonical_research_graph',
      custom_profile: 'freeform',
      review_followup_policy: 'audit_only',
      baseline_execution_policy: 'auto',
      manuscript_edit_mode: 'none',
      entry_state_summary: '',
      review_summary: '',
      review_materials: '',
      custom_brief: '',
      user_language: 'zh',
    }
  }

  return {
    title: 'Reproduce a public baseline and test one computable improvement direction',
    goal: [
      'First reproduce the target baseline and verify that the main metric and scripts run reliably. Then propose one efficiency-oriented improvement based on error analysis and run one comparable experiment.',
      '',
      'Success means the baseline is trustworthy, at least one branch produces a clear metric comparison, and the project leaves a concise conclusion with next-step advice.',
    ].join('\\n'),
    baseline_id: '',
    baseline_variant_id: '',
    baseline_source_mode: 'reproduce_from_source',
    execution_start_mode: 'plan_then_execute',
    baseline_acceptance_target: 'paper_repro_ready',
    baseline_urls: '',
    paper_urls: '',
    runtime_constraints: [
      '- Control cost.',
      '- Preserve logs and key intermediate results.',
      '- Do not make claims before evidence is sufficient.',
    ].join('\\n'),
    objectives: [
      '1. Establish a trustworthy baseline.',
      '2. Run one improvement branch.',
      '3. Produce metrics, logs, and a short analysis.',
    ].join('\\n'),
    need_research_paper: true,
    research_intensity: 'balanced',
    decision_policy: 'autonomous',
    launch_mode: 'standard',
    standard_profile: 'canonical_research_graph',
    custom_profile: 'freeform',
    review_followup_policy: 'audit_only',
    baseline_execution_policy: 'auto',
    manuscript_edit_mode: 'none',
    entry_state_summary: '',
    review_summary: '',
    review_materials: '',
    custom_brief: '',
    user_language: 'en',
  }
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

function resolveStartSetupSuggestedFormFromSnapshot(snapshot: unknown): Partial<StartResearchTemplate> | null {
  if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot)) return null
  const startupContract =
    'startup_contract' in snapshot &&
    snapshot.startup_contract &&
    typeof snapshot.startup_contract === 'object' &&
    !Array.isArray(snapshot.startup_contract)
      ? (snapshot.startup_contract as Record<string, unknown>)
      : null
  const startSetupSession =
    startupContract &&
    startupContract.start_setup_session &&
    typeof startupContract.start_setup_session === 'object' &&
    !Array.isArray(startupContract.start_setup_session)
      ? (startupContract.start_setup_session as Record<string, unknown>)
      : null
  const suggestedForm =
    startSetupSession &&
    startSetupSession.suggested_form &&
    typeof startSetupSession.suggested_form === 'object' &&
    !Array.isArray(startSetupSession.suggested_form)
      ? (startSetupSession.suggested_form as Partial<StartResearchTemplate>)
      : null
  return suggestedForm && Object.keys(suggestedForm).length > 0 ? suggestedForm : null
}

function resolveStartSetupSessionFromSnapshot(snapshot: unknown): StartSetupSessionState {
  if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot)) {
    return {
      suggestedForm: null,
      fitAssessment: null,
      recommendedWorkspaceMode: null,
      launchReadiness: null,
      missingConfirmations: [],
      previewPlan: null,
    }
  }
  const startupContract =
    'startup_contract' in snapshot &&
    snapshot.startup_contract &&
    typeof snapshot.startup_contract === 'object' &&
    !Array.isArray(snapshot.startup_contract)
      ? (snapshot.startup_contract as Record<string, unknown>)
      : null
  const startSetupSession =
    startupContract &&
    startupContract.start_setup_session &&
    typeof startupContract.start_setup_session === 'object' &&
    !Array.isArray(startupContract.start_setup_session)
      ? (startupContract.start_setup_session as Record<string, unknown>)
      : null
  const suggestedForm = cleanStartSetupSuggestedForm(startSetupSession?.suggested_form)
  const nestedSessionPatch = nestedStartSetupSessionPatch(startSetupSession)
  const sessionSource = nestedSessionPatch ? { ...startSetupSession, ...nestedSessionPatch } : startSetupSession
  const fitAssessment =
    sessionSource &&
    sessionSource.fit_assessment &&
    typeof sessionSource.fit_assessment === 'object' &&
    !Array.isArray(sessionSource.fit_assessment)
      ? (sessionSource.fit_assessment as StartSetupFitAssessment)
      : null
  const launchReadiness = String(sessionSource?.launch_readiness || '').trim() || null
  const rawPreviewPlan =
    sessionSource &&
    sessionSource.preview_plan &&
    typeof sessionSource.preview_plan === 'object' &&
    !Array.isArray(sessionSource.preview_plan)
      ? (sessionSource.preview_plan as StartSetupPreviewPlan)
      : null
  const missingConfirmations = Array.isArray(sessionSource?.missing_confirmations)
    ? sessionSource.missing_confirmations
        .map((item) => String(item || '').trim())
        .filter(Boolean)
    : []
  return {
    suggestedForm,
    fitAssessment,
    recommendedWorkspaceMode: String(sessionSource?.recommended_workspace_mode || '').trim() || null,
    launchReadiness,
    missingConfirmations,
    previewPlan: launchReadiness === 'ready' && missingConfirmations.length === 0 ? rawPreviewPlan : null,
  }
}

function normalizeStartSetupSessionPatch(value: unknown): StartSetupSessionPatch | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const raw = value as Record<string, unknown>
  const patch: StartSetupSessionPatch = {}
  const nestedPatch = nestedStartSetupSessionPatch(raw)
  const sessionRaw = nestedPatch ? { ...raw, ...nestedPatch } : raw
  const suggestedForm = cleanStartSetupSuggestedForm(raw.suggested_form)
  if (suggestedForm) {
    patch.suggested_form = suggestedForm
  }
  if (sessionRaw.fit_assessment && typeof sessionRaw.fit_assessment === 'object' && !Array.isArray(sessionRaw.fit_assessment)) {
    patch.fit_assessment = sessionRaw.fit_assessment as StartSetupFitAssessment
  }
  if ('recommended_workspace_mode' in sessionRaw) {
    patch.recommended_workspace_mode = String(sessionRaw.recommended_workspace_mode || '').trim() || null
  }
  if ('launch_readiness' in sessionRaw) {
    patch.launch_readiness = String(sessionRaw.launch_readiness || '').trim() || null
  }
  if (sessionRaw.preview_plan && typeof sessionRaw.preview_plan === 'object' && !Array.isArray(sessionRaw.preview_plan)) {
    const readiness = String(patch.launch_readiness || sessionRaw.launch_readiness || '').trim().toLowerCase()
    if (readiness === 'ready') {
      patch.preview_plan = sessionRaw.preview_plan as StartSetupPreviewPlan
    }
  }
  if (Array.isArray(sessionRaw.missing_confirmations)) {
    patch.missing_confirmations = sessionRaw.missing_confirmations
      .map((item) => String(item || '').trim())
      .filter(Boolean)
  }
  return Object.keys(patch).length > 0 ? patch : null
}

function mergeStartSetupSessionState(
  base: StartSetupSessionState,
  patch: StartSetupSessionPatch | null
): StartSetupSessionState {
  if (!patch) return base
  return {
    suggestedForm: patch.suggested_form && Object.keys(patch.suggested_form).length > 0
      ? { ...(base.suggestedForm || {}), ...patch.suggested_form }
      : base.suggestedForm,
    fitAssessment: patch.fit_assessment
      ? { ...(base.fitAssessment || {}), ...patch.fit_assessment }
      : base.fitAssessment,
    recommendedWorkspaceMode: patch.recommended_workspace_mode ?? base.recommendedWorkspaceMode,
    launchReadiness: patch.launch_readiness ?? base.launchReadiness,
    missingConfirmations: patch.missing_confirmations ?? base.missingConfirmations,
    previewPlan: patch.preview_plan
      ? { ...(base.previewPlan || {}), ...patch.preview_plan }
      : String(patch.launch_readiness || '').trim().toLowerCase() && String(patch.launch_readiness || '').trim().toLowerCase() !== 'ready'
        ? null
        : base.previewPlan,
  }
}

function normalizeLaunchMaterialAttachment(
  value: unknown,
  source: LaunchMaterialAttachment['source']
): LaunchMaterialAttachment | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const item = value as Record<string, unknown>
  const questRelativePath = String(item.quest_relative_path || '').trim() || null
  const path = String(item.path || '').trim() || null
  const location =
    String(item.extracted_text_path || '').trim() ||
    questRelativePath ||
    path ||
    String(item.asset_url || '').trim() ||
    null
  const id =
    questRelativePath ||
    path ||
    String(item.draft_id || '').trim() ||
    String(item.asset_url || '').trim() ||
    String(item.file_name || '').trim() ||
    String(item.name || '').trim()
  if (!id) return null
  const label =
    String(item.name || '').trim() ||
    String(item.file_name || '').trim() ||
    questRelativePath ||
    path ||
    id
  return {
    id,
    label,
    contentType: String(item.content_type || item.mime_type || '').trim() || null,
    kind: String(item.kind || '').trim() || null,
    location,
    questRelativePath,
    path,
    extractedTextPath: String(item.extracted_text_path || '').trim() || null,
    status: String(item.status || '').trim() || null,
    source,
  }
}

function collectSetupLaunchAttachments(feed: unknown[]): LaunchMaterialAttachment[] {
  const deduped = new Map<string, LaunchMaterialAttachment>()
  for (const value of feed) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) continue
    const item = value as Record<string, unknown>
    if (String(item.type || '').trim() !== 'message' || String(item.role || '').trim() !== 'user') continue
    const attachments = Array.isArray(item.attachments) ? item.attachments : []
    for (const attachment of attachments) {
      const normalized = normalizeLaunchMaterialAttachment(attachment, 'setup')
      if (!normalized) continue
      deduped.set(normalized.id, normalized)
    }
  }
  return Array.from(deduped.values())
}

function mergeLaunchMaterialAttachments(
  setupAttachments: LaunchMaterialAttachment[],
  localAttachments: QuestMessageAttachmentDraft[]
) {
  const deduped = new Map<string, LaunchMaterialAttachment>()
  for (const attachment of setupAttachments) {
    deduped.set(attachment.id, attachment)
  }
  for (const draft of localAttachments) {
    const normalized = normalizeLaunchMaterialAttachment(
      {
        draft_id: draft.draftId,
        name: draft.name,
        file_name: draft.name,
        content_type: draft.contentType,
        kind: draft.kind,
        quest_relative_path: draft.questRelativePath,
        path: draft.path,
        extracted_text_path: draft.extractedTextPath,
        status: draft.status,
      },
      'manual'
    )
    if (!normalized) continue
    deduped.set(`manual:${normalized.id}`, { ...normalized, id: `manual:${normalized.id}` })
  }
  return Array.from(deduped.values())
}

function fitAssessmentTone(value: string | null | undefined) {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized.includes('copilot') || normalized.includes('collab')) return 'warning'
  if (normalized.includes('possible') || normalized.includes('provisional')) return 'soft'
  return 'good'
}

function resolveSetupPlanDecision(session: StartSetupSessionState): SetupPlanDecision {
  if (session.fitAssessment?.is_autonomous_fit === false) return 'copilot'
  if (session.fitAssessment?.is_autonomous_fit === true) return 'autonomous'
  const combined = [
    session.recommendedWorkspaceMode,
    session.launchReadiness,
    session.fitAssessment?.verdict,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  if (combined.includes('copilot') || combined.includes('collab')) return 'copilot'
  if (combined.includes('provisional') || combined.includes('confirm') || combined.includes('needs')) return 'provisional'
  return 'autonomous'
}

function isSetupPlanningLaunchReady(
  session: StartSetupSessionState,
  form?: Partial<StartResearchTemplate> | null
): boolean {
  const readiness = String(session.launchReadiness || '').trim().toLowerCase()
  if (readiness !== 'ready') return false
  if (session.missingConfirmations.length > 0) return false
  const mergedForm = { ...(form || {}), ...(session.suggestedForm || {}) }
  const goal = String(mergedForm.goal || '').trim()
  const objectives = String(mergedForm.objectives || '').trim()
  const runtimeConstraints = String(mergedForm.runtime_constraints || '').trim()
  if (!goal || !objectives || !runtimeConstraints) return false
  const markdown = String(session.previewPlan?.markdown || '').trim()
  const summary = String(session.previewPlan?.summary || '').trim()
  const stages = Array.isArray(session.previewPlan?.phases)
    ? session.previewPlan?.phases
    : Array.isArray(session.previewPlan?.stages)
      ? session.previewPlan?.stages
      : []
  return Boolean(markdown || summary || (stages && stages.length > 0))
}

const START_SETUP_STALE_RUNNING_TIMEOUT_MS = 90_000

function isSetupQuestActivelyRunning(snapshot: unknown, options?: { hasLiveRun?: boolean; activeToolCount?: number; streaming?: boolean }) {
  if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot)) {
    return Boolean(options?.hasLiveRun || options?.streaming || (options?.activeToolCount || 0) > 0)
  }
  const record = snapshot as Record<string, unknown>
  const activeRunId = String(record.active_run_id ?? '').trim()
  const runtimeStatus = String(record.runtime_status ?? record.status ?? '').trim().toLowerCase()
  const bashRunningCount =
    record.counts && typeof record.counts === 'object' && !Array.isArray(record.counts)
      ? Number((record.counts as Record<string, unknown>).bash_running_count || 0)
      : 0
  const latestActivityRaw = String(record.last_tool_activity_at ?? record.last_transition_at ?? '').trim()
  const latestActivityMs = latestActivityRaw ? Date.parse(latestActivityRaw) : Number.NaN
  const staleWithoutLiveSignals =
    !options?.hasLiveRun &&
    !options?.streaming &&
    (options?.activeToolCount || 0) === 0 &&
    Number.isFinite(latestActivityMs) &&
    Date.now() - latestActivityMs > START_SETUP_STALE_RUNNING_TIMEOUT_MS

  // If there are live signals (streaming, active tools), always consider it running
  if (options?.hasLiveRun || options?.streaming || (options?.activeToolCount || 0) > 0) return true

  // If stale without any live signals, consider it stopped
  if (staleWithoutLiveSignals) return false

  // Check for active run or running status
  if (activeRunId) return true
  if (runtimeStatus === 'running' || runtimeStatus === 'retrying') return true
  if (Number.isFinite(bashRunningCount) && bashRunningCount > 0) return true

  return false
}

export function CreateProjectDialog({
  open,
  loading,
  error,
  initialGoal = '',
  setupPacket = null,
  setupQuestId = null,
  setupQuestCreating = false,
  onBack,
  onClose,
  onRequestSetupAgent,
  onSwitchToCopilot,
  onOpenBenchStore,
  onCreate,
}: {
  open: boolean
  loading?: boolean
  error?: string | null
  initialGoal?: string
  setupPacket?: BenchSetupPacket | null
  setupQuestId?: string | null
  setupQuestCreating?: boolean
  onBack?: () => void
  onClose: () => void
  onRequestSetupAgent?: (payload: {
    message: string
    form: StartResearchTemplate
    setupPacket?: BenchSetupPacket | null
    attachments?: QuestMessageAttachmentDraft[]
    createOnly?: boolean
  }) => Promise<void>
  onSwitchToCopilot?: (payload: {
    title: string
    message: string
    setupQuestId?: string | null
    setupAttachments?: LaunchMaterialAttachment[]
    localAttachments?: QuestMessageAttachmentDraft[]
  }) => Promise<void> | void
  onOpenBenchStore?: () => void
  onCreate: (payload: {
    title: string
    goal: string
    quest_id?: string
    requested_connector_bindings?: Array<{ connector: string; conversation_id?: string | null }>
    requested_baseline_ref?: { baseline_id: string; variant_id?: string | null } | null
    startup_contract?: Record<string, unknown> | null
    launch_materials?: {
      setup_quest_id?: string | null
      setup_attachments?: LaunchMaterialAttachment[]
      local_attachments?: QuestMessageAttachmentDraft[]
    } | null
  }) => Promise<void>
}) {
  const navigate = useNavigate()
  const { locale } = useI18n()
  const onboardingStatus = useOnboardingStore((state) => state.status)
  const t = normalizedCopy[locale]
  const deepxivT = deepxivCopy[locale]
  const backLabel = locale === 'zh' ? '返回' : 'Back'
  const [entryMode, setEntryMode] = useState<'intake' | 'form'>(setupPacket ? 'form' : 'intake')
  const [rightPaneMode, setRightPaneMode] = useState<StartResearchRightPaneMode>('assistant')
  const [showAdvanced, setShowAdvanced] = useState(true)
  const [form, setForm] = useState<StartResearchTemplate>(defaultStartResearchTemplate(locale))
  const [intakeMessage, setIntakeMessage] = useState(initialGoal)
  const [localSetupSessionPatch, setLocalSetupSessionPatch] = useState<StartSetupSessionPatch | null>(null)
  const [promptDraft, setPromptDraft] = useState('')
  const [manualOverride, setManualOverride] = useState(false)
  const [questIdManualOverride, setQuestIdManualOverride] = useState(false)
  const [suggestedQuestId, setSuggestedQuestId] = useState('')
  const [suggestedQuestIdLoading, setSuggestedQuestIdLoading] = useState(false)
  const [templates, setTemplates] = useState<StartResearchTemplateEntry[]>([])
  const [selectedTemplateId, setSelectedTemplateId] = useState('__new__')
  const [baselineEntries, setBaselineEntries] = useState<BaselineRegistryEntry[]>([])
  const [baselineEntriesLoading, setBaselineEntriesLoading] = useState(false)
  const [baselineEntriesError, setBaselineEntriesError] = useState<string | null>(null)
  const [connectors, setConnectors] = useState<ConnectorSnapshot[]>([])
  const [connectorsLoading, setConnectorsLoading] = useState(false)
  const [connectorsError, setConnectorsError] = useState<string | null>(null)
  const [deepxivSetupOpen, setDeepxivSetupOpen] = useState(false)
  const [validationDialogOpen, setValidationDialogOpen] = useState(false)
  const [validationMessage, setValidationMessage] = useState('')
  const [validationTarget, setValidationTarget] = useState<'title' | 'goal' | null>(null)
  const titleInputRef = useRef<HTMLInputElement | null>(null)
  const goalTextareaRef = useRef<HTMLTextAreaElement | null>(null)
  const [activeRunnerName, setActiveRunnerName] = useState(() => normalizeBuiltinRunnerName("codex"))
  const [selectedConnectorBindings, setSelectedConnectorBindings] = useState<Record<string, string | null>>({})
  const [agentManagedValues, setAgentManagedValues] = useState<Partial<StartResearchTemplate>>({})
  const [localLaunchAttachments, setLocalLaunchAttachments] = useState<QuestMessageAttachmentDraft[]>([])
  const [setupPlanningNoticeDismissed, setSetupPlanningNoticeDismissed] = useState(false)
  const [setupPlanningNoticeOpen, setSetupPlanningNoticeOpen] = useState(false)
  const [setupPlanningNoticeClosing, setSetupPlanningNoticeClosing] = useState(false)
  const [setupPlanningNoticeElapsedMs, setSetupPlanningNoticeElapsedMs] = useState(0)
  const [planningReviewDismissedKey, setPlanningReviewDismissedKey] = useState<string | null>(null)
  const [benchAutoAssistReady, setBenchAutoAssistReady] = useState(() => !setupPacket)
  const referenceTemplates = useMemo(() => listReferenceStartResearchTemplates(), [])
  const setupWorkspace = useQuestWorkspace(setupQuestId)
  const autoBenchAssistStartedRef = useRef<string | null>(null)
  const setupPlanningNoticeStartedAtRef = useRef<number | null>(null)
  const setupPlanningPollStartedAtRef = useRef<number | null>(null)
  const latestFormRef = useRef(form)
  const latestAgentManagedValuesRef = useRef(agentManagedValues)

  useEffect(() => {
    latestFormRef.current = form
  }, [form])

  useEffect(() => {
    latestAgentManagedValuesRef.current = agentManagedValues
  }, [agentManagedValues])

  useEffect(() => {
    if (!open) return
    let active = true
    void client.configDocument('config').then((payload) => {
      if (!active) return
      const structured = payload.meta?.structured_config && typeof payload.meta.structured_config === 'object'
        ? (payload.meta.structured_config as Record<string, unknown>)
        : {}
      setActiveRunnerName(normalizeBuiltinRunnerName(structured.default_runner))
    }).catch(() => {})
    return () => {
      active = false
    }
  }, [open])

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

  const customProfileItems = useMemo(
    () =>
      (['continue_existing_state', 'review_audit', 'revision_rebuttal', 'freeform'] as const).map((value) => ({
        value,
        title: t.customProfileChoiceOptions[value].title,
        meta: t.customProfileChoiceOptions[value].meta,
        description: t.customProfileChoiceOptions[value].body,
      })),
    [t]
  )

  const launchModeItems = useMemo(
    () =>
      (['standard', 'custom'] as const).map((value) => {
        const copy = splitOptionCopy(
          t.launchModeOptions?.[value],
          value === 'custom'
            ? locale === 'zh'
              ? '自定义入口'
              : 'Custom entry'
            : locale === 'zh'
              ? '标准工作流'
              : 'Standard workflow'
        )
        return {
          value,
          title: copy.title,
          meta: value === 'standard' ? (locale === 'zh' ? '默认' : 'Default') : 'Custom',
          description: copy.description,
        }
      }),
    [locale, t]
  )

  const standardProfileItems = useMemo(
    () =>
      (['canonical_research_graph', 'optimization_task'] as const).map((value) => {
        const option =
          value === 'optimization_task'
            ? t.standardOptimizationChoiceOption
            : t.standardProfileChoiceOption
        return {
          value,
          title: option.title,
          meta: option.meta,
          description: option.body,
        }
      }),
    [t]
  )

  const reviewFollowupPolicyItems = useMemo(
    () =>
      (['audit_only', 'auto_execute_followups', 'user_gated_followups'] as const).map((value) => ({
        value,
        title: t.reviewFollowupPolicyOptions[value].title,
        meta: t.reviewFollowupPolicyOptions[value].meta,
        description: t.reviewFollowupPolicyOptions[value].body,
      })),
    [t]
  )

  const baselineExecutionPolicyItems = useMemo(
    () =>
      (['auto', 'must_reproduce_or_verify', 'reuse_existing_only', 'skip_unless_blocking'] as const).map((value) => ({
        value,
        title: t.baselineExecutionPolicyOptions[value].title,
        meta: t.baselineExecutionPolicyOptions[value].meta,
        description: t.baselineExecutionPolicyOptions[value].body,
      })),
    [t]
  )

  const baselineSourceModeItems = useMemo(
    () =>
      (
        [
          'auto',
          'verify_local_existing',
          'attach_registry_baseline',
          'reproduce_from_source',
          'repair_existing_baseline',
          'skip_until_blocking',
        ] as const
      ).map((value) => ({
        value,
        title: t.baselineSourceModeOptions[value].title,
        meta: t.baselineSourceModeOptions[value].meta,
        description: t.baselineSourceModeOptions[value].body,
      })),
    [t]
  )

  const executionStartModeItems = useMemo(
    () =>
      (['plan_then_execute', 'execute_immediately'] as const).map((value) => ({
        value,
        title: t.executionStartModeOptions[value].title,
        meta: t.executionStartModeOptions[value].meta,
        description: t.executionStartModeOptions[value].body,
      })),
    [t]
  )

  const baselineAcceptanceTargetItems = useMemo(
    () =>
      (['comparison_ready', 'paper_repro_ready', 'registry_publishable'] as const).map((value) => ({
        value,
        title: t.baselineAcceptanceTargetOptions[value].title,
        meta: t.baselineAcceptanceTargetOptions[value].meta,
        description: t.baselineAcceptanceTargetOptions[value].body,
      })),
    [t]
  )

  const manuscriptEditModeItems = useMemo(
    () =>
      (['none', 'copy_ready_text', 'latex_required'] as const).map((value) => ({
        value,
        title: t.manuscriptEditModeOptions[value].title,
        meta: t.manuscriptEditModeOptions[value].meta,
        description: t.manuscriptEditModeOptions[value].body,
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
    () =>
      splitOptionCopy(
        t.launchModeOptions?.[form.launch_mode],
        form.launch_mode === 'custom'
          ? locale === 'zh'
            ? '自定义入口'
            : 'Custom entry'
          : locale === 'zh'
            ? '标准工作流'
            : 'Standard workflow'
      ),
    [form.launch_mode, locale, t]
  )

  useEffect(() => {
    if (!open) {
      return
    }
    setEntryMode(setupPacket ? 'form' : 'intake')
    setRightPaneMode('assistant')
    setBenchAutoAssistReady(!(setupPacket && onRequestSetupAgent))
    autoBenchAssistStartedRef.current = null
    setIntakeMessage(initialGoal || '')
    setLocalLaunchAttachments((current) => {
      current.forEach((item) => {
        if (item.previewUrl?.startsWith('blob:')) {
          URL.revokeObjectURL(item.previewUrl)
        }
      })
      return []
    })
    setSetupPlanningNoticeDismissed(false)
    setSetupPlanningNoticeElapsedMs(0)
    setupPlanningNoticeStartedAtRef.current = null
    setupPlanningPollStartedAtRef.current = null
    if (setupPacket && setupPacket.suggested_form && typeof setupPacket.suggested_form === 'object') {
      const suggested = setupPacket.suggested_form as Partial<StartResearchTemplate>
      const next = {
        ...defaultStartResearchTemplate(locale),
        ...suggested,
        quest_id: '',
        user_language: locale,
      }
      setForm(next)
      setTemplates(loadStartResearchHistory())
      setSelectedTemplateId('__new__')
      setManualOverride(false)
      setQuestIdManualOverride(false)
      setSuggestedQuestId('')
      setSelectedConnectorBindings({})
      setShowAdvanced(true)
      setAgentManagedValues(suggested)
      return
    }
    const next = defaultStartResearchTemplate(locale)
    const tutorialSeed = onboardingStatus === 'running' ? buildTutorialStartResearchExample(locale) : null
    const withSeed = {
      ...next,
      ...(tutorialSeed || {}),
      goal: initialGoal || tutorialSeed?.goal || next.goal,
      user_language: tutorialSeed?.user_language || locale,
    }
    setForm({
      ...withSeed,
      quest_id: '',
    })
    setTemplates(loadStartResearchHistory())
    setSelectedTemplateId('__new__')
    setManualOverride(false)
    setQuestIdManualOverride(false)
    setSuggestedQuestId('')
    setSelectedConnectorBindings({})
    setShowAdvanced(true)
    setAgentManagedValues({})
    setLocalSetupSessionPatch(null)
  }, [initialGoal, locale, onboardingStatus, open, setupPacket])

  useEffect(() => {
    if (open) return
    setBenchAutoAssistReady(true)
    autoBenchAssistStartedRef.current = null
  }, [open])

  const durableSetupSessionBase = useMemo(
    () => resolveStartSetupSessionFromSnapshot(setupWorkspace.snapshot),
    [setupWorkspace.snapshot]
  )

  const durableSetupSession = useMemo(
    () => mergeStartSetupSessionState(durableSetupSessionBase, localSetupSessionPatch),
    [durableSetupSessionBase, localSetupSessionPatch]
  )

  const durableSetupSuggestedForm = useMemo(
    () => durableSetupSession.suggestedForm || resolveStartSetupSuggestedFormFromSnapshot(setupWorkspace.snapshot),
    [durableSetupSession.suggestedForm, setupWorkspace.snapshot]
  )

  const setupAssessmentKey = useMemo(
    () => [
      durableSetupSession.recommendedWorkspaceMode || '',
      durableSetupSession.launchReadiness || '',
      String(durableSetupSession.previewPlan?.markdown || '').slice(0, 96),
      JSON.stringify(durableSetupSuggestedForm || {}),
    ].join('|'),
    [durableSetupSession.launchReadiness, durableSetupSession.previewPlan?.markdown, durableSetupSession.recommendedWorkspaceMode, durableSetupSuggestedForm]
  )

  const transformSetupAgentSubmitMessage = useCallback(
    (message: string) => {
      return message
    },
    []
  )

  const setupLaunchAttachments = useMemo(
    () => collectSetupLaunchAttachments(setupWorkspace.feed),
    [setupWorkspace.feed]
  )

  const launchMaterialAttachments = useMemo(
    () => mergeLaunchMaterialAttachments(setupLaunchAttachments, localLaunchAttachments),
    [localLaunchAttachments, setupLaunchAttachments]
  )

  const setupQuestStillRunning = useMemo(
    () =>
      isSetupQuestActivelyRunning(setupWorkspace.snapshot, {
        hasLiveRun: setupWorkspace.hasLiveRun,
        activeToolCount: setupWorkspace.activeToolCount,
        streaming: setupWorkspace.streaming,
      }),
    [
      setupWorkspace.activeToolCount,
      setupWorkspace.hasLiveRun,
      setupWorkspace.snapshot,
      setupWorkspace.streaming,
    ]
  )

  const durableSetupHasPlanningContent = useMemo(
    () => isSetupPlanningLaunchReady(
      durableSetupSession.suggestedForm ? durableSetupSession : { ...durableSetupSession, suggestedForm: durableSetupSuggestedForm },
      form
    ),
    [durableSetupSession, durableSetupSuggestedForm, form]
  )

  const visibleSetupSession = durableSetupSession
  const planningPreviewVisible = durableSetupHasPlanningContent
  const planningReviewOpen = Boolean(
    planningPreviewVisible &&
    setupAssessmentKey &&
    planningReviewDismissedKey !== setupAssessmentKey
  )

  const closePlanningReview = useCallback(() => {
    if (setupAssessmentKey) {
      setPlanningReviewDismissedKey(setupAssessmentKey)
    }
    setRightPaneMode('assistant')
  }, [setupAssessmentKey])

  const setupPlanningNoticeSettled = setupPlanningNoticeElapsedMs >= SETUP_PLANNING_NOTICE_SETTLED_MS
  const setupPlanningNoticePhaseIndex =
    setupPlanningNoticeElapsedMs >= 12_000 ? 2 :
    setupPlanningNoticeElapsedMs >= 5_000 ? 1 : 0
  const setupPlanningNoticeCardRevealCount = setupPlanningNoticeElapsedMs >= 17_000 ? 4 : setupPlanningNoticeElapsedMs >= 11_000 ? 3 : setupPlanningNoticeElapsedMs >= 5_000 ? 2 : 1
  const setupPlanningNoticeProgress = setupPlanningNoticeSettled
    ? 0.96
    : Math.min(0.96, 0.18 + (setupPlanningNoticeElapsedMs / SETUP_PLANNING_NOTICE_SETTLED_MS) * 0.78)
  const setupPlanningNoticeLiveIndex =
    setupPlanningNoticeElapsedMs >= 19_000 ? 4 :
    setupPlanningNoticeElapsedMs >= 14_000 ? 3 :
    setupPlanningNoticeElapsedMs >= 9_000 ? 2 :
    setupPlanningNoticeElapsedMs >= 4_000 ? 1 : 0
  const setupPlanningNoticeStageLabel = locale === 'zh'
    ? [
        '已收到任务，正在理解目标和边界。',
        '正在整理材料、约束和已有上下文。',
        '正在生成研究分析设计计划。',
      ][setupPlanningNoticePhaseIndex]
    : [
        'Task received. Understanding the goal and boundaries.',
        'Organizing materials, constraints, and current context.',
        'Drafting the research analysis and design plan.',
      ][setupPlanningNoticePhaseIndex]
  const setupPlanningNoticeCards = locale === 'zh'
    ? [
        {
          title: '任务定义',
          body: '明确目标、成功指标和最终交付物。',
          activeBody: '正在识别你真正想完成的研究目标。',
        },
        {
          title: '材料与资源',
          body: '检查论文、代码、数据、附件和可用算力。',
          activeBody: '正在整理已有材料和运行边界。',
        },
        {
          title: '全自动适配',
          body: '判断是否适合自主推进，或需要先协作确认。',
          activeBody: '正在评估任务能否在电脑内闭环完成。',
        },
        {
          title: '启动计划',
          body: '组织 baseline、优化、分析和风险确认步骤。',
          activeBody: '正在生成可审阅的启动规划。',
        },
      ]
    : [
        {
          title: 'Task definition',
          body: 'Clarifying the goal, success metrics, and final deliverables.',
          activeBody: 'Identifying the real research objective.',
        },
        {
          title: 'Materials & resources',
          body: 'Checking papers, code, data, attachments, and compute.',
          activeBody: 'Organizing available materials and runtime boundaries.',
        },
        {
          title: 'Autonomy fit',
          body: 'Deciding whether autonomous work is safe or confirmation is needed.',
          activeBody: 'Evaluating whether the task can run in a closed computer-side loop.',
        },
        {
          title: 'Launch plan',
          body: 'Structuring baseline, optimization, analysis, and risk gates.',
          activeBody: 'Drafting a reviewable launch plan.',
        },
      ]
  const setupPlanningNoticeLiveLines = locale === 'zh'
    ? [
        '正在识别研究目标、成功标准和最终交付物…',
        '正在整理已有材料、附件和参考来源…',
        '正在确认算力、网络、凭据和隐私边界…',
        '正在判断是否适合全自动模式…',
        '正在生成可审阅的启动规划…',
      ]
    : [
        'Identifying the research goal, success criteria, and deliverables…',
        'Organizing existing materials, attachments, and references…',
        'Checking compute, network, credentials, and privacy boundaries…',
        'Deciding whether autonomous mode is a good fit…',
        'Drafting a reviewable launch plan…',
      ]
  const setupPlanningNoticeVisibleSectionCount = Math.min(setupPlanningNoticeCards.length, setupPlanningNoticeCardRevealCount)
  const setupPlanningNoticeLiveLine = setupPlanningNoticeLiveLines[Math.min(setupPlanningNoticeLiveIndex, setupPlanningNoticeLiveLines.length - 1)]

  const closeSetupPlanningNotice = useCallback(() => {
    if (!setupPlanningNoticeOpen || setupPlanningNoticeClosing) return
    setSetupPlanningNoticeClosing(true)
    window.setTimeout(() => {
      setSetupPlanningNoticeOpen(false)
      setSetupPlanningNoticeClosing(false)
      setSetupPlanningNoticeDismissed(true)
      setSetupPlanningNoticeElapsedMs(0)
      setupPlanningNoticeStartedAtRef.current = null
      setRightPaneMode('assistant')
    }, 1800)
  }, [setupPlanningNoticeClosing, setupPlanningNoticeOpen])

  const startSetupPlanningNotice = useCallback(() => {
    setSetupPlanningNoticeDismissed(false)
    setSetupPlanningNoticeClosing(false)
    setSetupPlanningNoticeElapsedMs(0)
    setupPlanningNoticeStartedAtRef.current = Date.now()
    setSetupPlanningNoticeOpen(true)
  }, [])

  useEffect(() => {
    if (!setupQuestStillRunning || planningPreviewVisible) return
    if (setupPlanningNoticeDismissed) return
    if (setupPlanningNoticeOpen) return
    setSetupPlanningNoticeOpen(true)
    setSetupPlanningNoticeClosing(false)
    if (setupPlanningNoticeStartedAtRef.current == null) {
      setupPlanningNoticeStartedAtRef.current = Date.now()
    }
  }, [planningPreviewVisible, setupPlanningNoticeDismissed, setupPlanningNoticeOpen, setupQuestStillRunning])

  useEffect(() => {
    if (!setupPlanningNoticeOpen || setupPlanningNoticeClosing) return
    if (setupPlanningNoticeStartedAtRef.current == null) {
      setupPlanningNoticeStartedAtRef.current = Date.now()
    }
    const tick = () => {
      const startedAt = setupPlanningNoticeStartedAtRef.current ?? Date.now()
      const nextElapsed = Math.max(0, Math.min(Date.now() - startedAt, SETUP_PLANNING_NOTICE_TOTAL_MS))
      setSetupPlanningNoticeElapsedMs(nextElapsed)
      if (nextElapsed >= SETUP_PLANNING_NOTICE_TOTAL_MS) {
        closeSetupPlanningNotice()
      }
    }
    tick()
    const timer = window.setInterval(tick, 250)
    return () => window.clearInterval(timer)
  }, [closeSetupPlanningNotice, setupPlanningNoticeClosing, setupPlanningNoticeOpen])

  useEffect(() => {
    if (!durableSetupHasPlanningContent) return
    setupPlanningPollStartedAtRef.current = null
    closeSetupPlanningNotice()
  }, [closeSetupPlanningNotice, durableSetupHasPlanningContent])

  useEffect(() => {
    if (!open || !setupQuestId) {
      setupPlanningPollStartedAtRef.current = null
      return
    }
    if (durableSetupHasPlanningContent) {
      setupPlanningPollStartedAtRef.current = null
      return
    }
    if (setupPlanningPollStartedAtRef.current == null) {
      setupPlanningPollStartedAtRef.current = Date.now()
    }
    let cancelled = false
    const tick = () => {
      if (cancelled) return
      const startedAt = setupPlanningPollStartedAtRef.current ?? Date.now()
      if (Date.now() - startedAt > 90_000) {
        return
      }
      void setupWorkspace.refresh(false).catch(() => {})
    }
    const initialTimer = window.setTimeout(tick, 1200)
    const interval = window.setInterval(tick, 2000)
    return () => {
      cancelled = true
      window.clearTimeout(initialTimer)
      window.clearInterval(interval)
    }
  }, [durableSetupHasPlanningContent, open, setupQuestId, setupWorkspace.refresh])

  const benchAutoAssistWaitingForPatch = Boolean(
    setupPacket && onRequestSetupAgent && setupQuestCreating
  )

  useEffect(() => {
    if (!setupQuestId) return
    setEntryMode('form')
    setRightPaneMode('assistant')
  }, [setupQuestId])

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

  const queueLocalLaunchAttachments = useCallback((files: File[]) => {
    if (!files.length) return
    setLocalLaunchAttachments((current) => {
      const availableSlots = Math.max(0, START_RESEARCH_MAX_ATTACHMENTS - current.length)
      const nextFiles = files.slice(0, availableSlots)
      const nextDrafts: QuestMessageAttachmentDraft[] = []
      for (const file of nextFiles) {
        if (file.size > START_RESEARCH_MAX_ATTACHMENT_SIZE_BYTES) {
          continue
        }
        nextDrafts.push({
          draftId: makeLocalAttachmentDraftId(),
          name: file.name,
          contentType: file.type || undefined,
          sizeBytes: file.size,
          status: 'success',
          progress: 100,
          kind: isImageAttachmentMime(file.type) ? 'image' : 'path',
          previewUrl: isImageAttachmentMime(file.type) ? URL.createObjectURL(file) : null,
          file,
        })
      }
      return [...current, ...nextDrafts]
    })
  }, [])

  const removeLocalLaunchAttachment = useCallback((draftId: string) => {
    setLocalLaunchAttachments((current) => {
      const target = current.find((item) => item.draftId === draftId)
      if (target?.previewUrl?.startsWith('blob:')) {
        URL.revokeObjectURL(target.previewUrl)
      }
      return current.filter((item) => item.draftId !== draftId)
    })
  }, [])

  const clearLocalLaunchAttachments = useCallback(() => {
    setLocalLaunchAttachments((current) => {
      current.forEach((item) => {
        if (item.previewUrl?.startsWith('blob:')) {
          URL.revokeObjectURL(item.previewUrl)
        }
      })
      return []
    })
  }, [])

  const applyFormPatch = useCallback((patch: Partial<StartResearchTemplate>) => {
    setForm((current) => {
      const next = { ...current, ...patch }
      saveStartResearchDraft(next)
      return next
    })
    setAgentManagedValues((current) => ({ ...current, ...patch }))
  }, [])

  const applyAgentPatch = useCallback(
    (patch: Partial<StartResearchTemplate>) => {
      const currentManaged = latestAgentManagedValuesRef.current
      setForm((current) => {
        const next = { ...current }
        const nextManaged = { ...currentManaged }
        let changed = false
        for (const key of Object.keys(patch) as Array<keyof StartResearchTemplate>) {
          const proposed = patch[key]
          const currentValue = current[key]
          const previousManaged = nextManaged[key]
          const canApply =
            previousManaged === undefined ||
            currentValue === previousManaged ||
            currentValue === '' ||
            currentValue === null ||
            currentValue === undefined
          if (!canApply) {
            continue
          }
          if (currentValue === proposed && previousManaged === proposed) {
            continue
          }
          ;(next as Record<string, unknown>)[key] = proposed as unknown
          ;(nextManaged as Record<string, unknown>)[key as string] = proposed as unknown
          changed = true
        }
        if (!changed) {
          return current
        }
        saveStartResearchDraft(next)
        latestAgentManagedValuesRef.current = nextManaged
        setAgentManagedValues(nextManaged)
        return next
      })
      if (setupPacket && Object.keys(patch).length > 0) {
        setBenchAutoAssistReady(true)
      }
    },
    [setupPacket]
  )

  const benchAutoAssistMessage = useMemo(
    () => (setupPacket ? buildBenchstoreAutoAssistMessage(setupPacket, locale) : ''),
    [locale, setupPacket]
  )

  useEffect(() => {
    if (!open || !setupPacket || !onRequestSetupAgent) return
    if (setupQuestId || setupQuestCreating) return
    const triggerKey = [
      setupPacket.entry_id,
      setupPacket.benchmark_local_path || '',
      setupPacket.latex_markdown_path || '',
    ].join('::')
    if (autoBenchAssistStartedRef.current === triggerKey) return
    autoBenchAssistStartedRef.current = triggerKey
    void onRequestSetupAgent({
      message: benchAutoAssistMessage,
      form: latestFormRef.current,
      setupPacket,
    }).catch(() => {
      autoBenchAssistStartedRef.current = null
    })
  }, [
    benchAutoAssistMessage,
    onRequestSetupAgent,
    open,
    setupPacket,
    setupQuestCreating,
    setupQuestId,
  ])

  useEffect(() => {
    if (!setupQuestId) return
    const handleStartSetupPatch = (event: Event) => {
      const detail = (event as CustomEvent<{
        patch?: Partial<StartResearchTemplate>
        session_patch?: Record<string, unknown>
      }>).detail
      const patch =
        detail?.patch && typeof detail.patch === 'object' && !Array.isArray(detail.patch)
          ? (detail.patch as Partial<StartResearchTemplate>)
          : null
      const sessionPatch = normalizeStartSetupSessionPatch(detail?.session_patch)
      if (patch && Object.keys(patch).length > 0) {
        applyAgentPatch(patch)
      }
      if (sessionPatch) {
        setLocalSetupSessionPatch((current) => ({ ...(current || {}), ...sessionPatch }))
      }
      if (patch || sessionPatch) {
        setBenchAutoAssistReady(true)
      }
    }
    window.addEventListener('ds:start-setup:patch', handleStartSetupPatch as EventListener)
    return () =>
      window.removeEventListener('ds:start-setup:patch', handleStartSetupPatch as EventListener)
  }, [applyAgentPatch, setupQuestId])

  useEffect(() => {
    if (!setupPacket || !onRequestSetupAgent) return
    if (setupQuestCreating) {
      setBenchAutoAssistReady(false)
      return
    }
    if (!setupQuestId) {
      setBenchAutoAssistReady(false)
      return
    }
    if (durableSetupSuggestedForm && Object.keys(durableSetupSuggestedForm).length > 0) {
      setBenchAutoAssistReady(true)
      return
    }
    if (!setupQuestStillRunning) {
      setBenchAutoAssistReady(true)
      return
    }
    setBenchAutoAssistReady(false)
  }, [
    durableSetupSuggestedForm,
    onRequestSetupAgent,
    setupPacket,
    setupQuestCreating,
    setupQuestId,
    setupQuestStillRunning,
  ])

  const applyStandardProfile = useCallback((profile: StandardProfile) => {
    setForm((current) => {
      const next: StartResearchTemplate = {
        ...current,
        standard_profile: profile,
        need_research_paper: profile === 'optimization_task' ? false : true,
      }
      saveStartResearchDraft(next)
      return next
    })
  }, [])

  const applyLaunchMode = useCallback((mode: LaunchMode) => {
    setForm((current) => {
      const next: StartResearchTemplate = {
        ...current,
        launch_mode: mode,
        need_research_paper:
          mode === 'standard'
            ? current.standard_profile !== 'optimization_task'
            : current.need_research_paper,
      }
      saveStartResearchDraft(next)
      return next
    })
  }, [])

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

  const effectiveSelectedConnectorBindings = useMemo(
    () => resolveStartResearchConnectorBindings(connectorChoices, selectedConnectorBindings),
    [connectorChoices, selectedConnectorBindings]
  )

  const selectedConnectorTargets = useMemo(
    () =>
      connectorChoices.flatMap((item) => {
        const selectedConversationId = effectiveSelectedConnectorBindings[item.name] || null
        if (!selectedConversationId) return []
        const target = item.targets.find((candidate) => candidate.conversationId === selectedConversationId)
        if (!target) return []
        return [{ connector: item.label, target }]
      }),
    [connectorChoices, effectiveSelectedConnectorBindings]
  )
  const selectedConnectorTarget = selectedConnectorTargets[0] || null

  const templateOptions = useMemo(
    () => [...referenceTemplates, ...templates],
    [referenceTemplates, templates]
  )

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

  const compiledPromptPreview = useMemo(
    () =>
      compileStartResearchPrompt(form, {
        attachments: launchMaterialAttachments.map((item) => ({
          label: item.label,
          location: item.location || item.questRelativePath || item.path || null,
          contentType: item.contentType || null,
          source: item.source,
        })),
      }),
    [form, launchMaterialAttachments]
  )

  useEffect(() => {
    if (!open || manualOverride) {
      return
    }
    setPromptDraft(compiledPromptPreview)
  }, [compiledPromptPreview, manualOverride, open])

  const finalPrompt = compiledPromptPreview.trim()
  const promptRequired = open && !compiledPromptPreview.trim()
  const goalRequired = open && !manualOverride && !form.goal.trim()
  const benchAutoAssistLocked = Boolean(
    setupPacket &&
      onRequestSetupAgent &&
      !benchAutoAssistReady &&
      (benchAutoAssistWaitingForPatch || setupQuestStillRunning)
  )
  const createDisabledReason = loading
    ? 'loading'
    : benchAutoAssistLocked
      ? 'setup-agent-running'
      : 'none'

  const focusCreateValidationTarget = useCallback(
    (target: 'title' | 'goal') => {
      const node = target === 'title' ? titleInputRef.current : goalTextareaRef.current
      if (!node) return
      node.scrollIntoView({ behavior: 'smooth', block: 'center' })
      window.setTimeout(() => {
        node.focus()
      }, 120)
    },
    []
  )

  const validateBeforeCreate = useCallback((candidateForm: StartResearchTemplate = form, candidatePrompt: string = finalPrompt) => {
    const titleTrimmed = String(candidateForm.title || '').trim()
    const goalTrimmed = String(candidateForm.goal || '').trim()
    if (!titleTrimmed) {
      setValidationMessage(locale === 'zh' ? '请先填写课题标题。' : 'Please fill in the project title first.')
      setValidationTarget('title')
      setValidationDialogOpen(true)
      focusCreateValidationTarget('title')
      return false
    }
    if (!manualOverride && !goalTrimmed) {
      setValidationMessage(t.goalRequired)
      setValidationTarget('goal')
      setValidationDialogOpen(true)
      focusCreateValidationTarget('goal')
      return false
    }
    if (!candidatePrompt.trim()) {
      setValidationMessage(t.promptRequired)
      setValidationTarget('goal')
      setValidationDialogOpen(true)
      focusCreateValidationTarget('goal')
      return false
    }
    return true
  }, [finalPrompt, focusCreateValidationTarget, form, locale, manualOverride, t.goalRequired, t.promptRequired])

  const handleValidationDialogChange = useCallback(
    (nextOpen: boolean) => {
      setValidationDialogOpen(nextOpen)
      if (!nextOpen && validationTarget) {
        window.setTimeout(() => {
          focusCreateValidationTarget(validationTarget)
        }, 120)
      }
    },
    [focusCreateValidationTarget, validationTarget]
  )

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
      baseline_source_mode: next.baseline_source_mode,
      execution_start_mode: next.execution_start_mode,
      baseline_acceptance_target: next.baseline_acceptance_target,
      baseline_urls: next.baseline_urls,
      paper_urls: next.paper_urls,
      runtime_constraints: next.runtime_constraints,
      objectives: next.objectives,
      need_research_paper: next.need_research_paper,
      research_intensity: next.research_intensity,
      decision_policy: next.decision_policy,
      launch_mode: next.launch_mode,
      standard_profile: next.standard_profile,
      custom_profile: next.custom_profile,
      review_followup_policy: next.review_followup_policy,
      baseline_execution_policy: next.baseline_execution_policy,
      manuscript_edit_mode: next.manuscript_edit_mode,
      entry_state_summary: next.entry_state_summary,
      review_summary: next.review_summary,
      review_materials: next.review_materials,
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

  const handleLaunchTutorialDemo = useCallback(() => {
    onClose()
    resetDemoRuntime('demo-memory')
    navigate('/projects/demo-memory')
  }, [navigate, onClose])

  const handleSwitchToCopilot = useCallback(async () => {
    const suggestedTitle = String(durableSetupSuggestedForm?.title || '').trim()
    const suggestedGoal = String(durableSetupSuggestedForm?.goal || '').trim()
    const planMarkdown = String(durableSetupSession.previewPlan?.markdown || '').trim()
    const message = [
      intakeMessage.trim() || suggestedGoal || form.goal.trim() || compiledPromptPreview.trim(),
      planMarkdown ? `\n\nSetupAgent launch plan:\n${planMarkdown}` : '',
    ].filter(Boolean).join('')
    await onSwitchToCopilot?.({
      title: suggestedTitle || form.title.trim() || intakeMessage.trim() || form.goal.trim() || '',
      message,
      setupQuestId,
      setupAttachments: setupLaunchAttachments,
      localAttachments: localLaunchAttachments,
    })
  }, [
    compiledPromptPreview,
    durableSetupSession.previewPlan,
    durableSetupSuggestedForm,
    form.goal,
    form.title,
    intakeMessage,
    localLaunchAttachments,
    onSwitchToCopilot,
    setupLaunchAttachments,
    setupQuestId,
  ])

  const handleReviewSuggestedForm = useCallback(() => {
    if (durableSetupSuggestedForm) {
      applyAgentPatch(durableSetupSuggestedForm)
    }
    setEntryMode('form')
    setRightPaneMode('preview')
  }, [applyAgentPatch, durableSetupSuggestedForm])

  const handleStartSetupFromIntake = useCallback(async () => {
    if (!onRequestSetupAgent) {
      setEntryMode('form')
      return
    }
    const nextMessage = intakeMessage.trim()
    if (!nextMessage && localLaunchAttachments.length === 0) {
      setEntryMode('form')
      return
    }
    setEntryMode('form')
    setRightPaneMode('assistant')
    startSetupPlanningNotice()
    void onRequestSetupAgent({
      message: nextMessage,
      form,
      setupPacket,
      attachments: localLaunchAttachments,
    })
  }, [
    form,
    intakeMessage,
    localLaunchAttachments,
    onRequestSetupAgent,
    setupPacket,
    startSetupPlanningNotice,
  ])

  const handleCreate = async (formOverride?: StartResearchTemplate) => {
    if (onboardingStatus === 'running') {
      handleLaunchTutorialDemo()
      return
    }
    if (benchAutoAssistLocked) {
      return
    }
    const workingForm = formOverride || form
    const launchPrompt = compileStartResearchPrompt(workingForm, {
      attachments: launchMaterialAttachments.map((item) => ({
        label: item.label,
        location: item.location || item.questRelativePath || item.path || null,
        contentType: item.contentType || null,
        source: item.source,
      })),
    }).trim()
    if (!validateBeforeCreate(workingForm, launchPrompt)) {
      return
    }
    const saved = saveStartResearchTemplate(workingForm)
    const baselineId = saved.baseline_id.trim()
    const baselineVariantId = saved.baseline_variant_id.trim()
    const requestedBaselineRef = baselineId
      ? {
          baseline_id: baselineId,
          variant_id: baselineVariantId || null,
        }
      : null
    const derivedFields = resolveStartResearchContractFields(saved)
    const effectiveReviewFollowupPolicy =
      saved.custom_profile === 'review_audit' ? saved.review_followup_policy : 'audit_only'
    const effectiveManuscriptEditMode =
      saved.custom_profile === 'review_audit' || saved.custom_profile === 'revision_rebuttal'
        ? saved.manuscript_edit_mode
        : 'none'
    const effectiveReviewSummary =
      saved.custom_profile === 'review_audit' || saved.custom_profile === 'revision_rebuttal'
        ? saved.review_summary
        : ''
    const effectiveReviewMaterials =
      saved.custom_profile === 'review_audit' || saved.custom_profile === 'revision_rebuttal'
        ? sanitizeLines(saved.review_materials)
        : []
    const timeBudget = Number(derivedFields.time_budget_hours)
    const requestedConnectorBindings = connectorChoices
      .map((item) => ({
        connector: item.name,
        conversation_id: effectiveSelectedConnectorBindings[item.name] || null,
      }))
      .filter((item) => Boolean(item.conversation_id))
    const startupContract = {
      schema_version: 4,
      workspace_mode: 'autonomous',
      user_language: saved.user_language,
      need_research_paper: saved.need_research_paper,
      research_intensity: saved.research_intensity,
      decision_policy: saved.decision_policy,
      launch_mode: saved.launch_mode,
      standard_profile: saved.standard_profile,
      custom_profile: saved.custom_profile,
      review_followup_policy: effectiveReviewFollowupPolicy,
      baseline_execution_policy: saved.baseline_execution_policy,
      baseline_source_mode: saved.baseline_source_mode,
      execution_start_mode: saved.execution_start_mode,
      baseline_acceptance_target: saved.baseline_acceptance_target,
      manuscript_edit_mode: effectiveManuscriptEditMode,
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
      review_summary: effectiveReviewSummary,
      review_materials: effectiveReviewMaterials,
      custom_brief: saved.custom_brief,
      launch_form_source: setupQuestId ? 'setup_agent' : 'manual_form',
      launch_form_recorded_at: new Date().toISOString(),
      launch_setup_quest_id: setupQuestId || null,
      launch_form: buildStartResearchLaunchSnapshot(saved),
      launch_markdown: launchPrompt,
      project_display: {
        template: 'experiment',
        accent_color: 'sage',
      },
    }
    await onCreate({
      title: saved.title,
      goal: launchPrompt,
      quest_id: questIdManualOverride ? saved.quest_id || undefined : undefined,
      requested_connector_bindings: requestedConnectorBindings,
      requested_baseline_ref: requestedBaselineRef,
      startup_contract: startupContract,
      launch_materials: {
        setup_quest_id: setupQuestId || undefined,
        setup_attachments: setupLaunchAttachments,
        local_attachments: localLaunchAttachments,
      },
    })
  }

  const handleAcceptAutonomousPlan = () => {
    const suggested = durableSetupSuggestedForm ? { ...latestFormRef.current, ...durableSetupSuggestedForm } : latestFormRef.current
    if (durableSetupSuggestedForm) {
      applyAgentPatch(durableSetupSuggestedForm)
    }
    void handleCreate(suggested)
  }

  return (
    <>
      <OverlayDialog
        open={open}
        title={t.title}
        description={t.body}
        onClose={onClose}
        className={LAUNCH_DIALOG_SHELL_CLASS}
        hideHeader
      >
        {entryMode === 'intake' && !setupPacket ? (
          <AutonomousSetupIntakeSurface
            locale={locale}
            assistantLabel={`${runnerLabel(activeRunnerName)} · SetupAgent`}
            value={intakeMessage}
            onValueChange={setIntakeMessage}
            attachments={localLaunchAttachments}
            onQueueFiles={queueLocalLaunchAttachments}
            onRemoveAttachment={removeLocalLaunchAttachment}
            onSubmit={handleStartSetupFromIntake}
            submitting={setupQuestCreating}
            error={error}
            onSwitchToForm={() => setEntryMode('form')}
            onSwitchToCopilot={() => void handleSwitchToCopilot()}
            onOpenBenchStore={onOpenBenchStore}
            onClose={onClose}
          />
        ) : (
        <div
          className="feed-scrollbar modal-scrollbar relative flex h-full min-h-0 max-w-full flex-col gap-3 overflow-y-auto overflow-x-hidden p-3 sm:gap-4 sm:p-4 lg:grid lg:grid-cols-[minmax(0,1.08fr)_minmax(0,0.92fr)] lg:grid-rows-[minmax(0,1fr)] lg:items-stretch lg:overflow-hidden lg:p-5"
          data-onboarding-id="start-research-dialog"
        >
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="sticky right-0 top-0 z-40 ml-auto h-9 w-9 shrink-0 rounded-full bg-white/80 shadow-sm backdrop-blur lg:hidden"
          onClick={onClose}
          aria-label={locale === 'zh' ? '关闭' : 'Close'}
        >
          <X className="h-4 w-4" />
        </Button>
        <div
          className={cn(
            'flex min-w-0 max-w-full flex-none flex-col overflow-visible lg:h-full lg:min-h-0 lg:flex-auto lg:overflow-hidden lg:rounded-[28px] lg:border lg:border-black/[0.06] lg:bg-[rgba(255,250,245,0.76)] lg:shadow-[0_22px_72px_-54px_rgba(15,23,42,0.3)] lg:backdrop-blur-xl'
          )}
        >
          <div className="hidden shrink-0 border-b border-[rgba(45,42,38,0.08)] px-4 py-3 lg:block dark:border-[rgba(45,42,38,0.08)]">
            <div className="flex flex-wrap items-center justify-end gap-2 lg:justify-between">
              <div className="flex flex-wrap items-center gap-2" data-onboarding-id="start-research-preview-mode-tabs">
                <Button
                  type="button"
                  variant={rightPaneMode === 'assistant' ? 'secondary' : 'ghost'}
                  className="rounded-full"
                  onClick={() => {
                    setRightPaneMode('assistant')
                  }}
                  data-onboarding-id="start-research-toggle-assistant"
                >
                  {t.setupAgentToggle}
                </Button>
                {onSwitchToCopilot ? (
                  <Button
                    type="button"
                    variant="outline"
                    className="rounded-full"
                    onClick={() => void handleSwitchToCopilot()}
                  >
                    <ArrowUpRight className="mr-1.5 h-4 w-4" />
                    {locale === 'zh' ? '协作模式' : 'Copilot'}
                  </Button>
                ) : null}
                <Button
                  type="button"
                  variant={rightPaneMode === 'preview' ? 'secondary' : 'ghost'}
                  className="rounded-full"
                  onClick={() => setRightPaneMode('preview')}
                  data-onboarding-id="start-research-toggle-preview"
                >
                  {t.previewPanel}
                </Button>
              </div>
              <Button type="button" variant="ghost" size="icon" className="rounded-full" onClick={onClose} aria-label={locale === 'zh' ? '关闭' : 'Close'}>
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>

          <div className="min-w-0 max-w-full px-0 py-1 sm:px-0 sm:py-1 lg:feed-scrollbar lg:modal-scrollbar lg:min-h-0 lg:flex-1 lg:overflow-y-scroll lg:overscroll-contain lg:p-4">
            <div className="flex min-h-full min-w-0 max-w-full flex-col gap-4">
              {manualOverride ? (
                <div className="rounded-lg border border-[#c4a066]/50 bg-[#c4a066]/10 px-3 py-2 text-xs text-[rgba(56,49,35,0.92)]">
                  <div className="flex items-center gap-2 font-semibold">
                    <Lock className="h-3.5 w-3.5" />
                    {t.manualTitle}
                  </div>
                  <div className="mt-1">{t.manualBody}</div>
                </div>
              ) : null}

              <SectionCard title={t.basics}>
                <InlineField label={t.titleLabel} help={t.titleHelp} dataOnboardingId="start-research-title">
                  <Input
                    ref={titleInputRef}
                    value={form.title}
                    onChange={(event) => setField('title', event.target.value)}
                    placeholder={t.titlePlaceholder}
                    className={`rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs ${fieldToneClassName} dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78`}
                    disabled={manualOverride}
                  />
                </InlineField>

                {showAdvanced ? (
                  <InlineField label={t.repoLabel} help={t.repoHelp}>
                    <Input
                      value={displayedQuestId}
                      onChange={(event) => handleQuestIdChange(event.target.value)}
                      placeholder={suggestedQuestIdLoading ? t.repoLoading : suggestedQuestId || t.repoPlaceholder}
                      className={`rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs ${fieldToneClassName} dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78`}
                      disabled={manualOverride}
                    />
                  </InlineField>
                ) : null}

                <InlineField label={t.goalLabel} help={t.goalHelp} dataOnboardingId="start-research-goal">
                  <Textarea
                    ref={goalTextareaRef}
                    value={form.goal}
                    onChange={(event) => setField('goal', event.target.value)}
                    placeholder={t.goalPlaceholder}
                    className={`min-h-[150px] rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs leading-5 ${fieldToneClassName} dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78`}
                    disabled={manualOverride}
                  />
                </InlineField>
                {goalRequired ? <div className="text-xs text-[#9a1b1b]">{t.goalRequired}</div> : null}
              </SectionCard>

              <SectionCard title={t.references} dataOnboardingId="start-research-references">
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
                <InlineField label={t.baselineUrls} help={t.baselineUrlsHelp}>
                  <Textarea
                    value={form.baseline_urls}
                    onChange={(event) => setField('baseline_urls', event.target.value)}
                    placeholder={t.baselineUrlsPlaceholder}
                    className={`min-h-[92px] rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs leading-5 ${fieldToneClassName} dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78`}
                    disabled={manualOverride || Boolean(form.baseline_id?.trim())}
                  />
                </InlineField>
                <InlineField label={t.paperUrls} help={t.paperUrlsHelp}>
                  <Textarea
                    value={form.paper_urls}
                    onChange={(event) => setField('paper_urls', event.target.value)}
                    placeholder={t.paperUrlsPlaceholder}
                    className={`min-h-[92px] rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs leading-5 ${fieldToneClassName} dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78`}
                    disabled={manualOverride}
                  />
                </InlineField>
                <div
                  className="rounded-[18px] border border-[rgba(45,42,38,0.08)] bg-[linear-gradient(145deg,rgba(253,247,241,0.94),rgba(239,229,220,0.84)_42%,rgba(226,235,239,0.82))] px-4 py-4 shadow-[0_16px_44px_-34px_rgba(44,39,34,0.24)]"
                  data-onboarding-id="start-research-deepxiv"
                >
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-[rgba(38,36,33,0.95)] dark:text-[rgba(38,36,33,0.95)]">{deepxivT.title}</div>
                      <div className="mt-2 text-[11px] leading-6 text-[rgba(75,73,69,0.78)] dark:text-[rgba(75,73,69,0.78)]">
                        {deepxivT.body}
                      </div>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <Button
                        type="button"
                        variant="secondary"
                        className="rounded-full"
                        onClick={() => setDeepxivSetupOpen(true)}
                        data-onboarding-id="start-research-deepxiv-setup"
                      >
                        {deepxivT.openSetup}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        className="rounded-full"
                        onClick={() => navigate('/settings/deepxiv')}
                      >
                        {deepxivT.openSettings}
                      </Button>
                    </div>
                  </div>
                </div>
                {showAdvanced ? (
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
                ) : null}
              </SectionCard>

              <LaunchMaterialsCard
                locale={locale}
                setupAttachments={setupLaunchAttachments}
                localAttachments={localLaunchAttachments}
                onQueueFiles={queueLocalLaunchAttachments}
                onRemoveAttachment={removeLocalLaunchAttachment}
              />

              <>
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
                    <div className="mt-1 text-sm font-semibold text-[rgba(38,36,33,0.95)] dark:text-[rgba(38,36,33,0.95)]">{`${runnerLabel(activeRunnerName)} / ${locale === 'zh' ? '本地 daemon' : 'local daemon'}`}</div>
                  </div>
                </div>
                <div data-onboarding-id="start-research-connector">
                  <ConnectorChoiceField
                  label={t.connectorDeliveryLabel}
                  help={t.connectorDeliveryHelp}
                  hint={t.connectorDeliveryHint}
                  items={connectorChoices}
                  value={effectiveSelectedConnectorBindings}
                  loading={connectorsLoading}
                  error={connectorsError}
                  localOnlyLabel={t.connectorSelectPlaceholder}
                  onChange={(connectorName, next) =>
                    setSelectedConnectorBindings(() => {
                      const normalized: Record<string, string | null> = {}
                      for (const item of connectorChoices) {
                        normalized[item.name] = null
                      }
                      if (next) {
                        normalized[connectorName] = next
                      }
                      return normalized
                    })
                  }
                  />
                </div>
                  </SectionCard>

                  <SectionCard title={t.policy} dataOnboardingId="start-research-contract">
                <ChoiceField
                  label={t.launchModeLabel}
                  help={t.launchModeHelp}
                  hint={t.launchModeHelp}
                  value={form.launch_mode}
                  items={launchModeItems}
                  onChange={(value) => applyLaunchMode(value as LaunchMode)}
                  disabled={manualOverride}
                />
                {form.launch_mode === 'custom' ? (
                  <>
                    <ChoiceField
                      label={t.customProfileLabel}
                      help={t.customProfileHelp}
                      hint={t.customProfileHelp}
                      value={form.custom_profile}
                      items={customProfileItems}
                      onChange={(value) => setField('custom_profile', value as CustomProfile)}
                      disabled={manualOverride}
                    />
                    <ChoiceField
                      label={t.baselineExecutionPolicyLabel}
                      help={t.baselineExecutionPolicyHelp}
                      hint={t.baselineExecutionPolicyHelp}
                      value={form.baseline_execution_policy}
                      items={baselineExecutionPolicyItems}
                      onChange={(value) => setField('baseline_execution_policy', value as BaselineExecutionPolicy)}
                      disabled={manualOverride}
                    />
                    {form.custom_profile === 'review_audit' ? (
                      <ChoiceField
                        label={t.reviewFollowupPolicyLabel}
                        help={t.reviewFollowupPolicyHelp}
                        hint={t.reviewFollowupPolicyHelp}
                        value={form.review_followup_policy}
                        items={reviewFollowupPolicyItems}
                        onChange={(value) => setField('review_followup_policy', value as ReviewFollowupPolicy)}
                        disabled={manualOverride}
                      />
                    ) : null}
                    {form.custom_profile === 'revision_rebuttal' ||
                    (form.custom_profile === 'review_audit' && form.review_followup_policy !== 'audit_only') ? (
                      <>
                        <ChoiceField
                          label={t.manuscriptEditModeLabel}
                          help={t.manuscriptEditModeHelp}
                          hint={t.manuscriptEditModeHelp}
                          value={form.manuscript_edit_mode}
                          items={manuscriptEditModeItems}
                          onChange={(value) => setField('manuscript_edit_mode', value as ManuscriptEditMode)}
                          disabled={manualOverride}
                        />
                        {form.manuscript_edit_mode === 'latex_required' ? (
                          <div className="rounded-lg border border-[rgba(126,77,42,0.22)] bg-[rgba(126,77,42,0.06)] px-3 py-2 text-[11px] leading-5 text-[rgba(86,82,77,0.88)] dark:border-[rgba(126,77,42,0.22)] dark:bg-[rgba(126,77,42,0.08)] dark:text-[rgba(86,82,77,0.88)]">
                            {t.manuscriptEditModeNote}
                          </div>
                        ) : null}
                      </>
                    ) : null}
                    <InlineField label={t.entryStateSummaryLabel} help={t.entryStateSummaryHelp}>
                      <Textarea
                        value={form.entry_state_summary}
                        onChange={(event) => setField('entry_state_summary', event.target.value)}
                        placeholder={t.entryStateSummaryPlaceholder}
                        className={`min-h-[92px] rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs leading-5 ${fieldToneClassName} dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78`}
                        disabled={manualOverride}
                      />
                    </InlineField>
                    {form.custom_profile === 'review_audit' || form.custom_profile === 'revision_rebuttal' ? (
                      <InlineField label={t.reviewSummaryLabel} help={t.reviewSummaryHelp}>
                        <Textarea
                          value={form.review_summary}
                          onChange={(event) => setField('review_summary', event.target.value)}
                          placeholder={t.reviewSummaryPlaceholder}
                          className={`min-h-[92px] rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs leading-5 ${fieldToneClassName} dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78`}
                          disabled={manualOverride}
                        />
                      </InlineField>
                    ) : null}
                    {form.custom_profile === 'review_audit' || form.custom_profile === 'revision_rebuttal' ? (
                      <InlineField label={t.reviewMaterialsLabel} help={t.reviewMaterialsHelp}>
                        <Textarea
                          value={form.review_materials}
                          onChange={(event) => setField('review_materials', event.target.value)}
                          placeholder={t.reviewMaterialsPlaceholder}
                          className={`min-h-[92px] rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs leading-5 ${fieldToneClassName} dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78`}
                          disabled={manualOverride}
                        />
                      </InlineField>
                    ) : null}
                    <InlineField label={t.customBriefLabel} help={t.customBriefHelp}>
                      <Textarea
                        value={form.custom_brief}
                        onChange={(event) => setField('custom_brief', event.target.value)}
                        placeholder={t.customBriefPlaceholder}
                        className={`min-h-[92px] rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs leading-5 ${fieldToneClassName} dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78`}
                        disabled={manualOverride}
                      />
                    </InlineField>
                  </>
                ) : (
                  <ChoiceField
                    label={t.standardProfileLabel}
                    help={t.standardProfileHelp}
                    hint={t.standardProfileHelp}
                    value={form.standard_profile}
                    items={standardProfileItems}
                    onChange={(value) => applyStandardProfile(value as StandardProfile)}
                    disabled={manualOverride}
                  />
                )}
                <ChoiceField
                  label={t.baselineSourceModeLabel}
                  help={t.baselineSourceModeHelp}
                  hint={t.baselineSourceModeHelp}
                  value={form.baseline_source_mode}
                  items={baselineSourceModeItems}
                  onChange={(value) => setField('baseline_source_mode', value as BaselineSourceMode)}
                  disabled={manualOverride}
                />
                <ChoiceField
                  label={t.executionStartModeLabel}
                  help={t.executionStartModeHelp}
                  hint={t.executionStartModeHelp}
                  value={form.execution_start_mode}
                  items={executionStartModeItems}
                  onChange={(value) => setField('execution_start_mode', value as ExecutionStartMode)}
                  disabled={manualOverride}
                />
                <ChoiceField
                  label={t.baselineAcceptanceTargetLabel}
                  help={t.baselineAcceptanceTargetHelp}
                  hint={t.baselineAcceptanceTargetHelp}
                  value={form.baseline_acceptance_target}
                  items={baselineAcceptanceTargetItems}
                  onChange={(value) => setField('baseline_acceptance_target', value as BaselineAcceptanceTarget)}
                  disabled={manualOverride}
                />
                <div className="rounded-[14px] border border-[rgba(45,42,38,0.08)] bg-[rgba(244,239,233,0.52)] px-3 py-3 text-[11px] leading-5 text-[rgba(86,82,77,0.82)] dark:border-[rgba(45,42,38,0.08)] dark:bg-[rgba(244,239,233,0.62)] dark:text-[rgba(86,82,77,0.82)]">
                  {locale === 'zh'
                    ? '上面这 3 个控制项只影响“Start Research 刚开始时如何处理 baseline”。它们不会把后续所有 stage 都变成必须先计划后执行。'
                    : 'These 3 controls only affect how Start Research enters baseline work. They do not force every later stage into plan-then-execute mode.'}
                </div>
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
                {form.launch_mode === 'custom' ? (
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
                ) : null}
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
                    className={`min-h-[92px] rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs leading-5 ${fieldToneClassName} dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78`}
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
                    className={`min-h-[120px] rounded-[10px] border-[rgba(45,42,38,0.09)] bg-white/75 text-xs leading-5 ${fieldToneClassName} dark:border-[rgba(45,42,38,0.09)] dark:bg-white/78`}
                    disabled={manualOverride}
                  />
                </InlineField>
                  </SectionCard>
              </>
            </div>
          </div>
        </div>

        <div
          data-onboarding-id="start-research-preview"
          className={cn(
            'flex min-w-0 flex-none flex-col overflow-visible p-0 sm:p-0 lg:h-full lg:min-h-0 lg:flex-auto lg:overflow-hidden lg:rounded-[28px] lg:bg-transparent lg:p-0'
          )}
        >
          <div className="hidden min-h-0 flex-1 lg:block">
            {rightPaneMode === 'assistant' ? (
              <div data-onboarding-id="start-research-assistant-surface" className="h-full min-h-0">
                {setupQuestId ? (
                  <SetupAgentQuestPanel
                    questId={setupQuestId}
                    locale={locale}
                    transformSubmitMessage={transformSetupAgentSubmitMessage}
                  />
                ) : (
                  <SetupAgentRail
                    locale={locale}
                    setupPacket={setupPacket}
                    assistantLabel={`${runnerLabel(activeRunnerName)} · SetupAgent`}
                    loading={setupQuestCreating}
                    error={error}
                    onStartAssist={async (message, attachments) => {
                      await onRequestSetupAgent?.({
                        message,
                        form,
                        setupPacket,
                        attachments,
                      })
                    }}
                  />
                )}
              </div>
            ) : (
              <div className="flex h-full min-h-0 flex-col rounded-[24px] border border-[rgba(45,42,38,0.08)] bg-[rgba(255,255,255,0.78)] shadow-[0_20px_56px_-42px_rgba(45,42,38,0.28)] backdrop-blur-xl" data-onboarding-id="start-research-preview-surface">
                <div className="shrink-0 border-b border-[rgba(45,42,38,0.08)] px-4 py-3">
                  <div className="text-sm font-semibold text-[rgba(38,36,33,0.95)]">{t.preview}</div>
                  <div className="mt-1 text-xs leading-5 text-[rgba(107,103,97,0.72)]">{t.previewBody}</div>
                </div>
                <div className="min-h-0 flex-1 p-4">
                  <Textarea
                    value={compiledPromptPreview}
                    readOnly
                    aria-label={t.preview}
                    containerClassName="flex h-full min-h-0"
                    className={`h-full min-h-full overflow-y-auto rounded-[18px] border-[rgba(45,42,38,0.08)] bg-white/70 text-xs leading-6 ${fieldToneClassName} dark:border-[rgba(45,42,38,0.08)] dark:bg-white/78`}
                  />
                </div>
              </div>
            )}
          </div>

          <div className="mt-3 flex shrink-0 flex-col gap-3 px-1 sm:flex-row sm:items-center sm:justify-between lg:px-0">
            <div className="flex flex-col gap-1">
              <div className="inline-flex items-center gap-2 text-[11px] text-[rgba(107,103,97,0.72)] dark:text-[rgba(107,103,97,0.72)]">
                <BookmarkPlus className="h-3.5 w-3.5" />
                <span>{templateOptions.length} template(s)</span>
              </div>
              {benchAutoAssistLocked ? (
                <div className="text-[11px] text-[rgba(107,103,97,0.8)] dark:text-[rgba(107,103,97,0.78)]">
                  {t.benchAutoAssistPending}
                </div>
              ) : null}
            </div>
            <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center sm:gap-3">
              {onBack ? (
                <Button
                  variant="outline"
                  onClick={onBack}
                  className="w-full sm:w-auto"
                >
                  <ArrowLeft className="h-4 w-4" />
                  {backLabel}
                </Button>
              ) : null}
              {manualOverride ? (
                <Button
                  variant="secondary"
                  disabled={loading}
                  onClick={handleRestore}
                  className="w-full sm:w-auto"
                >
                  <RotateCcw className="h-4 w-4" />
                  {t.restore}
                </Button>
              ) : null}
              <Button variant="ghost" onClick={onClose} className="w-full sm:w-auto">
                {t.cancel}
              </Button>
              <Button
                onClick={() => void handleCreate()}
                disabled={loading || benchAutoAssistLocked}
                className={cn(
                  'w-full sm:w-auto',
                  benchAutoAssistLocked &&
                    'bg-[rgba(45,42,38,0.14)] text-[rgba(107,103,97,0.78)] shadow-none'
                )}
                data-onboarding-id="start-research-create"
                data-disabled-reason={createDisabledReason}
              >
                <Sparkles className="h-4 w-4" />
                {loading ? '…' : t.create}
              </Button>
            </div>
          </div>
        </div>
        {planningReviewOpen ? (
          <StartSetupPlanningReviewDialog
            open={planningReviewOpen}
            locale={locale}
            session={visibleSetupSession}
            hasSuggestedForm={Boolean(durableSetupSuggestedForm && Object.keys(durableSetupSuggestedForm).length > 0)}
            loading={Boolean(loading)}
            onClose={closePlanningReview}
            onAcceptAutonomous={handleAcceptAutonomousPlan}
            onReviewForm={() => {
              handleReviewSuggestedForm()
              closePlanningReview()
            }}
            onSwitchToCopilot={onSwitchToCopilot ? () => void handleSwitchToCopilot() : undefined}
          />
        ) : null}
        </div>
        )}
      <Dialog open={validationDialogOpen} onOpenChange={handleValidationDialogChange}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t.validationTitle}</DialogTitle>
            <DialogDescription>{validationMessage || t.validationBody}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              onClick={() => handleValidationDialogChange(false)}
            >
              {locale === 'zh' ? '我来补齐' : 'Fix it now'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      </OverlayDialog>
      {setupPlanningNoticeOpen ? (
        <div
          className={cn(
            'pointer-events-none fixed inset-0 z-[10020] flex items-center justify-center bg-black/10 p-4 backdrop-blur-[2px] transition-all duration-[1800ms] ease-out',
            setupPlanningNoticeClosing ? 'opacity-0 backdrop-blur-0' : 'opacity-100'
          )}
        >
          <div
            className={cn(
              'pointer-events-auto feed-scrollbar modal-scrollbar w-full max-w-2xl max-h-[calc(100dvh-1.5rem)] overflow-y-auto rounded-[28px] border border-[rgba(45,42,38,0.08)] bg-[rgba(252,248,242,0.96)] px-5 py-5 shadow-[0_34px_100px_-54px_rgba(15,23,42,0.58)] backdrop-blur-2xl transition-all duration-[1800ms] ease-out',
              setupPlanningNoticeClosing ? 'translate-y-3 scale-[0.985] opacity-0' : 'translate-y-0 scale-100 opacity-100'
            )}
          >
            <div className="flex items-start gap-3">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-white/72 shadow-[inset_0_0_0_1px_rgba(45,42,38,0.08)]">
                <img
                  src={assetUrl('logo.svg')}
                  alt="DeepScientist"
                  className="h-7 w-7 object-contain"
                />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-base font-semibold text-black dark:text-black">
                  {locale === 'zh' ? '收到啦，正在认真规划 ✨' : 'Got it — planning carefully ✨'}
                </div>
                <div className="mt-1 text-[13px] leading-6 text-[rgba(86,82,77,0.82)]">
                  {setupPlanningNoticeSettled
                    ? locale === 'zh'
                      ? '预计总计需要约 5 分钟进行研究分析设计计划，请耐心等候。'
                      : 'This research analysis and design plan may take about 5 minutes in total. Thanks for your patience.'
                    : setupPlanningNoticeStageLabel}
                </div>
                <div
                  key={setupPlanningNoticeSettled ? 'settled' : setupPlanningNoticeLiveLine}
                  className="mt-3 rounded-2xl border border-[rgba(45,42,38,0.08)] bg-white/64 px-3.5 py-2.5 text-[13px] leading-5 text-[rgba(45,42,38,0.88)] shadow-[0_14px_36px_-32px_rgba(45,42,38,0.32)] motion-safe:animate-in motion-safe:fade-in-0 motion-safe:slide-in-from-bottom-1 motion-safe:duration-500"
                >
                  {setupPlanningNoticeSettled
                    ? locale === 'zh'
                      ? '规划生成会继续在 SetupAgent 对话里完成；完成后会自动展示可审阅的启动计划。'
                      : 'Planning will continue in the SetupAgent conversation and appear there when ready.'
                    : setupPlanningNoticeLiveLine}
                </div>
                <div className="mt-4 overflow-hidden rounded-full bg-[rgba(45,42,38,0.08)]">
                  <div
                    className={cn(
                      'h-1.5 rounded-full bg-[linear-gradient(90deg,rgba(199,173,150,0.95),rgba(157,185,198,0.95))] transition-[width,opacity] duration-700 ease-out',
                      setupPlanningNoticeSettled && 'opacity-80'
                    )}
                    style={{ width: `${Math.round(setupPlanningNoticeProgress * 100)}%` }}
                  />
                </div>
                <PlanningStepsPulse
                  locale={locale}
                  className="mt-4"
                  activeIndex={setupPlanningNoticePhaseIndex}
                  settled={setupPlanningNoticeSettled}
                />
                <div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
                  {setupPlanningNoticeCards.map((card, index) => {
                    const revealed = index < setupPlanningNoticeVisibleSectionCount
                    const active = !setupPlanningNoticeSettled && revealed && index === setupPlanningNoticeVisibleSectionCount - 1
                    const completed = setupPlanningNoticeSettled || index < setupPlanningNoticeVisibleSectionCount - 1
                    return (
                      <div
                        key={card.title}
                        className={cn(
                          'min-h-[132px] rounded-[18px] border px-3.5 py-3 transition-all duration-500',
                          active
                            ? 'border-[rgba(126,77,42,0.20)] bg-white/86 text-[rgba(45,42,38,0.92)] shadow-[0_18px_42px_-30px_rgba(126,77,42,0.34)] ring-1 ring-[rgba(199,173,150,0.28)]'
                            : revealed
                              ? 'border-[rgba(45,42,38,0.08)] bg-white/72 text-[rgba(45,42,38,0.86)] shadow-[0_12px_32px_-28px_rgba(45,42,38,0.28)]'
                              : 'border-[rgba(45,42,38,0.05)] bg-[rgba(248,245,240,0.72)] text-[rgba(107,103,97,0.62)]'
                        )}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="text-[11px] font-semibold uppercase tracking-[0.14em]">
                            {card.title}
                          </div>
                          <span
                            className={cn(
                              'mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border text-[10px] transition-all duration-500',
                              completed
                                ? 'border-[rgba(88,122,94,0.18)] bg-[rgba(88,122,94,0.12)] text-[rgba(57,96,65,0.95)]'
                                : active
                                  ? 'border-[rgba(126,77,42,0.18)] bg-[rgba(199,173,150,0.20)] text-[rgba(126,77,42,0.95)]'
                                  : 'border-[rgba(45,42,38,0.08)] bg-white/42 text-[rgba(107,103,97,0.58)]'
                            )}
                          >
                            {completed ? '✓' : active ? '•' : index + 1}
                          </span>
                        </div>
                        <div className="mt-2 text-[12px] leading-5 text-[rgba(86,82,77,0.78)]">
                          {active ? card.activeBody : card.body}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
              <button
                type="button"
                className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[rgba(107,103,97,0.72)] transition hover:bg-black/[0.04] hover:text-[rgba(45,42,38,0.94)]"
                onClick={() => {
                  closeSetupPlanningNotice()
                }}
                aria-label={locale === 'zh' ? '关闭规划提示' : 'Close planning notice'}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      ) : null}
      <DeepXivSetupDialog open={deepxivSetupOpen} onClose={() => setDeepxivSetupOpen(false)} locale={locale} />
    </>
  )
}
