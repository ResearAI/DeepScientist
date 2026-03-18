import { assetUrl } from '@/lib/assets'

export type HeroStage = {
  key: string
  title: string
  body: string
  metricPrimary: string
  metricSecondary: string
  icon: string
  tone: 'warm' | 'cool'
}

export type HeroResearchStep = {
  id: string
  title: string
  subtitle: string
  body: string
  tags: string[]
  icon: string
  tone: 'warm' | 'cool'
  terminal: string[]
}

export type HeroFeature = {
  id: string
  kicker: string
  title: string
  body: string
  bullets: string[]
  chips: string[]
  icon: string
  tone: 'warm' | 'cool'
}

export const HERO_STAGES: HeroStage[] = [
  {
    key: 'local',
    title: 'Local Optimum',
    body: 'Establish a reproducible baseline before pushing the frontier.',
    metricPrimary: 'Baseline Value - 1.0x',
    metricSecondary: 'Observations - 24',
    icon: 'BarChart3',
    tone: 'warm',
  },
  {
    key: 'learn',
    title: 'Learn & Adapt',
    body: 'Accumulate experiments and notes to update strategy with evidence.',
    metricPrimary: 'Experiment Cycles - 12',
    metricSecondary: 'Notes Linked - 86',
    icon: 'Brain',
    tone: 'cool',
  },
  {
    key: 'escape',
    title: 'Escape Local',
    body: 'Introduce new hypotheses and evidence to widen the search.',
    metricPrimary: 'Exploration Radius - +32%',
    metricSecondary: 'New Hypotheses - 5',
    icon: 'SparklesIcon',
    tone: 'warm',
  },
  {
    key: 'global',
    title: 'Global Optimum',
    body: 'Converge on the best result and ship reproducible outputs.',
    metricPrimary: 'Insights - +17.3%',
    metricSecondary: 'Reproducibility - High',
    icon: 'Crown',
    tone: 'cool',
  },
]

export const HERO_COPY = {
  headline: 'Automated scientific discovery, driven by autonomous AI research',
  subhead: '',
  tagline: 'Survey / Experiment / Publish',
  primaryCta: 'Start Research',
  secondaryCta: 'List Quest',
  supportLine: 'DeepScientist keeps your full research loop local, reproducible, and continuously moving.',
}

export const HERO_RESEARCH_STEPS: HeroResearchStep[] = [
  {
    id: 'literature',
    title: 'Survey literature',
    subtitle: 'Map the landscape in minutes',
    body: 'Ingest PDFs, extract claims, and highlight contradictions before you design experiments.',
    tags: ['PDF ingestion', 'Citation map', 'Claim index'],
    icon: 'BookOpen',
    tone: 'cool',
    terminal: [
      '> /help',
      '/new     Start a new quest',
      '/config  Edit config',
      '/resume  Resume a session',
      '/model   Show or set model',
      '',
      '> /resume',
      'Session: protein-folding',
      'Step 1/4 Literature survey',
      'Sources indexed: 128',
      'Contradictions flagged: 6',
    ],
  },
  {
    id: 'design',
    title: 'Design experiments',
    subtitle: 'Turn hypotheses into runnable plans',
    body: 'Draft protocols, define controls, and pre-register the metrics before execution.',
    tags: ['Hypothesis grid', 'Protocol draft', 'Risk notes'],
    icon: 'Braces',
    tone: 'warm',
    terminal: [
      '> /config',
      'sync_mode: remote',
      'model: glm-4.6',
      '',
      '> /resume',
      'Step 2/4 Experiment design',
      'Candidate hypotheses: 4',
      'Planned runs: 12',
      'Controls assigned: 3',
    ],
  },
  {
    id: 'execute',
    title: 'Run experiments',
    subtitle: 'Measure, adapt, and accelerate',
    body: 'Launch runs, track live metrics, and widen exploration when gains plateau.',
    tags: ['Queued runs', 'Live metrics', 'Auto notes'],
    icon: 'BarChart3',
    tone: 'cool',
    terminal: [
      '> /resume',
      'Step 3/4 Run experiments',
      'Active runs: 12',
      'Best delta: +8.4%',
      'Next action: widen sweep',
      'Notes linked: 52',
    ],
  },
  {
    id: 'publish',
    title: 'Write and publish',
    subtitle: 'Draft, visualize, and export',
    body: 'Generate figures, assemble the manuscript, and export a reproducible package.',
    tags: ['AutoFigure', 'LaTeX export', 'Repro package'],
    icon: 'File',
    tone: 'warm',
    terminal: [
      '> /resume',
      'Step 4/4 Draft and publish',
      'Figures rendered: 6',
      'Manuscript: results.tex',
      'Export: arxiv-ready.zip',
      'Share link created',
    ],
  },
]

export const HERO_FEATURES: HeroFeature[] = [
  {
    id: 'welcome',
    kicker: 'Welcome + Copilot',
    title: 'Turn a question into a structured research plan',
    body: 'Start fast with guided prompts, then connect the dialogue to your sources and notes.',
    bullets: [
      'Guided prompts for concept, literature, and experiments',
      'Drag and drop PDFs, notebooks, or data tables',
      'Jump back into pinned threads with full context',
    ],
    chips: ['Concept', 'Literature', 'Experiment', 'Analysis'],
    icon: assetUrl('icons/welcome/feature-knowledge.png'),
    tone: 'warm',
  },
  {
    id: 'autofigure',
    kicker: 'AutoFigure',
    title: 'AutoFigure turns papers into editable scientific visuals',
    body: 'Import a paper, draft a layout, iterate with AI, then render and export.',
    bullets: [
      'Draft, iterate, and render in a single workflow',
      'Multiple iterations with a clean final export',
      'Saved to the project file tree automatically',
    ],
    chips: ['Draft', 'Iterate', 'Render'],
    icon: assetUrl('logo.svg'),
    tone: 'cool',
  },
  {
    id: 'workspace',
    kicker: 'Projects / Workspace',
    title: 'One project holds the full research system',
    body: 'Notebook, PDF, LaTeX, code, and collaboration stay unified from start to finish.',
    bullets: [
      'Unified file tree',
      'Multi-plugin workflow (Notebook / AutoFigure / PDF / Copilot)',
      'Shareable and reproducible by default',
    ],
    chips: ['Notebook', 'PDF', 'LaTeX', 'Copilot'],
    icon: assetUrl('icons/FolderIcon.png'),
    tone: 'warm',
  },
]

export const HERO_TERMINAL_INTRO = ['# Autonomous research loop', 'Type /help for commands.', '']
