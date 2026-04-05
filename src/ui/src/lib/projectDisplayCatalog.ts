export type ProjectAccentId = 'graphite' | 'sage' | 'clay' | 'mist' | 'rose'
export type ProjectTemplateId = 'blank' | 'experiment' | 'literature' | 'analysis'
export type ProjectBackgroundStyleId = 'paper' | 'grid' | 'archive' | 'cloud' | 'studio'

export type ProjectAccentOption = {
  id: ProjectAccentId
  label: string
  dotClassName: string
  previewClassName: string
  washClassName: string
}

export type ProjectTemplateOption = {
  id: ProjectTemplateId
  label: string
  description: string
}

export type ProjectBackgroundStyleOption = {
  id: ProjectBackgroundStyleId
  label: string
  description: string
}

export const PROJECT_ACCENT_OPTIONS: ProjectAccentOption[] = [
  {
    id: 'graphite',
    label: 'Graphite',
    dotClassName: 'bg-[#8E8A84]',
    previewClassName: 'from-[#ECE9E3] via-[#E4DED6] to-[#DDD7D0]',
    washClassName: 'bg-[radial-gradient(circle_at_top,rgba(120,118,114,0.2),transparent_62%)]',
  },
  {
    id: 'sage',
    label: 'Sage',
    dotClassName: 'bg-[#8AA18A]',
    previewClassName: 'from-[#EEF2EA] via-[#E6ECE0] to-[#DBE3D5]',
    washClassName: 'bg-[radial-gradient(circle_at_top,rgba(123,149,123,0.22),transparent_62%)]',
  },
  {
    id: 'clay',
    label: 'Clay',
    dotClassName: 'bg-[#C28F73]',
    previewClassName: 'from-[#F4ECE7] via-[#EEDFD6] to-[#E5D0C4]',
    washClassName: 'bg-[radial-gradient(circle_at_top,rgba(192,143,115,0.22),transparent_62%)]',
  },
  {
    id: 'mist',
    label: 'Mist',
    dotClassName: 'bg-[#8CA2B5]',
    previewClassName: 'from-[#EEF2F5] via-[#E4EBF0] to-[#D5E0E8]',
    washClassName: 'bg-[radial-gradient(circle_at_top,rgba(140,162,181,0.22),transparent_62%)]',
  },
  {
    id: 'rose',
    label: 'Rose',
    dotClassName: 'bg-[#C59AA5]',
    previewClassName: 'from-[#F6EEF0] via-[#EEDFE3] to-[#E6D0D6]',
    washClassName: 'bg-[radial-gradient(circle_at_top,rgba(197,154,165,0.22),transparent_62%)]',
  },
]

export const PROJECT_TEMPLATE_OPTIONS: ProjectTemplateOption[] = [
  {
    id: 'blank',
    label: 'Blank workspace',
    description: 'Start with a general research copilot and decide the flow later.',
  },
  {
    id: 'experiment',
    label: 'Experiment board',
    description: 'Best for implementation, debugging, and running experiments from chat.',
  },
  {
    id: 'literature',
    label: 'Literature desk',
    description: 'Best for reading papers, comparing baselines, and collecting notes.',
  },
  {
    id: 'analysis',
    label: 'Analysis deck',
    description: 'Best for digging into logs, results, and follow-up checks.',
  },
]

export const PROJECT_BACKGROUND_STYLE_OPTIONS: ProjectBackgroundStyleOption[] = [
  {
    id: 'paper',
    label: 'Paper',
    description: 'Soft paper tone with quiet depth.',
  },
  {
    id: 'grid',
    label: 'Grid',
    description: 'Light structural grid for organized work.',
  },
  {
    id: 'archive',
    label: 'Archive',
    description: 'Card-catalog feel with calmer desk texture.',
  },
  {
    id: 'cloud',
    label: 'Cloud',
    description: 'Airy layered backdrop with soft atmosphere.',
  },
  {
    id: 'studio',
    label: 'Studio',
    description: 'Cleaner product-panel style surface.',
  },
]

export function resolveProjectAccent(id?: string | null): ProjectAccentOption {
  const normalized = String(id || '').trim().toLowerCase()
  return PROJECT_ACCENT_OPTIONS.find((item) => item.id === normalized) || PROJECT_ACCENT_OPTIONS[0]
}

export function resolveProjectTemplate(id?: string | null): ProjectTemplateOption {
  const normalized = String(id || '').trim().toLowerCase()
  return PROJECT_TEMPLATE_OPTIONS.find((item) => item.id === normalized) || PROJECT_TEMPLATE_OPTIONS[0]
}

export function resolveProjectBackgroundStyle(id?: string | null): ProjectBackgroundStyleOption {
  const normalized = String(id || '').trim().toLowerCase()
  return PROJECT_BACKGROUND_STYLE_OPTIONS.find((item) => item.id === normalized) || PROJECT_BACKGROUND_STYLE_OPTIONS[0]
}

export function resolveProjectDisplay(input?: {
  project_display?: Record<string, unknown> | null
} | null): {
  template: ProjectTemplateId
  accentColor: ProjectAccentId
  backgroundStyle: ProjectBackgroundStyleId
} {
  const projectDisplay =
    input?.project_display && typeof input.project_display === 'object' && !Array.isArray(input.project_display)
      ? input.project_display
      : null
  const template = resolveProjectTemplate(String(projectDisplay?.template || '')).id
  const accentColor = resolveProjectAccent(String(projectDisplay?.accent_color || '')).id
  const backgroundStyle = resolveProjectBackgroundStyle(String(projectDisplay?.background_style || '')).id
  return { template, accentColor, backgroundStyle }
}
