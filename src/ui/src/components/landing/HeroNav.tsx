'use client'

import Link from 'next/link'
import { BookOpen, GraduationCap, Languages, Settings2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SystemUpdateButton } from '@/components/system-update/SystemUpdateButton'
import { BRAND_LOGO_SMALL_SRC } from '@/lib/constants/assets'
import { useI18n } from '@/lib/i18n'
import { useOnboardingStore } from '@/lib/stores/onboarding'
import { cn } from '@/lib/utils'
import { LocalAuthTokenButton } from './LocalAuthTokenButton'

export default function HeroNav() {
  const { locale, toggleLocale, t } = useI18n()
  const restartTutorial = useOnboardingStore((state) => state.restartTutorial)
  const openChooser = useOnboardingStore((state) => state.openChooser)

  return (
    <header
      className={cn(
        'sticky top-0 z-50 w-full overflow-visible py-2 [padding-top:calc(env(safe-area-inset-top,0px)+0.5rem)]',
        'border-b border-black/5 bg-white/60 backdrop-blur-xl',
        'supports-[backdrop-filter]:bg-white/40'
      )}
    >
      <div className="mx-auto flex min-h-16 w-full max-w-[90vw] items-center justify-between gap-4 px-6">
        <Link
          href="/"
          className="flex items-center gap-2 rounded-full px-2 py-1 transition-colors hover:bg-black/[0.03]"
          aria-label="DeepScientist"
        >
          <img
            src={BRAND_LOGO_SMALL_SRC}
            alt="DeepScientist"
            width={28}
            height={28}
            className="object-contain"
            loading="eager"
            fetchPriority="high"
            decoding="async"
            draggable={false}
          />
          <span className="text-sm font-semibold tracking-tight text-[#2D2A26]">
            DeepScientist
          </span>
        </Link>

        <div className="flex items-center gap-2">
          <SystemUpdateButton />
          <LocalAuthTokenButton />
          <Button
            variant="outline"
            size="sm"
            className="h-9 rounded-full border-black/10 bg-white/60 text-[#2D2A26] hover:bg-white/90"
            onClick={toggleLocale}
          >
            <Languages className="mr-2 h-4 w-4" />
            {locale === 'zh' ? 'English' : '中文'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="hidden h-9 rounded-full border-black/10 bg-white/60 text-[#2D2A26] hover:bg-white/90 sm:inline-flex"
            onClick={() => {
              const nextLanguage = locale === 'zh' ? 'zh' : 'en'
              restartTutorial('/', nextLanguage)
            }}
            data-onboarding-id="landing-replay-tutorial"
          >
            <GraduationCap className="mr-2 h-4 w-4" />
            {locale === 'zh' ? '教程' : 'Tutorial'}
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="h-9 rounded-full border-black/10 bg-white/60 text-[#2D2A26] hover:bg-white/90"
            asChild
          >
            <Link href="/docs">
              <BookOpen className="mr-2 h-4 w-4" />
              {t('navDocs')}
            </Link>
          </Button>
          <Button
            size="sm"
            className="h-9 rounded-full bg-[#C7AD96] text-[#2D2A26] hover:bg-[#D7C6AE]"
            asChild
          >
            <Link href="/settings">
              <Settings2 className="mr-2 h-4 w-4" />
              {t('navSettings')}
            </Link>
          </Button>
        </div>
      </div>
    </header>
  )
}
