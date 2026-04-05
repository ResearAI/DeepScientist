'use client'

import React from 'react'
import { KeyRound } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { copyToClipboard } from '@/lib/clipboard'
import { useI18n } from '@/lib/i18n'
import { useBrowserAuth } from '@/components/auth/AuthProvider'

function copyBundle(locale: 'en' | 'zh') {
  if (locale === 'zh') {
    return {
      button: '密码',
      title: '本地访问密码',
      subtitle: '这个密码保存在当前浏览器中，用于访问本地 DeepScientist daemon。',
      copy: '复制',
      copied: '已复制',
      unavailable: '暂时无法读取密码。',
      loading: '正在读取…',
    }
  }
  return {
    button: 'Password',
    title: 'Local Access Password',
    subtitle: 'This password is stored in the current browser and unlocks the local DeepScientist daemon.',
    copy: 'Copy',
    copied: 'Copied',
    unavailable: 'The password is unavailable right now.',
    loading: 'Loading…',
  }
}

export function LocalAuthTokenButton() {
  const { locale } = useI18n()
  const { enabled, authenticated, revealToken } = useBrowserAuth()
  const copy = React.useMemo(() => copyBundle(locale), [locale])
  const [open, setOpen] = React.useState(false)
  const [token, setToken] = React.useState<string | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [copied, setCopied] = React.useState(false)

  const openDialog = React.useCallback(async () => {
    setOpen(true)
    setCopied(false)
    setError(null)
    setLoading(true)
    try {
      const resolved = await revealToken()
      setToken(resolved)
      if (!resolved) {
        setError(copy.unavailable)
      }
    } catch {
      setError(copy.unavailable)
    } finally {
      setLoading(false)
    }
  }, [copy.unavailable, revealToken])

  if (!enabled || !authenticated) {
    return null
  }

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="h-9 rounded-full border-black/10 bg-white/60 text-[#2D2A26] hover:bg-white/90"
        onClick={() => {
          void openDialog()
        }}
      >
        <KeyRound className="mr-2 h-4 w-4" />
        {copy.button}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md border-black/10 bg-[#F6F1E8] text-[#2D2A26]">
          <DialogHeader className="space-y-3 text-left">
            <DialogTitle className="text-[20px] font-semibold text-[#2D2A26]">{copy.title}</DialogTitle>
            <DialogDescription className="text-sm leading-6 text-[#5D5A55]">{copy.subtitle}</DialogDescription>
          </DialogHeader>
          <div className="rounded-2xl border border-black/10 bg-white/75 px-4 py-3 font-mono text-sm text-[#2D2A26]">
            {loading ? copy.loading : token || error || copy.unavailable}
          </div>
          <DialogFooter className="mt-2 gap-2 sm:justify-end">
            <Button
              variant="outline"
              className="rounded-full border-black/10"
              disabled={!token}
              onClick={() => {
                if (!token) return
                void copyToClipboard(token).then((ok) => setCopied(ok))
              }}
            >
              {copied ? copy.copied : copy.copy}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
