import type { ConnectorAvailabilitySnapshot } from '@/types'

export type ResearchScope = 'baseline_only' | 'baseline_plus_direction' | 'full_research'
export type BaselineMode =
  | 'existing'
  | 'restore_from_url'
  | 'allow_degraded_minimal_reproduction'
  | 'stop_if_insufficient'
export type ResourcePolicy = 'conservative' | 'balanced' | 'aggressive'
export type GitStrategy =
  | 'branch_per_analysis_then_paper'
  | 'semantic_head_plus_controlled_integration'
  | 'manual_integration_only'
export type ResearchIntensity = 'light' | 'balanced' | 'sprint'
export type DecisionPolicy = 'autonomous' | 'user_gated'
export type LaunchMode = 'standard' | 'custom'
export type CustomProfile = 'continue_existing_state' | 'revision_rebuttal' | 'freeform'

export type StartResearchTemplate = {
  title: string
  quest_id: string
  goal: string
  baseline_id: string
  baseline_variant_id: string
  baseline_urls: string
  paper_urls: string
  runtime_constraints: string
  objectives: string
  need_research_paper: boolean
  research_intensity: ResearchIntensity
  decision_policy: DecisionPolicy
  launch_mode: LaunchMode
  custom_profile: CustomProfile
  entry_state_summary: string
  review_summary: string
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
      baseline_mode: 'restore_from_url',
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
    baseline_urls: '',
    paper_urls: '',
    runtime_constraints: '',
    objectives: '',
    need_research_paper: true,
    research_intensity: 'balanced',
    decision_policy: 'autonomous',
    launch_mode: 'standard',
    custom_profile: 'freeform',
    entry_state_summary: '',
    review_summary: '',
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

export function listReferenceStartResearchTemplates(): StartResearchTemplateEntry[] {
  const timestamp = '2026-03-17T00:00:00.000Z'
  const zhTemplate: StartResearchTemplate = {
    title: '示例 · 在指定 Qwen 端点上复现 P-and-B 并探索更优的 token 控制',
    quest_id: '',
    goal: [
      '请复现 P-and-B（Planning and Budgeting）论文与官方仓库中的核心 baseline，并在严格保持评测任务一致的前提下，继续探索更高质量、更省 token、且具有学术洞见的改进方向。',
      '',
      '本课题默认使用用户指定的单一推理接口与单一模型：`http://127.0.0.1:8004/v1`、API key `1234`、模型 `/model/Qwen3.5-35B-A3B`（实验中记录为 `Qwen3.5-35B-A3B`）。不需要横向测试其他模型，而是围绕这一固定端点完成 baseline 复现、分析与改进。',
      '',
      '要求先完整恢复并验证官方 baseline，再沿着文献调研与实验结果提出新方向。所有新 idea 都必须建立在充分的相关工作阅读、对失败模式的分析，以及对当前最佳 baseline 的清晰理解之上。',
      '',
      '研究目标不是只得到一个更高分结果，而是形成一项适合作为论文工作的研究成果：结论需要可靠，洞见需要明确，结果需要能解释为什么有效、何时有效、何时无效。',
    ].join('\n'),
    baseline_id: '',
    baseline_variant_id: '',
    baseline_urls: 'https://github.com/junhongmit/P-and-B',
    paper_urls: 'https://arxiv.org/abs/2505.16122',
    runtime_constraints: [
      '- 推理接口 base URL 固定为 `http://127.0.0.1:8004/v1`。',
      '- API key 固定为 `1234`。',
      '- 模型固定为 `/model/Qwen3.5-35B-A3B`，在实验记录中统一写作 `Qwen3.5-35B-A3B`。',
      '- 只围绕这一组 endpoint + key + model 完成研究；不要横向测试其他模型。',
      '- `max_tokens`、任务定义与主要评测协议默认保持官方设置；只有在明确证据表明当前上限不够时，才允许做最小幅度调整并记录原因。',
      '- 最大并发数量按 `96` 设计，可以使用最多 `96` 个并发 worker / 异步请求；如需调整并发、超时或重试逻辑，必须记录原因。',
      '- 在不破坏服务稳定性的前提下，尽量占满 API 服务器吞吐。',
      '- 除非有充分证据证明必须调整，否则优先保持官方 baseline 的任务定义、主要超参数与评测协议不变。',
      '- 不允许伪造实验结果；失败、异常、中断和退化结果都必须如实记录。',
    ].join('\n'),
    objectives: [
      '1. 恢复并验证官方 baseline，形成可复用的可信起点。',
      '2. 在固定的 Qwen3.5-35B-A3B 端点上记录关键指标、token 开销、长尾失败模式与主要观察结论。',
      '3. 基于文献与实验结果提出至少一个有研究价值的改进方向。',
      '4. 形成足以支持论文写作的实验与分析材料。',
    ].join('\n'),
    need_research_paper: true,
    research_intensity: 'balanced',
    decision_policy: 'autonomous',
    launch_mode: 'standard',
    custom_profile: 'freeform',
    entry_state_summary: '',
    review_summary: '',
    custom_brief: '',
    user_language: 'zh',
  }

  const enTemplate: StartResearchTemplate = {
    title: 'Example · Reproduce P-and-B on the specified Qwen endpoint and explore better token control',
    quest_id: '',
    goal: [
      'Please reproduce the core baselines from the P-and-B (Planning and Budgeting) paper and official repository, then continue exploring stronger and more token-efficient reasoning-control ideas while keeping the task definition and evaluation protocol faithful to the original work.',
      '',
      'This project assumes one fixed inference setup from the start: base URL `http://127.0.0.1:8004/v1`, API key `1234`, and model `/model/Qwen3.5-35B-A3B` (record experiment results as `Qwen3.5-35B-A3B`). Do not broaden into multi-model benchmarking; the task is to understand and improve the method on this designated endpoint.',
      '',
      'The workflow should first restore and verify the official baselines, then move into literature-grounded idea generation and evidence-driven experimentation. Every new idea must be justified by careful reading of related work, analysis of failure modes, and a clear understanding of the current best baseline.',
      '',
      'The goal is not merely to obtain one better score, but to produce a paper-worthy research result: the claims must be reliable, the insights must be explicit, and the evidence must explain why the method helps, when it helps, and where it breaks.',
    ].join('\n'),
    baseline_id: '',
    baseline_variant_id: '',
    baseline_urls: 'https://github.com/junhongmit/P-and-B',
    paper_urls: 'https://arxiv.org/abs/2505.16122',
    runtime_constraints: [
      '- Fix the inference base URL to `http://127.0.0.1:8004/v1`.',
      '- Fix the API key to `1234`.',
      '- Fix the model to `/model/Qwen3.5-35B-A3B`, and normalize experiment records to `Qwen3.5-35B-A3B`.',
      '- Use only this endpoint + key + model combination; do not turn the project into a multi-model benchmark.',
      '- Keep `max_tokens`, task definition, and the main evaluation protocol aligned with the official setup unless there is concrete evidence that the token cap itself is blocking valid runs; if changed, record the reason explicitly.',
      '- Design for up to `96` concurrent workers / async requests; if concurrency, timeout, or retry settings are changed, record the reason explicitly.',
      '- Keep throughput high without destabilizing the service, and try to saturate the available API capacity safely.',
      '- Preserve the official task setup, major hyperparameters, and evaluation protocol unless there is concrete evidence that an adaptation is necessary.',
      '- Never fabricate results; failed, interrupted, degraded, or inconclusive runs must be recorded honestly.',
    ].join('\n'),
    objectives: [
      '1. Restore and verify the official baseline as a trustworthy reusable starting point.',
      '2. On the fixed Qwen3.5-35B-A3B endpoint, record key metrics, token costs, long-tail failure modes, and main observations.',
      '3. Propose at least one research-worthy improvement direction grounded in literature and experimental evidence.',
      '4. Produce experiment and analysis assets that are strong enough to support paper writing.',
    ].join('\n'),
    need_research_paper: true,
    research_intensity: 'balanced',
    decision_policy: 'autonomous',
    launch_mode: 'standard',
    custom_profile: 'freeform',
    entry_state_summary: '',
    review_summary: '',
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

function sanitizeCustomProfile(value: unknown): CustomProfile {
  const normalized = String(value || '').trim().toLowerCase()
  if (
    normalized === 'continue_existing_state' ||
    normalized === 'revision_rebuttal' ||
    normalized === 'freeform'
  ) {
    return normalized
  }
  return 'freeform'
}

function sanitizeLines(text: string) {
  return text
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

export function resolveStartResearchContractFields(
  input: Pick<StartResearchTemplate, 'research_intensity' | 'baseline_id'>
): StartResearchContractFields {
  const intensity = sanitizeResearchIntensity(input.research_intensity, input)
  const resolved = {
    ...START_RESEARCH_INTENSITY_PRESETS[intensity].contract,
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
    baseline_urls: String(input.baseline_urls || '').trim(),
    paper_urls: String(input.paper_urls || '').trim(),
    runtime_constraints: String(input.runtime_constraints || '').trim(),
    objectives: String(input.objectives || '').trim(),
    need_research_paper: input.need_research_paper !== false,
    research_intensity: sanitizeResearchIntensity(input.research_intensity, input),
    decision_policy: sanitizeDecisionPolicy(input.decision_policy),
    launch_mode: sanitizeLaunchMode(input.launch_mode),
    custom_profile: sanitizeCustomProfile(input.custom_profile),
    entry_state_summary: String(input.entry_state_summary || '').trim(),
    review_summary: String(input.review_summary || '').trim(),
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

function labelCustomProfile(value: CustomProfile) {
  switch (value) {
    case 'continue_existing_state':
      return 'Continue existing state: audit and normalize an existing baseline, result, draft, or mixed project state before deciding the next anchor.'
    case 'revision_rebuttal':
      return 'Revision / rebuttal: treat the current paper and reviewer package as the active contract, then route supplementary experiments and manuscript edits from that state.'
    default:
      return 'Freeform: follow the user-defined custom brief and open only the skills actually needed.'
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
      '- The project should normally continue through baseline, literature-grounded idea selection, implementation, main experiments, necessary analysis, paper outline, drafting, revision, and paper bundle preparation.',
      '- Do not stop after obtaining only one improved algorithm or one promising run.',
      '- After each `artifact.record_main_experiment(...)`, first interpret the measured result, then decide whether to improve further, run necessary follow-up analysis, or move into writing.',
      '- The idea stage only creates or revises a candidate direction; the round is not complete until a main experiment result is recorded and routed.',
      '- Unless the user explicitly changes scope, do not terminate the project before at least one paper-like deliverable exists.',
    ]
  }
  return [
    '- A research paper is NOT required for this project.',
    '- The primary goal is the strongest justified algorithmic result, not paper drafting or paper packaging.',
    '- The project must still do rigorous baseline work, literature-grounded idea selection, implementation, and main experiments.',
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
    '- Do not hand ordinary route, branch, cost, baseline-reuse, or experiment-selection decisions back to the user.',
    '- Report chosen routes through threaded progress or milestone updates, and keep moving unless you are explicitly requesting final completion approval.',
  ]
}

function customLaunchLines(input: StartResearchTemplate) {
  const normalized = sanitizeTemplate(input)
  if (normalized.launch_mode !== 'custom') {
    return [
      '- Standard launch mode is active.',
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
  if (normalized.review_summary) {
    lines.push('- Review / revision summary:', normalized.review_summary)
  }
  if (normalized.custom_brief) {
    lines.push('- Custom brief:', normalized.custom_brief)
  }
  if (normalized.custom_profile === 'continue_existing_state') {
    lines.push('- First action: audit and trust-rank existing baselines, results, drafts, or review assets before rerunning expensive work.')
    lines.push('- Prefer `intake-audit` first if the starting state is not already normalized.')
  } else if (normalized.custom_profile === 'revision_rebuttal') {
    lines.push('- First action: interpret reviewer comments and current paper state before ordinary writing or fresh ideation.')
    lines.push('- Prefer `rebuttal` first, and route supplementary runs only when a reviewer issue genuinely requires them.')
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
  const baselineContext = normalized.baseline_id
    ? `Runtime will attach and confirm baseline_id ${normalized.baseline_id}${baselineVariant ? ` (variant ${baselineVariant})` : ''} before the project starts. Treat it as the pre-bound baseline unless you find a concrete incompatibility, corruption, or missing-evidence problem.`
    : baselineUrls.length > 0
      ? baselineUrls.map((url) => `- ${url}`).join('\n')
      : 'No baseline link has been attached yet. The first obligation is to discover, repair, or reconstruct a reusable baseline.'
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
    'Reference Papers / Repositories',
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
    `- Research intensity: ${labelResearchIntensity(normalized.research_intensity)}`,
    `- Decision policy: ${labelDecisionPolicy(normalized.decision_policy)}`,
    `- Research paper required: ${normalized.need_research_paper ? 'Yes' : 'No; optimize for the strongest justified algorithmic result.'}`,
    `- Scope: ${labelScope(derivedContract.scope)}`,
    `- Baseline policy: ${labelBaselineMode(derivedContract.baseline_mode)}`,
    `- Resource policy: ${labelResourcePolicy(derivedContract.resource_policy)}`,
    `- Git strategy: ${labelGitStrategy(derivedContract.git_strategy)}`,
    `- Time budget per research round: ${derivedContract.time_budget_hours} hour(s)`,
    '',
    'Mandatory Working Rules',
    '- Keep all durable files inside the project root.',
    '- Reuse existing baseline artifacts whenever possible before rebuilding them.',
    normalized.launch_mode === 'custom'
      ? '- Custom launch mode is authoritative here: do not restart from scratch unless the existing state is unusable or misleading.'
      : '- Standard launch mode is active here: use the canonical research graph unless later durable evidence justifies a different entry path.',
    '- Emit explicit milestone updates after each meaningful step.',
    '- Every decision must include reasons, evidence, and the next recommended action.',
    '- If the startup contract already fixes the delivery mode and baseline policy, follow it without asking the user again unless cost, safety, or scope changes materially.',
    normalized.decision_policy === 'autonomous'
      ? '- Autonomous mode is the default contract here: decide the route yourself and continue unless you are requesting explicit completion approval.'
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
