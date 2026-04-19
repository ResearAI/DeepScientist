import type { ConnectorAvailabilitySnapshot } from '@/types'

export type ResearchScope = 'baseline_only' | 'baseline_plus_direction' | 'full_research'
export type BaselineMode =
  | 'auto'
  | 'existing'
  | 'restore_from_url'
  | 'allow_degraded_minimal_reproduction'
  | 'stop_if_insufficient'
export type BaselineSourceMode =
  | 'auto'
  | 'verify_local_existing'
  | 'attach_registry_baseline'
  | 'reproduce_from_source'
  | 'repair_existing_baseline'
  | 'skip_until_blocking'
export type ExecutionStartMode = 'plan_then_execute' | 'execute_immediately'
export type BaselineAcceptanceTarget =
  | 'comparison_ready'
  | 'paper_repro_ready'
  | 'registry_publishable'
export type ResourcePolicy = 'conservative' | 'balanced' | 'aggressive'
export type GitStrategy =
  | 'branch_per_analysis_then_paper'
  | 'semantic_head_plus_controlled_integration'
  | 'manual_integration_only'
export type ResearchIntensity = 'light' | 'balanced' | 'sprint'
export type DecisionPolicy = 'autonomous' | 'user_gated'
export type LaunchMode = 'standard' | 'custom'
export type StandardProfile = 'canonical_research_graph' | 'optimization_task'
export type CustomProfile =
  | 'continue_existing_state'
  | 'review_audit'
  | 'revision_rebuttal'
  | 'freeform'
export type ReviewFollowupPolicy =
  | 'audit_only'
  | 'auto_execute_followups'
  | 'user_gated_followups'
export type BaselineExecutionPolicy =
  | 'auto'
  | 'must_reproduce_or_verify'
  | 'reuse_existing_only'
  | 'skip_unless_blocking'
export type ManuscriptEditMode = 'none' | 'copy_ready_text' | 'latex_required'

export type StartResearchTemplate = {
  title: string
  quest_id: string
  goal: string
  baseline_id: string
  baseline_variant_id: string
  baseline_source_mode: BaselineSourceMode
  execution_start_mode: ExecutionStartMode
  baseline_acceptance_target: BaselineAcceptanceTarget
  baseline_urls: string
  paper_urls: string
  runtime_constraints: string
  objectives: string
  need_research_paper: boolean
  research_intensity: ResearchIntensity
  decision_policy: DecisionPolicy
  launch_mode: LaunchMode
  standard_profile: StandardProfile
  custom_profile: CustomProfile
  review_followup_policy: ReviewFollowupPolicy
  baseline_execution_policy: BaselineExecutionPolicy
  manuscript_edit_mode: ManuscriptEditMode
  entry_state_summary: string
  review_summary: string
  review_materials: string
  custom_brief: string
  user_language: 'en' | 'zh'
}

export type StartResearchContractFields = {
  scope: ResearchScope
  baseline_mode: BaselineMode
  resource_policy: ResourcePolicy
  time_budget_hours: string
  git_strategy: GitStrategy
}

export type StartResearchConnectorChoice = {
  name: string
  targets: Array<{
    conversationId: string
  }>
}

export type StartResearchTemplateEntry = StartResearchTemplate & {
  id: string
  updated_at: string
  compiled_prompt: string
}

type PersistedStartResearchTemplate = Partial<
  StartResearchTemplate &
    StartResearchContractFields & {
      baseline_root_id?: string
    }
>

const START_RESEARCH_INTENSITY_PRESETS: Record<
  ResearchIntensity,
  {
    id: ResearchIntensity
    contract: StartResearchContractFields
  }
> = {
  light: {
    id: 'light',
    contract: {
      scope: 'baseline_only',
      baseline_mode: 'stop_if_insufficient',
      resource_policy: 'conservative',
      time_budget_hours: '8',
      git_strategy: 'manual_integration_only',
    },
  },
  balanced: {
    id: 'balanced',
    contract: {
      scope: 'baseline_plus_direction',
      baseline_mode: 'auto',
      resource_policy: 'balanced',
      time_budget_hours: '24',
      git_strategy: 'semantic_head_plus_controlled_integration',
    },
  },
  sprint: {
    id: 'sprint',
    contract: {
      scope: 'full_research',
      baseline_mode: 'allow_degraded_minimal_reproduction',
      resource_policy: 'aggressive',
      time_budget_hours: '48',
      git_strategy: 'branch_per_analysis_then_paper',
    },
  },
}

export const START_RESEARCH_INTENSITY_ORDER: ResearchIntensity[] = ['light', 'balanced', 'sprint']

export const START_RESEARCH_STORAGE_KEY = 'ds:start-research:v5'
export const START_RESEARCH_HISTORY_KEY = 'ds:start-research:history:v4'
const LEGACY_START_RESEARCH_STORAGE_KEYS = ['ds:start-research:v4', 'ds:start-research:v3']
const LEGACY_START_RESEARCH_HISTORY_KEYS = ['ds:start-research:history:v3', 'ds:start-research:history:v2']
const MAX_TEMPLATE_HISTORY = 8

export function slugifyQuestRepo(value: string) {
  const normalized = value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return normalized.slice(0, 80)
}

export function deriveQuestRepoId(input: { title?: string; goal?: string }) {
  const fromTitle = slugifyQuestRepo(input.title || '')
  if (fromTitle) {
    return fromTitle
  }
  const fromGoal = slugifyQuestRepo((input.goal || '').split(/\n+/)[0] || '')
  return fromGoal
}

export function defaultStartResearchTemplate(language: 'en' | 'zh'): StartResearchTemplate {
  return {
    title: '',
    quest_id: '',
    goal: '',
      baseline_id: '',
      baseline_variant_id: '',
      baseline_source_mode: 'auto',
      execution_start_mode: 'execute_immediately',
      baseline_acceptance_target: 'comparison_ready',
      baseline_urls: '',
    paper_urls: '',
    runtime_constraints: '',
    objectives: '',
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
    user_language: language,
  }
}

export function shouldRecommendStartResearchConnectorBinding(input: {
  open: boolean
  availabilityResolved: boolean
  availabilityLoading: boolean
  availabilityError?: string | null
  connectorRecommendationHandled: boolean
  availability: ConnectorAvailabilitySnapshot | null
}) {
  if (!input.open) return false
  if (!input.availabilityResolved) return false
  if (input.availabilityLoading) return false
  if (input.availabilityError) return false
  if (input.connectorRecommendationHandled) return false
  return Boolean(input.availability?.should_recommend_binding)
}

export function resolveStartResearchConnectorBindings(
  items: StartResearchConnectorChoice[],
  current: Record<string, string | null> = {}
) {
  const next: Record<string, string | null> = {}
  const hasExplicitState = items.some((item) => Object.prototype.hasOwnProperty.call(current, item.name))
  const hasExplicitSelection = items.some((item) => Boolean(String(current[item.name] || '').trim()))
  const explicitLocalOnly = hasExplicitState && !hasExplicitSelection
  let selectedConnectorName: string | null = null

  for (const item of items) {
    const currentValue = String(current[item.name] || '').trim() || null
    const normalizedTargets = item.targets
      .map((target) => String(target.conversationId || '').trim())
      .filter(Boolean)
    if (currentValue && normalizedTargets.includes(currentValue)) {
      next[item.name] = currentValue
      if (!selectedConnectorName) {
        selectedConnectorName = item.name
      }
      continue
    }
    next[item.name] = normalizedTargets[0] || null
  }

  if (explicitLocalOnly) {
    for (const item of items) {
      next[item.name] = null
    }
    return next
  }

  if (!selectedConnectorName) {
    selectedConnectorName =
      items.find((item) => String(next[item.name] || '').trim())?.name || null
  }

  if (!selectedConnectorName) {
    return next
  }

  for (const item of items) {
    if (item.name !== selectedConnectorName) {
      next[item.name] = null
    }
  }

  return next
}

export function listReferenceStartResearchTemplates(): StartResearchTemplateEntry[] {
  const timestamp = '2026-03-17T00:00:00.000Z'
  const zhTemplate: StartResearchTemplate = {
    title: '参考示例 · 在指定推理端点上复现 P-and-B 并探索更优的 token 控制',
    quest_id: '',
    goal: [
      '请复现 P-and-B（Planning and Budgeting）论文与官方仓库中的核心 baseline，并在严格保持评测任务一致的前提下，继续探索更高质量、更省 token、且具有学术洞见的改进方向。',
      '',
      '下面的 endpoint / API key / model 只是参考占位，不是 DeepScientist 的默认配置。请替换成你的真实运行时，例如 base URL `http://<your-host>:<your-port>/v1`、API key `<YOUR_API_KEY>`、模型 `<YOUR_MODEL>`。研究时只围绕你实际填入的那组配置完成 baseline 复现、分析与改进，不要把本示例当成系统默认值。',
      '',
      '要求先完整恢复并验证官方 baseline，再沿着文献调研与实验结果提出新方向。所有新 idea 都必须建立在充分的相关工作阅读、对失败模式的分析，以及对当前最佳 baseline 的清晰理解之上。',
      '',
      '研究目标不是只得到一个更高分结果，而是形成一项适合作为论文工作的研究成果：结论需要可靠，洞见需要明确，结果需要能解释为什么有效、何时有效、何时无效。',
    ].join('\n'),
    baseline_id: '',
    baseline_variant_id: '',
    baseline_source_mode: 'reproduce_from_source',
    execution_start_mode: 'plan_then_execute',
    baseline_acceptance_target: 'paper_repro_ready',
    baseline_urls: 'https://github.com/junhongmit/P-and-B',
    paper_urls: 'https://arxiv.org/abs/2505.16122',
    runtime_constraints: [
      '- 以下 runtime 示例仅供参考，不是产品默认配置。',
      '- 将推理接口 base URL 替换为你的真实 endpoint，例如 `http://<your-host>:<your-port>/v1`。',
      '- 将 API key 替换为你的真实密钥，例如 `<YOUR_API_KEY>`。',
      '- 将模型替换为你的真实模型，例如 `<YOUR_MODEL>`；实验记录里统一使用你实际采用的模型名。',
      '- 只围绕你实际填写的 endpoint + key + model 完成研究；不要把本示例当成系统默认值，也不要横向测试其他模型。',
      '- `max_tokens`、任务定义与主要评测协议默认保持官方设置；只有在明确证据表明当前上限不够时，才允许做最小幅度调整并记录原因。',
      '- 最大并发数量按 `96` 设计，可以使用最多 `96` 个并发 worker / 异步请求；如需调整并发、超时或重试逻辑，必须记录原因。',
      '- 在不破坏服务稳定性的前提下，尽量占满 API 服务器吞吐。',
      '- 除非有充分证据证明必须调整，否则优先保持官方 baseline 的任务定义、主要超参数与评测协议不变。',
      '- 不允许伪造实验结果；失败、异常、中断和退化结果都必须如实记录。',
    ].join('\n'),
    objectives: [
      '1. 恢复并验证官方 baseline，形成可复用的可信起点。',
      '2. 在你实际指定的单一推理端点上记录关键指标、token 开销、长尾失败模式与主要观察结论。',
      '3. 基于文献与实验结果提出至少一个有研究价值的改进方向。',
      '4. 形成足以支持论文写作的实验与分析材料。',
    ].join('\n'),
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

  const enTemplate: StartResearchTemplate = {
    title: 'Reference example · Reproduce P-and-B on a specified inference endpoint and explore better token control',
    quest_id: '',
    goal: [
      'Please reproduce the core baselines from the P-and-B (Planning and Budgeting) paper and official repository, then continue exploring stronger and more token-efficient reasoning-control ideas while keeping the task definition and evaluation protocol faithful to the original work.',
      '',
      'The endpoint / API key / model below are reference placeholders only, not DeepScientist defaults. Replace them with your real runtime setup, for example base URL `http://<your-host>:<your-port>/v1`, API key `<YOUR_API_KEY>`, and model `<YOUR_MODEL>`. The task should stay focused on the actual setup you provide rather than treating this example as a built-in default.',
      '',
      'The workflow should first restore and verify the official baselines, then move into literature-grounded idea generation and evidence-driven experimentation. Every new idea must be justified by careful reading of related work, analysis of failure modes, and a clear understanding of the current best baseline.',
      '',
      'The goal is not merely to obtain one better score, but to produce a paper-worthy research result: the claims must be reliable, the insights must be explicit, and the evidence must explain why the method helps, when it helps, and where it breaks.',
    ].join('\n'),
    baseline_id: '',
    baseline_variant_id: '',
    baseline_source_mode: 'reproduce_from_source',
    execution_start_mode: 'plan_then_execute',
    baseline_acceptance_target: 'paper_repro_ready',
    baseline_urls: 'https://github.com/junhongmit/P-and-B',
    paper_urls: 'https://arxiv.org/abs/2505.16122',
    runtime_constraints: [
      '- The runtime values below are reference placeholders only, not product defaults.',
      '- Replace the inference base URL with your actual endpoint, for example `http://<your-host>:<your-port>/v1`.',
      '- Replace the API key with your real secret, for example `<YOUR_API_KEY>`.',
      '- Replace the model with your real model id, for example `<YOUR_MODEL>`; normalize experiment records to the actual model name you use.',
      '- Use only the endpoint + key + model combination you actually provide; do not treat this example as a built-in default or turn the project into a multi-model benchmark.',
      '- Keep `max_tokens`, task definition, and the main evaluation protocol aligned with the official setup unless there is concrete evidence that the token cap itself is blocking valid runs; if changed, record the reason explicitly.',
      '- Design for up to `96` concurrent workers / async requests; if concurrency, timeout, or retry settings are changed, record the reason explicitly.',
      '- Keep throughput high without destabilizing the service, and try to saturate the available API capacity safely.',
      '- Preserve the official task setup, major hyperparameters, and evaluation protocol unless there is concrete evidence that an adaptation is necessary.',
      '- Never fabricate results; failed, interrupted, degraded, or inconclusive runs must be recorded honestly.',
    ].join('\n'),
    objectives: [
      '1. Restore and verify the official baseline as a trustworthy reusable starting point.',
      '2. On the single inference endpoint you actually specify, record key metrics, token costs, long-tail failure modes, and main observations.',
      '3. Propose at least one research-worthy improvement direction grounded in literature and experimental evidence.',
      '4. Produce experiment and analysis assets that are strong enough to support paper writing.',
    ].join('\n'),
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

  const templates = [
    { id: 'builtin_example_zh_pandb', template: zhTemplate },
    { id: 'builtin_example_en_pandb', template: enTemplate },
  ]

  return templates.map(({ id, template }) => ({
    ...template,
    id,
    updated_at: timestamp,
    compiled_prompt: compileStartResearchPrompt(template),
  }))
}

export function listStartResearchIntensityPresets() {
  return START_RESEARCH_INTENSITY_ORDER.map((presetId) => START_RESEARCH_INTENSITY_PRESETS[presetId])
}

export function applyStartResearchIntensityPreset(
  input: StartResearchTemplate,
  presetId: ResearchIntensity
): StartResearchTemplate {
  return {
    ...input,
    research_intensity: presetId,
  }
}

export function detectStartResearchIntensity(
  input: Pick<StartResearchTemplate, 'research_intensity' | 'baseline_id'> &
    Partial<StartResearchContractFields>
): ResearchIntensity {
  return sanitizeResearchIntensity(input.research_intensity, input)
}

function sanitizeResearchIntensity(
  value: unknown,
  input?: Partial<StartResearchTemplate & StartResearchContractFields>
): ResearchIntensity {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized === 'light' || normalized === 'balanced' || normalized === 'sprint') {
    return normalized
  }
  const scope = String(input?.scope || '').trim()
  const resourcePolicy = String(input?.resource_policy || '').trim()
  const gitStrategy = String(input?.git_strategy || '').trim()
  const timeBudget = String(input?.time_budget_hours || '').trim()
  if (
    scope === 'baseline_only' ||
    resourcePolicy === 'conservative' ||
    gitStrategy === 'manual_integration_only' ||
    timeBudget === '8'
  ) {
    return 'light'
  }
  if (
    scope === 'full_research' ||
    resourcePolicy === 'aggressive' ||
    gitStrategy === 'branch_per_analysis_then_paper' ||
    timeBudget === '48'
  ) {
    return 'sprint'
  }
  return 'balanced'
}

function sanitizeDecisionPolicy(value: unknown): DecisionPolicy {
  const normalized = String(value || '').trim().toLowerCase()
  return normalized === 'user_gated' ? 'user_gated' : 'autonomous'
}

function sanitizeLaunchMode(value: unknown): LaunchMode {
  const normalized = String(value || '').trim().toLowerCase()
  return normalized === 'custom' ? 'custom' : 'standard'
}

function sanitizeStandardProfile(value: unknown): StandardProfile {
  const normalized = String(value || '').trim().toLowerCase()
  return normalized === 'optimization_task' ? 'optimization_task' : 'canonical_research_graph'
}

function sanitizeCustomProfile(value: unknown): CustomProfile {
  const normalized = String(value || '').trim().toLowerCase()
  if (
    normalized === 'continue_existing_state' ||
    normalized === 'review_audit' ||
    normalized === 'revision_rebuttal' ||
    normalized === 'freeform'
  ) {
    return normalized
  }
  return 'freeform'
}

function sanitizeBaselineExecutionPolicy(value: unknown): BaselineExecutionPolicy {
  const normalized = String(value || '').trim().toLowerCase()
  if (
    normalized === 'auto' ||
    normalized === 'must_reproduce_or_verify' ||
    normalized === 'reuse_existing_only' ||
    normalized === 'skip_unless_blocking'
  ) {
    return normalized
  }
  return 'auto'
}

function sanitizeBaselineSourceMode(value: unknown): BaselineSourceMode {
  const normalized = String(value || '').trim().toLowerCase()
  if (
    normalized === 'auto' ||
    normalized === 'verify_local_existing' ||
    normalized === 'attach_registry_baseline' ||
    normalized === 'reproduce_from_source' ||
    normalized === 'repair_existing_baseline' ||
    normalized === 'skip_until_blocking'
  ) {
    return normalized
  }
  return 'auto'
}

function sanitizeExecutionStartMode(value: unknown): ExecutionStartMode {
  const normalized = String(value || '').trim().toLowerCase()
  return normalized === 'plan_then_execute' ? 'plan_then_execute' : 'execute_immediately'
}

function sanitizeBaselineAcceptanceTarget(value: unknown): BaselineAcceptanceTarget {
  const normalized = String(value || '').trim().toLowerCase()
  if (
    normalized === 'comparison_ready' ||
    normalized === 'paper_repro_ready' ||
    normalized === 'registry_publishable'
  ) {
    return normalized
  }
  return 'comparison_ready'
}

function sanitizeReviewFollowupPolicy(value: unknown): ReviewFollowupPolicy {
  const normalized = String(value || '').trim().toLowerCase()
  if (
    normalized === 'audit_only' ||
    normalized === 'auto_execute_followups' ||
    normalized === 'user_gated_followups'
  ) {
    return normalized
  }
  return 'audit_only'
}

function sanitizeManuscriptEditMode(value: unknown): ManuscriptEditMode {
  const normalized = String(value || '').trim().toLowerCase()
  if (normalized === 'none' || normalized === 'copy_ready_text' || normalized === 'latex_required') {
    return normalized
  }
  return 'none'
}

function sanitizeLines(text: string) {
  return text
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

export function resolveStartResearchContractFields(
  input: Pick<StartResearchTemplate, 'research_intensity' | 'baseline_id' | 'baseline_source_mode'>
): StartResearchContractFields {
  const intensity = sanitizeResearchIntensity(input.research_intensity, input)
  const resolved = {
    ...START_RESEARCH_INTENSITY_PRESETS[intensity].contract,
  }
  const baselineSourceMode = sanitizeBaselineSourceMode(input.baseline_source_mode)
  if (baselineSourceMode === 'verify_local_existing' || baselineSourceMode === 'attach_registry_baseline') {
    resolved.baseline_mode = 'existing'
    return resolved
  }
  if (baselineSourceMode === 'reproduce_from_source') {
    resolved.baseline_mode = 'restore_from_url'
    return resolved
  }
  if (baselineSourceMode === 'repair_existing_baseline') {
    resolved.baseline_mode = 'allow_degraded_minimal_reproduction'
    return resolved
  }
  if (baselineSourceMode === 'skip_until_blocking') {
    resolved.baseline_mode = 'stop_if_insufficient'
    return resolved
  }
  if (String(input.baseline_id || '').trim()) {
    resolved.baseline_mode = 'existing'
  }
  return resolved
}

function sanitizeTemplate(input: PersistedStartResearchTemplate): StartResearchTemplate {
  const legacyBaselineId = input.baseline_root_id
  return {
    title: String(input.title || '').trim(),
    quest_id: slugifyQuestRepo(String(input.quest_id || '')),
    goal: String(input.goal || '').trim(),
    baseline_id: String(input.baseline_id || legacyBaselineId || '').trim(),
    baseline_variant_id: String(input.baseline_variant_id || '').trim(),
    baseline_source_mode: sanitizeBaselineSourceMode(input.baseline_source_mode),
    execution_start_mode: sanitizeExecutionStartMode(input.execution_start_mode),
    baseline_acceptance_target: sanitizeBaselineAcceptanceTarget(input.baseline_acceptance_target),
    baseline_urls: String(input.baseline_urls || '').trim(),
    paper_urls: String(input.paper_urls || '').trim(),
    runtime_constraints: String(input.runtime_constraints || '').trim(),
    objectives: String(input.objectives || '').trim(),
    need_research_paper: input.need_research_paper !== false,
    research_intensity: sanitizeResearchIntensity(input.research_intensity, input),
    decision_policy: sanitizeDecisionPolicy(input.decision_policy),
    launch_mode: sanitizeLaunchMode(input.launch_mode),
    standard_profile: sanitizeStandardProfile(input.standard_profile),
    custom_profile: sanitizeCustomProfile(input.custom_profile),
    review_followup_policy: sanitizeReviewFollowupPolicy(input.review_followup_policy),
    baseline_execution_policy: sanitizeBaselineExecutionPolicy(input.baseline_execution_policy),
    manuscript_edit_mode: sanitizeManuscriptEditMode(input.manuscript_edit_mode),
    entry_state_summary: String(input.entry_state_summary || '').trim(),
    review_summary: String(input.review_summary || '').trim(),
    review_materials: String(input.review_materials || '').trim(),
    custom_brief: String(input.custom_brief || '').trim(),
    user_language: input.user_language === 'en' ? 'en' : 'zh',
  }
}

function withoutPersistedQuestId(input: StartResearchTemplate): StartResearchTemplate {
  return {
    ...sanitizeTemplate(input),
    quest_id: '',
  }
}

function stableId(input: StartResearchTemplate) {
  const source = JSON.stringify(withoutPersistedQuestId(input))
  let hash = 0
  for (let index = 0; index < source.length; index += 1) {
    hash = (hash * 31 + source.charCodeAt(index)) >>> 0
  }
  return `tmpl_${hash.toString(36)}`
}

function labelResearchIntensity(value: ResearchIntensity) {
  switch (value) {
    case 'light':
      return 'Light: keep the first round tight, conservative, and baseline-first.'
    case 'sprint':
      return 'Sprint: use a larger round to push through baseline, implementation, and analysis-ready evidence faster.'
    default:
      return 'Balanced: secure a trustworthy baseline and probe one justified direction without overcommitting.'
  }
}

function labelDecisionPolicy(value: DecisionPolicy) {
  switch (value) {
    case 'user_gated':
      return 'User-gated: ask the user for a blocking decision only when continuation truly depends on their preference or approval.'
    default:
      return 'Autonomous: decide ordinary route choices yourself, keep the user informed through threaded updates, and do not hand routine decisions back to the user.'
  }
}

function labelLaunchMode(value: LaunchMode) {
  switch (value) {
    case 'custom':
      return 'Custom mode: start from an existing state, review-driven task, or a user-defined brief instead of assuming a blank full-research launch.'
    default:
      return 'Standard mode: start from the ordinary canonical research loop and let the default stage graph drive the first round.'
  }
}

function labelStandardProfile(value: StandardProfile) {
  switch (value) {
    case 'optimization_task':
      return 'Optimization task: skip default paper writing and avoid default analysis-campaign routing; focus on repeated implementation attempts and the strongest justified result.'
    default:
      return 'Canonical research workflow: follow the ordinary research graph from baseline and idea selection through experiment, analysis, and paper work when justified.'
  }
}

function labelCustomProfile(value: CustomProfile) {
  switch (value) {
    case 'continue_existing_state':
      return 'Continue existing state: audit and normalize an existing baseline, result, draft, or mixed project state before deciding the next anchor.'
    case 'review_audit':
      return 'Review / audit: treat the current draft or paper package as the active contract and run an independent skeptical review before more writing or finalization.'
    case 'revision_rebuttal':
      return 'Revision / rebuttal: treat the current paper and reviewer package as the active contract, then route supplementary experiments and manuscript edits from that state.'
    default:
      return 'Other / freeform: follow the user-defined custom brief and open only the skills actually needed.'
  }
}

function labelBaselineExecutionPolicy(value: BaselineExecutionPolicy) {
  switch (value) {
    case 'must_reproduce_or_verify':
      return 'Reproduce or verify first: explicitly recover or verify the rebuttal-critical baseline/comparator before reviewer-linked follow-up work.'
    case 'reuse_existing_only':
      return 'Reuse existing only: start from the trusted current baseline and do not rerun it unless the stored evidence is inconsistent or unusable.'
    case 'skip_unless_blocking':
      return 'Skip unless blocking: do not spend time rerunning baselines by default; only do it if a reviewer-linked item truly depends on a missing comparator.'
    default:
      return 'Automatic: let the startup contract and current evidence decide whether rebuttal work should verify, reuse, or skip baseline reruns.'
  }
}

function labelBaselineSourceMode(value: BaselineSourceMode) {
  switch (value) {
    case 'verify_local_existing':
      return 'Verify local existing: if local code or a local service is already comparison-ready, verify it first instead of reproducing from scratch.'
    case 'attach_registry_baseline':
      return 'Attach registry baseline: treat a reusable registered baseline as the preferred comparator route.'
    case 'reproduce_from_source':
      return 'Reproduce from source: restore the baseline from repositories or artifacts when no trusted local comparator already exists.'
    case 'repair_existing_baseline':
      return 'Repair existing baseline: fix or refresh a stale local baseline before rebuilding it from zero.'
    case 'skip_until_blocking':
      return 'Skip until blocking: do not front-load baseline work unless later evidence shows the missing comparator is actually blocking.'
    default:
      return 'Automatic: choose the lightest trustworthy comparator route from the current baseline sources and local evidence.'
  }
}

function labelExecutionStartMode(value: ExecutionStartMode) {
  switch (value) {
    case 'plan_then_execute':
      return 'Plan first: write a concrete bounded execution plan and wait for user approval before heavy reproduction or expensive setup.'
    default:
      return 'Execute immediately: if the route is already clear, begin the smallest useful execution step without a separate approval round.'
  }
}

function labelBaselineAcceptanceTarget(value: BaselineAcceptanceTarget) {
  switch (value) {
    case 'paper_repro_ready':
      return 'Paper-grade reproduction ready: do not treat the baseline as complete until the reproduction is strong enough to defend in a paper.'
    case 'registry_publishable':
      return 'Registry publishable: treat the baseline as complete only when it is clean and reusable enough to publish as a reusable baseline package.'
    default:
      return 'Comparison ready: accept the lightest trustworthy comparator that is sufficient for downstream idea selection and experiment comparison.'
  }
}

function labelReviewFollowupPolicy(value: ReviewFollowupPolicy) {
  switch (value) {
    case 'auto_execute_followups':
      return 'Auto-execute follow-ups: after the audit artifacts are durable, continue automatically into the required experiments, manuscript deltas, and closure work.'
    case 'user_gated_followups':
      return 'User-gated follow-ups: finish the audit first, then turn the next major experiment/revision package into a structured decision if continuation depends on user approval.'
    default:
      return 'Audit only: stop after the review artifacts and route recommendation are durable.'
  }
}

function labelManuscriptEditMode(value: ManuscriptEditMode) {
  switch (value) {
    case 'copy_ready_text':
      return 'Copy-ready text: produce manuscript-facing revision text and section-level deltas, but do not require LaTeX-specific delivery.'
    case 'latex_required':
      return 'LaTeX required: when manuscript revision is needed, prefer the provided LaTeX tree as the writing surface and produce LaTeX-ready replacement text; if LaTeX source is unavailable, make that blocker explicit.'
    default:
      return 'No manuscript edit package is required by default beyond the review/rebuttal planning artifacts.'
  }
}

function labelScope(value: ResearchScope) {
  switch (value) {
    case 'baseline_only':
      return 'Baseline only: stop after a solid reusable baseline is established.'
    case 'baseline_plus_direction':
      return 'Baseline + direction: secure the baseline, then test one promising improvement direction.'
    default:
      return 'Full research: baseline, idea selection, implementation, analysis, and writing readiness.'
  }
}

function labelBaselineMode(value: BaselineMode) {
  switch (value) {
    case 'existing':
      return 'Use existing baseline: trust the selected reusable baseline first and let runtime attach and confirm it before the project begins.'
    case 'restore_from_url':
      return 'Restore from URL: recover the baseline from provided repositories or artifact links.'
    case 'allow_degraded_minimal_reproduction':
      return 'Allow degraded minimal reproduction: accept a weaker but still measurable baseline if exact recovery is impossible.'
    default:
      return 'Stop if insufficient: pause the project instead of faking a baseline when evidence is missing.'
  }
}

function labelResourcePolicy(value: ResourcePolicy) {
  switch (value) {
    case 'conservative':
      return 'Conservative: minimize compute and only run the most justified steps.'
    case 'aggressive':
      return 'Aggressive: spend more resources to search broadly and move faster.'
    default:
      return 'Balanced: keep progress steady while still controlling cost and risk.'
  }
}

function labelGitStrategy(value: GitStrategy) {
  switch (value) {
    case 'semantic_head_plus_controlled_integration':
      return 'Semantic head + controlled integration: keep a cleaner main line and merge only reviewed branches.'
    case 'manual_integration_only':
      return 'Manual integration only: avoid automatic integration and require explicit merge decisions.'
    default:
      return 'Branch per analysis then paper: split main experiment and downstream analysis branches before final paper integration.'
  }
}

function deliveryModeLines(needResearchPaper: boolean) {
  if (needResearchPaper) {
    return [
      '- A research paper is required for this project.',
      '- The default paper-facing route is baseline, idea selection, implementation, measured experiments, only the analysis that the evidence actually needs, then drafting and packaging.',
      '- Do not stop after obtaining only one improved algorithm or one promising run unless the user explicitly narrows scope.',
      '- After each `artifact.record_main_experiment(...)`, first interpret the measured result, then decide whether to improve further, run necessary follow-up analysis, or move into writing.',
      '- The idea stage only creates or revises a candidate direction; the round is not complete until a main experiment result is recorded and routed.',
      '- Treat later analysis, review, and finalize work as follow-on stages to open when the nearer gate is actually ready, not as boxes that must always be pre-completed before progress counts.',
    ]
  }
  return [
    '- A research paper is NOT required for this project.',
    '- The primary goal is the strongest justified algorithmic result, not paper drafting or paper packaging.',
    '- The project must still do rigorous baseline work, literature-grounded idea selection, implementation, and main experiments.',
    '- Do not schedule analysis-campaign work by default; only run extra analysis when it directly changes optimization decisions or validates a suspected result.',
    '- After each `artifact.record_main_experiment(...)`, use the measured result to decide the next optimization step.',
    '- The idea stage only creates or revises a candidate direction; it does not by itself decide the next round.',
    '- The agent should decide how to continue from durable evidence such as the accepted baseline, the current research head, and the strongest recent main-experiment result.',
    '- Do not default into `artifact.submit_paper_outline(...)`, `artifact.submit_paper_bundle(...)`, or paper/finalize work unless the user later explicitly asks for paper writing.',
    '- Even without paper writing, all important decisions, runs, evidence, and conclusions must be recorded durably so later rounds can build on them.',
  ]
}

function decisionPolicyLines(value: DecisionPolicy) {
  if (value === 'user_gated') {
    return [
      '- User-gated decision mode is active.',
      '- If a real route choice cannot be resolved safely from local evidence, ask the user with a structured blocking decision request.',
      '- Even in user-gated mode, ordinary progress and stage completions should stay threaded and non-blocking.',
    ]
  }
  return [
    '- Autonomous decision mode is active.',
    '- Do not hand ordinary route, branch, cost, baseline-reuse, or experiment-selection decisions back to the user by default.',
    '- If the main fork is a large-cost choice such as verify/reuse versus full reproduction, one short clarification or one bounded plan is acceptable before heavy execution.',
    '- Report chosen routes through threaded progress or milestone updates, and keep moving unless you are explicitly requesting final completion approval.',
  ]
}

function customLaunchLines(input: StartResearchTemplate) {
  const normalized = sanitizeTemplate(input)
  if (normalized.launch_mode !== 'custom') {
    if (normalized.standard_profile === 'optimization_task') {
      return [
        '- Standard launch mode is active.',
        '- Standard profile: optimization task.',
        '- This standard entry is non-paper by default: do not plan around paper writing, paper review, paper bundle work, or default analysis-campaign expansion.',
        '- The first round should focus on baseline trust, implementation attempts, fast iteration, main-experiment measurement, and promotion of the strongest durable optimization line.',
      ]
    }
    return [
      '- Standard launch mode is active.',
      '- Standard profile: canonical research workflow.',
      '- Start from the canonical research graph unless durable state later proves that a non-standard entry path is better.',
    ]
  }
  const lines = [
    '- Custom launch mode is active.',
    '- Do not force the project into a blank full-research loop if the custom brief is narrower or the project already has meaningful durable state.',
    `- Custom profile: ${labelCustomProfile(normalized.custom_profile)}`,
  ]
  if (normalized.entry_state_summary) {
    lines.push('- Existing state summary:', normalized.entry_state_summary)
  }
  if ((normalized.custom_profile === 'review_audit' || normalized.custom_profile === 'revision_rebuttal') && normalized.review_summary) {
    lines.push('- Review / revision summary:', normalized.review_summary)
  }
  if ((normalized.custom_profile === 'review_audit' || normalized.custom_profile === 'revision_rebuttal') && normalized.review_materials) {
    lines.push('- Review materials (URLs or local paths/directories):')
    lines.push(...sanitizeLines(normalized.review_materials).map((item) => `  - ${item}`))
  }
  if (normalized.custom_brief) {
    lines.push('- Custom brief:', normalized.custom_brief)
  }
  if (normalized.custom_profile === 'review_audit') {
    lines.push(`- Review follow-up policy: ${labelReviewFollowupPolicy(normalized.review_followup_policy)}`)
  }
  lines.push(`- Baseline execution policy: ${labelBaselineExecutionPolicy(normalized.baseline_execution_policy)}`)
  if (normalized.custom_profile === 'review_audit' || normalized.custom_profile === 'revision_rebuttal') {
    lines.push(`- Manuscript edit mode: ${labelManuscriptEditMode(normalized.manuscript_edit_mode)}`)
  }
  if (normalized.custom_profile === 'continue_existing_state') {
    lines.push('- First action: audit and trust-rank existing baselines, results, drafts, or review assets before rerunning expensive work.')
    lines.push('- Prefer `intake-audit` first if the starting state is not already normalized.')
    lines.push('- First goal: recover the active route and unlock the next blocker, not restart the full research graph from zero.')
  } else if (normalized.custom_profile === 'review_audit') {
    lines.push('- First action: inspect the current manuscript and run an independent skeptical audit before further drafting or finalization.')
    lines.push('- Prefer `review` first, and only route to extra experiments when the audit shows the current evidence is genuinely insufficient.')
    if (normalized.review_followup_policy === 'auto_execute_followups') {
      lines.push('- After the audit artifacts are durable, continue automatically into the required experiments, manuscript deltas, and review-closure work.')
    } else if (normalized.review_followup_policy === 'user_gated_followups') {
      lines.push('- After the audit artifacts are durable, turn the next expensive follow-up package into a structured decision before continuing.')
    } else {
      lines.push('- Stop after the durable audit artifacts unless the user later asks for execution follow-up.')
    }
  } else if (normalized.custom_profile === 'revision_rebuttal') {
    lines.push('- First action: interpret reviewer comments and current paper state before ordinary writing or fresh ideation.')
    lines.push('- Prefer `rebuttal` first, and route supplementary runs only when a reviewer issue genuinely requires them.')
    lines.push('- If a manuscript PDF, reviewer packet, or local review directory is already known, inspect and normalize those inputs before planning reviewer-linked experiments.')
  } else {
    lines.push('- First action: follow the custom brief and open only the minimum necessary skills.')
  }
  return lines
}

export function compileStartResearchPrompt(input: StartResearchTemplate) {
  const normalized = sanitizeTemplate(input)
  const derivedContract = resolveStartResearchContractFields(normalized)
  const baselineUrls = sanitizeLines(normalized.baseline_urls)
  const paperUrls = sanitizeLines(normalized.paper_urls)
  const baselineVariant = normalized.baseline_variant_id
  const baselineSourceMode = sanitizeBaselineSourceMode(normalized.baseline_source_mode)
  const executionStartMode = sanitizeExecutionStartMode(normalized.execution_start_mode)
  const baselineAcceptanceTarget = sanitizeBaselineAcceptanceTarget(normalized.baseline_acceptance_target)
  const baselineContext = normalized.baseline_id
    ? `Runtime will attach and confirm baseline_id ${normalized.baseline_id}${baselineVariant ? ` (variant ${baselineVariant})` : ''} before the project starts. Treat it as the pre-bound baseline unless you find a concrete incompatibility, corruption, or missing-evidence problem.`
    : baselineUrls.length > 0
      ? baselineUrls.map((url) => `- ${url}`).join('\n')
      : 'No baseline link has been attached yet. First establish the lightest trustworthy comparator for this quest instead of assuming a full source reproduction is automatically required.'
  const questRepo = normalized.quest_id || 'auto-assigned-sequential-on-create'
  const objectiveLines = normalized.objectives
    ? sanitizeLines(normalized.objectives).map((line) => `- ${line}`).join('\n')
    : '- Produce a trustworthy baseline\n- Decide whether the current direction is worth implementation\n- Preserve clean artifacts, metrics, and reasons for each decision'

  return [
    'Project Bootstrap',
    `- Project title: ${normalized.title || 'Untitled project'}`,
    `- Project id: ${questRepo}`,
    `- User language: ${normalized.user_language === 'zh' ? 'Chinese' : 'English'}`,
    '',
    'Primary Research Request',
    normalized.goal || 'No goal provided.',
    '',
    'Research Goals',
    objectiveLines,
    '',
    'Baseline Context',
    baselineContext,
    '',
    'Baseline Source Preference',
    `- ${labelBaselineSourceMode(baselineSourceMode)}`,
    '',
    'Execution Start Mode',
    `- ${labelExecutionStartMode(executionStartMode)}`,
    '',
    'Baseline Acceptance Target',
    `- ${labelBaselineAcceptanceTarget(baselineAcceptanceTarget)}`,
    '',
    'Reference Papers / Repositories / Local Paths',
    paperUrls.length > 0 ? paperUrls.map((url) => `- ${url}`).join('\n') : '- None provided',
    '',
    'Operational Constraints',
    normalized.runtime_constraints || 'No explicit runtime, privacy, dataset, or hardware constraints were provided.',
    '',
    'Research Delivery Mode',
    ...deliveryModeLines(normalized.need_research_paper),
    '',
    'Decision Handling Mode',
    ...decisionPolicyLines(normalized.decision_policy),
    '',
    'Launch Mode',
    ...customLaunchLines(normalized),
    '',
    'Research Contract',
    `- Launch mode: ${labelLaunchMode(normalized.launch_mode)}`,
    `- Standard entry type: ${normalized.launch_mode === 'standard' ? labelStandardProfile(normalized.standard_profile) : 'Not applicable outside Standard mode.'}`,
    `- Research intensity: ${labelResearchIntensity(normalized.research_intensity)}`,
    `- Decision policy: ${labelDecisionPolicy(normalized.decision_policy)}`,
    `- Research paper required: ${normalized.need_research_paper ? 'Yes' : 'No; optimize for the strongest justified algorithmic result.'}`,
    `- Scope: ${labelScope(derivedContract.scope)}`,
    `- Baseline policy: ${labelBaselineMode(derivedContract.baseline_mode)}`,
    `- Baseline source preference: ${labelBaselineSourceMode(baselineSourceMode)}`,
    `- Execution start mode: ${labelExecutionStartMode(executionStartMode)}`,
    `- Baseline acceptance target: ${labelBaselineAcceptanceTarget(baselineAcceptanceTarget)}`,
    `- Review follow-up policy: ${normalized.custom_profile === 'review_audit' ? labelReviewFollowupPolicy(normalized.review_followup_policy) : 'Not applicable outside the Review custom task type.'}`,
    `- Baseline execution policy: ${normalized.launch_mode === 'custom' ? labelBaselineExecutionPolicy(normalized.baseline_execution_policy) : 'Standard baseline handling from the ordinary research loop.'}`,
    `- Manuscript edit mode: ${normalized.custom_profile === 'review_audit' || normalized.custom_profile === 'revision_rebuttal' ? labelManuscriptEditMode(normalized.manuscript_edit_mode) : 'No manuscript-facing custom edit contract requested.'}`,
    `- Resource policy: ${labelResourcePolicy(derivedContract.resource_policy)}`,
    `- Git strategy: ${labelGitStrategy(derivedContract.git_strategy)}`,
    `- Time budget per research round: ${derivedContract.time_budget_hours} hour(s)`,
    '',
    'Default Working Rules',
    '- Keep all durable files inside the project root.',
    '- Prefer reusing existing baseline artifacts before rebuilding them from scratch.',
    baselineSourceMode === 'verify_local_existing'
      ? '- Baseline source mode is local-existing-first: if the user already has local runnable code or a local service with a clear metric path, verify it as the comparator before planning a from-scratch reproduction.'
      : baselineSourceMode === 'attach_registry_baseline'
        ? '- Baseline source mode is registry-first: if a reusable baseline entry exists, attach and verify it before considering full reproduction.'
        : baselineSourceMode === 'reproduce_from_source'
          ? '- Baseline source mode is source-reproduction-first: plan around restoring the comparator from source repos or artifacts unless a stronger local existing route becomes obvious.'
          : baselineSourceMode === 'repair_existing_baseline'
            ? '- Baseline source mode is repair-first: prefer repairing the stale local baseline over restarting from a clean slate.'
            : baselineSourceMode === 'skip_until_blocking'
              ? '- Baseline source mode is skip-until-blocking: do not front-load baseline reproduction unless the missing comparator is actually blocking the next scientific step.'
              : '- Baseline source mode is automatic: choose the lightest trustworthy comparator route from the currently provided baseline sources and local evidence.',
    executionStartMode === 'plan_then_execute'
      ? '- Execution start mode is plan-first: for heavy baseline reproduction, expensive setup, or broad code changes, first produce a bounded step-by-step plan and wait for explicit user approval.'
      : '- Execution start mode is execute-immediately: if the route is already concrete, begin with the smallest useful validating action rather than pausing for a separate approval round.',
    baselineAcceptanceTarget === 'comparison_ready'
      ? '- Baseline acceptance target is comparison-ready: once the comparator is trustworthy enough to unlock the next scientific step, move forward instead of polishing the baseline indefinitely.'
      : baselineAcceptanceTarget === 'paper_repro_ready'
        ? '- Baseline acceptance target is paper-grade reproduction: baseline work may remain primary until the comparator is strong enough to defend in paper-facing writing.'
        : '- Baseline acceptance target is registry-publishable: treat the baseline as incomplete until it is reusable and clean enough to publish as a durable baseline package.',
    normalized.launch_mode === 'custom'
      ? '- Custom launch mode is authoritative here: do not restart from scratch unless the existing state is unusable or misleading.'
      : normalized.standard_profile === 'optimization_task'
        ? '- Standard optimization entry is authoritative here: do not drift into paper writing or default analysis-campaign work unless the user later changes scope.'
        : '- Standard launch mode is active here: use the canonical research graph unless later durable evidence justifies a different entry path.',
    '- Emit explicit milestone updates after each meaningful step.',
    '- Every consequential decision should include reasons, evidence, and the next recommended action.',
    '- If the startup contract already fixes the delivery mode and baseline policy, follow it without asking the user again unless cost, safety, or scope changes materially.',
    normalized.manuscript_edit_mode === 'latex_required'
      ? '- If manuscript edits are required, prefer the provided LaTeX tree as the writing surface; if LaTeX source is unavailable, produce LaTeX-ready replacement text and state the blocker explicitly.'
      : '- If manuscript edits are required, make the section-level deltas explicit and keep the replacement wording copy-ready.',
    normalized.decision_policy === 'autonomous'
      ? '- Autonomous mode is the default contract here: decide the route yourself and continue unless you are requesting explicit completion approval or the cost fork genuinely deserves one short clarification.'
      : '- User-gated mode is enabled here: if local evidence is insufficient for a safe route decision, ask the user with one blocking decision request.',
  ].join('\n')
}

function loadPersistedJson(primaryKey: string, fallbackKeys: string[]) {
  if (typeof window === 'undefined') {
    return null
  }
  for (const storageKey of [primaryKey, ...fallbackKeys]) {
    const raw = window.localStorage.getItem(storageKey)
    if (raw) {
      return raw
    }
  }
  return null
}

export function loadStartResearchTemplate(language: 'en' | 'zh') {
  if (typeof window === 'undefined') {
    return defaultStartResearchTemplate(language)
  }
  try {
    const raw = loadPersistedJson(START_RESEARCH_STORAGE_KEY, LEGACY_START_RESEARCH_STORAGE_KEYS)
    if (!raw) {
      return defaultStartResearchTemplate(language)
    }
    const parsed = JSON.parse(raw) as PersistedStartResearchTemplate
    const base = {
      ...defaultStartResearchTemplate(language),
      ...sanitizeTemplate(parsed),
      quest_id: '',
      user_language: language,
    }
    return {
      ...base,
      quest_id: '',
    }
  } catch {
    return defaultStartResearchTemplate(language)
  }
}

export function saveStartResearchDraft(input: StartResearchTemplate) {
  if (typeof window === 'undefined') {
    return
  }
  window.localStorage.setItem(START_RESEARCH_STORAGE_KEY, JSON.stringify(withoutPersistedQuestId(input)))
}

function languageFromHistory(item: Partial<StartResearchTemplateEntry>): 'en' | 'zh' {
  return item.user_language === 'en' ? 'en' : 'zh'
}

export function loadStartResearchHistory(): StartResearchTemplateEntry[] {
  if (typeof window === 'undefined') {
    return []
  }
  try {
    const raw = loadPersistedJson(START_RESEARCH_HISTORY_KEY, LEGACY_START_RESEARCH_HISTORY_KEYS)
    if (!raw) {
      return []
    }
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) {
      return []
    }
    return parsed
      .filter((item) => item && typeof item === 'object')
      .map((item) => {
        const normalized = sanitizeTemplate({
          ...defaultStartResearchTemplate((item.user_language as 'en' | 'zh') || languageFromHistory(item)),
          ...(item as PersistedStartResearchTemplate),
        })
        return {
          ...item,
          ...normalized,
          quest_id: '',
        } as StartResearchTemplateEntry
      })
      .sort((left, right) => right.updated_at.localeCompare(left.updated_at))
      .slice(0, MAX_TEMPLATE_HISTORY)
  } catch {
    return []
  }
}

export function saveStartResearchTemplate(input: StartResearchTemplate): StartResearchTemplateEntry {
  const normalized = sanitizeTemplate(input)
  const persisted = withoutPersistedQuestId(normalized)
  const persistedEntry: StartResearchTemplateEntry = {
    ...persisted,
    quest_id: '',
    id: stableId(persisted),
    updated_at: new Date().toISOString(),
    compiled_prompt: compileStartResearchPrompt(persisted),
  }
  const savedQuestId = normalized.quest_id
  const next: StartResearchTemplateEntry = {
    ...persistedEntry,
    quest_id: savedQuestId,
    compiled_prompt: compileStartResearchPrompt({
      ...normalized,
      quest_id: savedQuestId,
    }),
  }

  if (typeof window !== 'undefined') {
    saveStartResearchDraft(normalized)
    const current = loadStartResearchHistory().filter((item) => item.id !== persistedEntry.id)
    const merged = [persistedEntry, ...current].slice(0, MAX_TEMPLATE_HISTORY)
    window.localStorage.setItem(START_RESEARCH_HISTORY_KEY, JSON.stringify(merged))
  }

  return next
}
