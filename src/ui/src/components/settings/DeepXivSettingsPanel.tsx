import { Sparkles } from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { Locale } from "@/types"

import { DeepXivSetupDialog } from "./DeepXivSetupDialog"

const copy = {
  en: {
    title: "DeepXiv",
    eyebrow: "Literature provider",
    summary: "Configure DeepXiv through a short setup flow: register, paste the token, confirm the defaults, and optionally preview a live `transformers` retrieval.",
    start: "Start setup",
  },
  zh: {
    title: "DeepXiv",
    eyebrow: "文献能力提供方",
    summary: "通过一个简短的分步流程完成 DeepXiv 配置：注册、填写 Token、确认默认值，并按需预览一次 `transformers` 的实时检索结果。",
    start: "开始配置",
  },
} satisfies Record<Locale, Record<string, string>>

export function DeepXivSettingsPanel({ locale }: { locale: Locale }) {
  const t = copy[locale]
  const [open, setOpen] = useState(false)

  return (
    <>
      <section className="rounded-[28px] border border-[rgba(45,42,38,0.08)] bg-[linear-gradient(145deg,rgba(253,247,241,0.94),rgba(239,229,220,0.84)_42%,rgba(226,235,239,0.82))] px-6 py-6 shadow-[0_28px_90px_-64px_rgba(44,39,34,0.42)]">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary" className="rounded-full bg-white/80 px-3 py-1 text-[11px] font-semibold text-[#4f4a43]">
            DeepXiv
          </Badge>
          <div className="inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-[#8f8578]">
            <Sparkles className="h-3.5 w-3.5" />
            {t.eyebrow}
          </div>
        </div>
        <div className="mt-3 text-3xl font-semibold tracking-[-0.03em] text-[#2f2b27]">{t.title}</div>
        <div className="mt-2 max-w-[760px] text-sm leading-7 text-[#5d5953]">{t.summary}</div>
        <div className="mt-6">
          <Button className="rounded-full px-6" onClick={() => setOpen(true)}>
            {t.start}
          </Button>
        </div>
      </section>
      <DeepXivSetupDialog open={open} onClose={() => setOpen(false)} locale={locale} />
    </>
  )
}

export default DeepXivSettingsPanel
