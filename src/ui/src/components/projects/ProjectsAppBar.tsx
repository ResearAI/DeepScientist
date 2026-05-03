import { GraduationCap, Languages, Search } from 'lucide-react'
import { NavLink, useLocation } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { SystemUpdateButton } from '@/components/system-update/SystemUpdateButton'
import { assetUrl } from '@/lib/assets'
import { useI18n } from '@/lib/i18n'
import { useOnboardingStore } from '@/lib/stores/onboarding'
import { useThemeStore } from '@/lib/stores/theme'
import { cn } from '@/lib/utils'

export function ProjectsAppBar({
  title,
  subtitle,
  search,
  onSearchChange,
}: {
  title?: string
  subtitle?: string
  search?: string
  onSearchChange?: (value: string) => void
}) {
  const { locale, toggleLocale, t } = useI18n()
  const location = useLocation()
  const restartTutorial = useOnboardingStore((state) => state.restartTutorial)
  const resolvedTheme = useThemeStore((state) => state.resolvedTheme)
  const resolvedTitle = title || t('projectsTitle')
  const resolvedSubtitle = subtitle || (title ? undefined : t('sharedApiHint'))
  const logoSrc = assetUrl(
    resolvedTheme === 'dark' ? 'assets/branding/logo-inverted.svg' : 'assets/branding/logo.svg'
  )

  const navClassName = ({ isActive }: { isActive: boolean }) =>
    cn(
      'rounded-full px-3 py-2 text-sm transition',
      isActive
        ? 'bg-black/[0.06] text-foreground dark:bg-white/[0.08]'
        : 'text-muted-foreground hover:bg-black/[0.04] hover:text-foreground dark:hover:bg-white/[0.06]'
    )

  return (
    <header className="shrink-0">
      <div className="morandi-panel mx-auto flex max-w-[1520px] flex-wrap items-center justify-between gap-3 px-4 py-2.5 sm:flex-nowrap sm:px-5 sm:py-3">
        <div className="relative z-[1] flex min-w-0 items-center gap-3">
          <NavLink
            to="/"
            end
            className="inline-flex min-w-0 items-center gap-2 rounded-full px-2 py-1 transition hover:bg-black/[0.03] dark:hover:bg-white/[0.05]"
          >
            <img src={logoSrc} alt="DeepScientist" className="h-7 w-auto" draggable={false} />
            <span className="hidden text-sm font-semibold tracking-tight sm:inline">{t('brand')}</span>
          </NavLink>

          <div className="hidden h-7 w-px bg-black/10 sm:block dark:bg-white/10" />

          <div className="min-w-0">
            <div className="truncate text-sm font-semibold tracking-tight sm:text-base">{resolvedTitle}</div>
            {resolvedSubtitle ? (
              <div className="hidden truncate text-[11px] text-muted-foreground sm:block">{resolvedSubtitle}</div>
            ) : null}
          </div>
        </div>

        <div className="relative z-[1] flex min-w-0 flex-1 items-center justify-end gap-2 sm:gap-3">
          {onSearchChange ? (
            <div className="relative hidden w-full max-w-md lg:block">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search || ''}
                onChange={(event) => onSearchChange(event.target.value)}
                placeholder={t('searchPlaceholder')}
                className="h-10 rounded-full border-black/[0.08] bg-white/[0.5] pl-10 shadow-none dark:border-white/[0.08] dark:bg-white/[0.04]"
              />
            </div>
          ) : null}

          <nav className="hidden items-center gap-1 md:flex">
            <NavLink to="/" end className={navClassName}>
              {t('navProjects')}
            </NavLink>
            <NavLink to="/docs" className={navClassName}>
              {t('navDocs')}
            </NavLink>
            <NavLink to="/settings" className={navClassName}>
              {t('navSettings')}
            </NavLink>
          </nav>

          <SystemUpdateButton />

          <Button
            variant="outline"
            size="sm"
            onClick={() => restartTutorial(location.pathname || '/', locale === 'zh' ? 'zh' : 'en')}
            className="rounded-full px-2 sm:px-3"
            aria-label={locale === 'zh' ? '教程' : 'Tutorial'}
          >
            <GraduationCap className="h-4 w-4" />
            <span className="hidden sm:inline">{locale === 'zh' ? '教程' : 'Tutorial'}</span>
          </Button>

          <Button variant="secondary" size="sm" onClick={toggleLocale} className="rounded-full">
            <Languages className="h-4 w-4" />
            {locale === 'zh' ? 'English' : '中文'}
          </Button>
        </div>
      </div>
    </header>
  )
}
