import { FolderOpen, Loader2, Plus } from 'lucide-react'
import * as React from 'react'
import { useNavigate } from 'react-router-dom'

import { ExperimentLaunchModeDialog } from '@/components/projects/ExperimentLaunchModeDialog'
import { ProjectDisplayPreviewCard } from '@/components/projects/ProjectDisplayPreviewCard'
import { Button } from '@/components/ui/button'
import { listProjects, type Project } from '@/lib/api/projects'
import { resolveProjectDisplay, resolveProjectTemplate } from '@/lib/projectDisplayCatalog'

const copy = {
  en: {
    eyebrow: 'Projects',
    title: 'All research workspaces',
    body: 'Open an existing quest, or start a new Copilot or autonomous experiment from here.',
    create: 'Start Experiment',
    empty: 'No project yet. Start your first experiment to create a workspace.',
    updated: 'Updated',
  },
  zh: {
    eyebrow: 'Projects',
    title: '全部科研工作区',
    body: '你可以从这里打开已有 quest，或者开始一个新的 Copilot / 全自动实验。',
    create: 'Start Experiment',
    empty: '还没有项目。开始你的第一个实验后，这里就会出现工作区。',
    updated: '更新于',
  },
} as const

function formatUpdatedAt(value?: string | null, locale: 'en' | 'zh' = 'en') {
  if (!value) return ''
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat(locale === 'zh' ? 'zh-CN' : 'en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed)
}

export function ProjectsPage() {
  const navigate = useNavigate()
  const locale =
    (typeof navigator !== 'undefined' ? navigator.language : 'en').toLowerCase().startsWith('zh') ? 'zh' : 'en'
  const t = copy[locale]
  const [items, setItems] = React.useState<Project[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [launchOpen, setLaunchOpen] = React.useState(false)

  React.useEffect(() => {
    let active = true
    void listProjects()
      .then((payload) => {
        if (!active) return
        setItems(payload.items || [])
        setError(null)
      })
      .catch((caught) => {
        if (!active) return
        setError(caught instanceof Error ? caught.message : 'Failed to load projects.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [])

  return (
    <div className="min-h-screen bg-[#F5F2EC] font-project text-[#2D2A26]">
      <div
        className="min-h-screen px-6 py-8"
        style={{
          backgroundImage:
            'radial-gradient(960px circle at 10% 10%, rgba(214, 198, 182, 0.36), transparent 58%), radial-gradient(820px circle at 90% 0%, rgba(158, 178, 194, 0.28), transparent 52%), linear-gradient(180deg, #F7F3ED 0%, #EFE9E0 100%)',
        }}
      >
        <div className="mx-auto max-w-7xl">
          <div className="flex flex-wrap items-end justify-between gap-4 pb-8">
            <div>
              <div className="text-xs uppercase tracking-[0.22em] text-[#8A8278]">{t.eyebrow}</div>
              <h1 className="mt-2 text-3xl font-semibold tracking-[-0.03em]">{t.title}</h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-[#5D5A55]">{t.body}</p>
            </div>
            <Button
              className="h-11 rounded-full bg-[#C7AD96] px-5 text-[#2D2A26] hover:bg-[#D7C6AE]"
              onClick={() => setLaunchOpen(true)}
            >
              <Plus className="mr-2 h-4 w-4" />
              {t.create}
            </Button>
          </div>

          {loading ? (
            <div className="flex min-h-[40vh] items-center justify-center gap-3 text-sm text-[#5D5A55]">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading…
            </div>
          ) : error ? (
            <div className="rounded-[28px] border border-rose-400/25 bg-rose-50/80 px-5 py-4 text-sm text-rose-700">
              {error}
            </div>
          ) : items.length === 0 ? (
            <div className="rounded-[32px] border border-dashed border-black/12 bg-white/55 px-6 py-16 text-center text-sm leading-6 text-[#5D5A55]">
              {t.empty}
            </div>
          ) : (
            <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
              {items.map((item) => {
                const settings = item.settings && typeof item.settings === 'object' ? item.settings : {}
                const projectDisplayInput =
                  settings && typeof settings === 'object' && 'project_display' in settings
                    ? { project_display: (settings as Record<string, unknown>).project_display as Record<string, unknown> | null }
                    : null
                const display = resolveProjectDisplay(projectDisplayInput)
                const templateMeta = resolveProjectTemplate(display.template)
                const workspaceMode = String((settings as Record<string, unknown>).workspace_mode || '').trim().toLowerCase()
                const modeLabel = workspaceMode === 'copilot' ? 'Copilot' : 'Auto'
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => navigate(`/projects/${item.id}`)}
                    className="text-left"
                  >
                    <ProjectDisplayPreviewCard
                      title={item.name}
                      subtitle={item.description || ''}
                      template={display.template}
                      accentColor={display.accentColor}
                      backgroundStyle={display.backgroundStyle}
                      meta={`${t.updated} ${formatUpdatedAt(item.updated_at, locale)}`}
                      modeLabel={modeLabel}
                      className="h-full transition duration-300 hover:-translate-y-1"
                    />
                    <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-[#5D5A55]">
                      <div className="inline-flex items-center gap-2">
                        <FolderOpen className="h-4 w-4" />
                        {item.id}
                      </div>
                      <div className="rounded-full border border-black/10 bg-white/72 px-3 py-1 text-[11px] font-medium text-[#5D5A55]">
                        {templateMeta.label}
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </div>

      <ExperimentLaunchModeDialog
        open={launchOpen}
        locale={locale}
        onClose={() => setLaunchOpen(false)}
        onSelectMode={(mode) => {
          setLaunchOpen(false)
          navigate(mode === 'copilot' ? '/projects/new/copilot' : '/projects/new/auto')
        }}
      />
    </div>
  )
}

export default ProjectsPage
