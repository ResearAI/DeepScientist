import { ArrowRight, BookOpen, GraduationCap, Settings2, X } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { Locale } from '@/types'

type ConnectorCoachMode = 'no_enabled' | 'no_target' | 'recommended'

const COPY = {
  en: {
    title: 'Before you start',
    subtitle:
      'Set up an external connector for milestone delivery, or jump into the guided demo first.',
    connector: {
      eyebrow: 'STEP 1',
      title: 'Bind a connector first',
      body: {
        no_enabled:
          'No external connector is enabled yet. It is recommended to configure one first so milestones, replies, and progress can reach you outside the web workspace.',
        no_target:
          'A connector is enabled, but there is no selectable delivery target yet. Open connector settings first, or send one message from the target connector and then come back here.',
        recommended:
          'It is recommended to confirm one default connector target before starting. Then Start Research and later project progress can be delivered to your normal external conversation.',
      },
      cta: {
        no_enabled: 'Open Connector Settings',
        no_target: 'Check Connector Settings',
        recommended: 'Bind Connector',
      },
      note:
        'This reminder appears on entry while no external connector is bound, so you can set delivery up before the first real run.',
    },
    tutorial: {
      eyebrow: 'STEP 2',
      title: 'Play the guided demo',
      body:
        'If you want a safe first pass through the interface, launch the guided demo. It walks through Start Research, Explorer, Canvas, Memory, and Copilot with a staged project.',
      zh: 'Chinese Demo',
      en: 'English Demo',
      skip: 'Skip demo for now',
      never: 'Do not remind again',
    },
    close: 'Close',
  },
  zh: {
    title: '开始之前',
    subtitle: '先配置一个外部连接器，或先播放一次引导演示。',
    connector: {
      eyebrow: '步骤 1',
      title: '先绑定一个连接器',
      body: {
        no_enabled:
          '你现在还没有启用任何外部连接器。建议先配置一个，这样研究过程中的里程碑、回复和进展可以直接发送到网页之外。',
        no_target:
          '你已经启用了连接器，但还没有可选择的投递目标。建议先进入连接器设置页检查配置，或者先在对应连接器中发一条消息，再回来继续。',
        recommended:
          '建议先确认一个默认连接器目标。这样之后“开始研究”和项目运行中的进展都可以直接同步出去。',
      },
      cta: {
        no_enabled: '前往连接器设置',
        no_target: '检查连接器设置',
        recommended: '绑定连接器',
      },
      note:
        '只要还没有绑定外部连接器，这个提醒在进入首页时就会继续出现，方便你在第一次真实运行前先完成投递配置。',
    },
    tutorial: {
      eyebrow: '步骤 2',
      title: '播放首次 Demo',
      body:
        '如果你想先安全地熟悉界面和工作流，可以先进入教程演示。它会一步步带你理解“开始研究”、Explorer、Canvas、Memory 和 Copilot。',
      zh: '中文演示',
      en: '英文演示',
      skip: '暂时跳过演示',
      never: '不再提醒',
    },
    close: '关闭',
  },
} as const

function stepLabel(label: string, fallback: string, showBoth: boolean) {
  if (showBoth) return label
  return fallback
}

export function EntryCoachDialog({
  open,
  locale,
  connectorMode,
  showConnectorStep,
  showTutorialStep,
  onClose,
  onOpenConnectorSettings,
  onSetLanguage,
  onStartTutorial,
  onSkipTutorial,
  onNeverShowTutorial,
}: {
  open: boolean
  locale: Locale
  connectorMode: ConnectorCoachMode
  showConnectorStep: boolean
  showTutorialStep: boolean
  onClose: () => void
  onOpenConnectorSettings: () => void
  onSetLanguage: (language: Locale) => void
  onStartTutorial: (language: 'zh' | 'en') => void
  onSkipTutorial: () => void
  onNeverShowTutorial: () => void
}) {
  if (!open) {
    return null
  }

  const t = COPY[locale]
  const showBoth = showConnectorStep && showTutorialStep

  return (
    <div
      className="fixed inset-0 z-[10010] flex items-center justify-center bg-[rgba(12,14,18,0.48)] p-4 backdrop-blur-md"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-[980px] overflow-hidden rounded-[32px] border border-white/10 bg-[rgba(252,248,242,0.98)] shadow-[0_40px_120px_-52px_rgba(15,23,42,0.62)]"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 border-b border-black/[0.06] px-6 py-5">
          <div className="min-w-0">
            <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[rgba(126,108,82,0.72)]">
              {locale === 'zh' ? '快速开始' : 'Quick Start'}
            </div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight text-[rgba(38,36,33,0.96)]">
              {t.title}
            </h2>
            <div className="mt-2 max-w-2xl text-sm text-[rgba(86,82,77,0.86)]">
              <div className="leading-7">{t.subtitle}</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="inline-flex rounded-full border border-[rgba(126,108,82,0.14)] bg-[rgba(244,239,233,0.84)] p-1">
              <button
                type="button"
                onClick={() => onSetLanguage?.('zh')}
                className={cn(
                  'rounded-full px-3 py-1.5 text-xs font-semibold transition',
                  locale === 'zh'
                    ? 'bg-[#2D2A26] text-white'
                    : 'text-[rgba(86,82,77,0.82)] hover:bg-white'
                )}
              >
                中文
              </button>
              <button
                type="button"
                onClick={() => onSetLanguage?.('en')}
                className={cn(
                  'rounded-full px-3 py-1.5 text-xs font-semibold transition',
                  locale === 'en'
                    ? 'bg-[#2D2A26] text-white'
                    : 'text-[rgba(86,82,77,0.82)] hover:bg-white'
                )}
              >
                English
              </button>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-10 w-10 items-center justify-center rounded-full text-[rgba(107,103,97,0.82)] transition hover:bg-black/[0.04] hover:text-[rgba(38,36,33,0.96)]"
              aria-label={t.close}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div
          className={cn(
            'grid gap-0',
            showBoth ? 'lg:grid-cols-[1.05fr_0.95fr]' : 'grid-cols-1'
          )}
        >
          {showConnectorStep ? (
            <section className="relative overflow-hidden bg-[#23262D] px-6 py-6 text-white lg:px-7 lg:py-7">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(199,173,150,0.16),transparent_48%),radial-gradient(circle_at_bottom_right,rgba(95,117,138,0.18),transparent_44%)]" />
              <div className="relative">
                <div className="inline-flex items-center gap-2 rounded-full border border-white/12 bg-white/6 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-white/74">
                  <Settings2 className="h-3.5 w-3.5" />
                  {stepLabel(t.connector.eyebrow, locale === 'zh' ? '步骤 1' : 'STEP 1', showBoth)}
                </div>
                <h3 className="mt-4 text-2xl font-semibold tracking-tight">
                  {t.connector.title}
                </h3>
                <div className="mt-3 text-sm text-white/82">
                  <div className="leading-7">{t.connector.body[connectorMode]}</div>
                </div>
                <Button
                  type="button"
                  onClick={onOpenConnectorSettings}
                  className="mt-6 h-12 rounded-full bg-[#121419] px-6 text-sm font-semibold text-white shadow-[0_20px_40px_-24px_rgba(0,0,0,0.6)] transition hover:bg-black"
                >
                  {t.connector.cta[connectorMode]}
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
                <div className="mt-4 text-[12px] text-white/60">
                  <div className="leading-6">{t.connector.note}</div>
                </div>
              </div>
            </section>
          ) : null}

          {showTutorialStep ? (
            <section className="px-6 py-6 lg:px-7 lg:py-7">
              <div className="inline-flex items-center gap-2 rounded-full border border-[rgba(126,108,82,0.14)] bg-[rgba(244,239,233,0.72)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[rgba(126,108,82,0.78)]">
                <GraduationCap className="h-3.5 w-3.5" />
                {stepLabel(t.tutorial.eyebrow, locale === 'zh' ? '步骤 1' : 'STEP 1', showBoth)}
              </div>
              <h3 className="mt-4 text-2xl font-semibold tracking-tight text-[rgba(38,36,33,0.96)]">
                {t.tutorial.title}
              </h3>
              <div className="mt-3 text-sm text-[rgba(86,82,77,0.86)]">
                <div className="leading-7">{t.tutorial.body}</div>
              </div>

              <div className="mt-6 grid gap-3 sm:grid-cols-2">
                <button
                  type="button"
                  onClick={() => onStartTutorial('zh')}
                  className="rounded-[20px] border border-[rgba(126,77,42,0.16)] bg-[rgba(244,239,233,0.76)] px-4 py-4 text-left transition hover:border-[rgba(126,77,42,0.28)] hover:bg-white"
                >
                  <div className="flex items-center gap-2 text-sm font-semibold text-[rgba(38,36,33,0.95)]">
                    <BookOpen className="h-4 w-4" />
                    {t.tutorial.zh}
                  </div>
                  <div className="mt-1 text-[12px] leading-6 text-[rgba(86,82,77,0.82)]">
                    {locale === 'zh'
                      ? '一步步熟悉首页、开始研究和项目工作区。'
                      : 'Walk through the landing page, Start Research, and workspace basics.'}
                  </div>
                </button>
                <button
                  type="button"
                  onClick={() => onStartTutorial('en')}
                  className="rounded-[20px] border border-[rgba(126,77,42,0.16)] bg-[rgba(244,239,233,0.76)] px-4 py-4 text-left transition hover:border-[rgba(126,77,42,0.28)] hover:bg-white"
                >
                  <div className="flex items-center gap-2 text-sm font-semibold text-[rgba(38,36,33,0.95)]">
                    <GraduationCap className="h-4 w-4" />
                    {t.tutorial.en}
                  </div>
                  <div className="mt-1 text-[12px] leading-6 text-[rgba(86,82,77,0.82)]">
                    {locale === 'zh'
                      ? '使用英文引导完成同一套首次演示。'
                      : 'Use the same guided flow in English.'}
                  </div>
                </button>
              </div>

              <div className="mt-5 flex flex-col gap-2 sm:flex-row sm:justify-end">
                <Button variant="ghost" onClick={onSkipTutorial}>
                  {t.tutorial.skip}
                </Button>
                <Button variant="secondary" onClick={onNeverShowTutorial}>
                  {t.tutorial.never}
                </Button>
              </div>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  )
}

export default EntryCoachDialog
