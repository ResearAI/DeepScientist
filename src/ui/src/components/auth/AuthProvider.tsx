'use client'

import React from 'react'
import { BookOpen, FolderOpen, Languages, Settings2 } from 'lucide-react'
import { useReducedMotion } from 'framer-motion'

import HeroScene from '@/components/landing/HeroScene'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { BRAND_LOGO_SMALL_SRC } from '@/lib/constants/assets'
import { useMobileViewport } from '@/lib/hooks/useMobileViewport'
import {
  clearBrowserAuthTokenFromLocation,
  fetchBrowserAuthToken,
  readStoredBrowserAuthToken,
  readUrlBrowserAuthToken,
  runtimeAuthConfig,
  storeBrowserAuthToken,
} from '@/lib/auth'
import { useI18n } from '@/lib/i18n'
import { getHeroBundle } from '@/components/landing/hero-content'

type AuthContextValue = {
  enabled: boolean
  authenticated: boolean
  token: string | null
  revealToken: () => Promise<string | null>
}

const AuthContext = React.createContext<AuthContextValue>({
  enabled: false,
  authenticated: true,
  token: null,
  revealToken: async () => null,
})

type AuthCopy = {
  title: string
  subtitle: string
  placeholder: string
  submit: string
  loading: string
  invalid: string
  unavailable: string
  helperTitle: string
  helperViewToken: string
  helperDisableAuth: string
  backgroundEyebrow: string
  backgroundTitle: string
  backgroundBody: string
}

function authCopy(locale: 'en' | 'zh'): AuthCopy {
  if (locale === 'zh') {
    return {
      title: '输入本地访问密码',
      subtitle: 'DeepScientist 已启用本地密码模式。输入启动时生成的 16 位密码后才能继续使用。',
      placeholder: '请输入 16 位密码',
      submit: '继续',
      loading: '正在验证本地访问权限…',
      invalid: '密码不正确，请重试。',
      unavailable: '当前无法连接本地 daemon，请确认 `ds` 正在运行。',
      helperTitle: '如何查看或关闭密码',
      helperViewToken: '查看密码：回到启动 `ds` 的终端输出，或执行 `ds --status`。',
      helperDisableAuth: '关闭密码：重新启动时使用 `ds --auth false`。',
      backgroundEyebrow: '本地优先科研工作区',
      backgroundTitle: 'DeepScientist 会先锁住本地入口，再继续打开研究工作区。',
      backgroundBody: '输入本次启动生成的本地访问密码后，首页、项目列表和工作区才会继续加载。',
    }
  }
  return {
    title: 'Enter the Local Access Password',
    subtitle: 'DeepScientist is running in local password mode. Enter the generated 16-character password to continue.',
    placeholder: 'Enter the 16-character password',
    submit: 'Continue',
    loading: 'Checking local access…',
    invalid: 'The password is not valid.',
    unavailable: 'The local daemon is unavailable. Confirm that `ds` is running.',
    helperTitle: 'How to view or disable the password',
    helperViewToken: 'View the password in the terminal where `ds` was started, or run `ds --status`.',
    helperDisableAuth: 'Disable the password on the next launch with `ds --auth false`.',
    backgroundEyebrow: 'Local-first research workspace',
    backgroundTitle: 'DeepScientist locks the local browser entry before opening the research workspace.',
    backgroundBody: 'Enter the password generated for this launch, then the landing page, quest list, and workspace will continue to load.',
  }
}

async function probeAuth(candidateToken?: string | null) {
  const headers: Record<string, string> = {}
  const normalized = typeof candidateToken === 'string' ? candidateToken.trim() : ''
  if (normalized) {
    headers.Authorization = `Bearer ${normalized}`
  }
  const response = await fetch('/api/health', {
    headers,
    cache: 'no-store',
  })
  if (response.ok) {
    return true
  }
  if (response.status === 401) {
    return false
  }
  throw new Error(`HTTP ${response.status}`)
}

function AuthLockScreen(props: {
  copy: AuthCopy
  locale: 'en' | 'zh'
  initialValue: string
  error: string | null
  onToggleLocale: () => void
  onSubmit: (token: string) => Promise<void>
}) {
  const [token, setToken] = React.useState(props.initialValue)
  const [submitting, setSubmitting] = React.useState(false)
  const hero = React.useMemo(() => getHeroBundle(props.locale), [props.locale])
  const prefersReducedMotion = useReducedMotion()
  const reducedMotion = prefersReducedMotion ?? false
  const isCompact = useMobileViewport()

  const handleSubmit = React.useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault()
      if (!token.trim() || submitting) {
        return
      }
      setSubmitting(true)
      try {
        await props.onSubmit(token)
      } finally {
        setSubmitting(false)
      }
    },
    [props, submitting, token]
  )

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#F5F2EC] text-[#2D2A26]">
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            'radial-gradient(900px circle at 15% 15%, rgba(185, 199, 214, 0.28), transparent 60%), radial-gradient(700px circle at 85% 0%, rgba(215, 198, 174, 0.32), transparent 58%), linear-gradient(180deg, #F5F2EC 0%, #EEE7DD 60%, #F5F2EC 100%)',
        }}
      />
      <div className="absolute inset-0 bg-white/10" />

      <div className="relative z-10 min-h-screen pointer-events-none">
        <header className="border-b border-black/5 bg-white/50 backdrop-blur-xl">
          <div className="mx-auto flex min-h-16 w-full max-w-[90vw] items-center justify-between gap-4 px-6 py-2">
            <div className="flex items-center gap-2 rounded-full px-2 py-1">
              <img
                src={BRAND_LOGO_SMALL_SRC}
                alt="DeepScientist"
                width={28}
                height={28}
                className="object-contain"
                draggable={false}
              />
              <span className="text-sm font-semibold tracking-tight text-[#2D2A26]">DeepScientist</span>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled
                className="h-9 rounded-full border-black/10 bg-white/60 text-[#2D2A26]/80 opacity-100"
                onClick={props.onToggleLocale}
              >
                <Languages className="mr-2 h-4 w-4" />
                {props.locale === 'zh' ? 'English' : '中文'}
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled
                className="hidden h-9 rounded-full border-black/10 bg-white/60 text-[#2D2A26]/80 opacity-100 sm:inline-flex"
              >
                <BookOpen className="mr-2 h-4 w-4" />
                Docs
              </Button>
              <Button
                size="sm"
                disabled
                className="h-9 rounded-full bg-[#C7AD96]/85 text-[#2D2A26]/85 opacity-100"
              >
                <Settings2 className="mr-2 h-4 w-4" />
                Settings
              </Button>
            </div>
          </div>
        </header>

        <section className="relative min-h-[calc(100vh-4.5rem)]">
          <div className="mx-auto grid min-h-[calc(100vh-4.5rem)] w-full max-w-[90vw] items-start gap-12 px-6 pb-16 pt-10 lg:grid-cols-[0.9fr_1.6fr] lg:pb-24">
            <div className="min-w-0 space-y-6">
              <div className="inline-flex items-center gap-2 rounded-full border border-black/10 bg-white/60 px-3 py-1 text-xs uppercase tracking-[0.2em] text-[#7E8B97]">
                {props.copy.backgroundEyebrow}
              </div>
              <div className="space-y-4">
                <h1 className="max-w-2xl text-4xl font-semibold leading-tight md:text-5xl">
                  {hero.copy.headline}
                </h1>
                <p className="max-w-xl text-base leading-7 text-[#5D5A55]">{props.copy.backgroundBody}</p>
                <div className="text-sm uppercase tracking-[0.22em] text-[#9FB1C2]">{hero.copy.tagline}</div>
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <Button className="h-12 rounded-full bg-[#C7AD96] px-7 text-[#2D2A26] shadow-[0_12px_28px_-14px_rgba(45,42,38,0.55)]">
                  {hero.copy.primaryCta}
                </Button>
                <Button
                  variant="outline"
                  className="h-11 rounded-full border-black/15 bg-white/70 px-6 text-[#2D2A26]"
                >
                  <FolderOpen className="mr-2 h-4 w-4" />
                  {hero.copy.secondaryCta}
                </Button>
              </div>

              <p className="max-w-xl text-sm leading-7 text-[#7E8B97]">{props.copy.backgroundTitle}</p>
            </div>

            <div className="relative min-w-0">
              <HeroScene
                progress={0.62}
                stageIndex={2}
                reducedMotion={reducedMotion}
                isMobile={isCompact}
              />
            </div>
          </div>
        </section>
      </div>

      <div className="absolute inset-0 z-20 bg-[#ECEBE8]/78 backdrop-blur-[3px]" />
      <div className="relative z-30 flex min-h-screen items-center justify-center px-6 py-8">
        <div className="w-full max-w-lg rounded-[30px] border border-black/10 bg-[#EFEFEF]/95 p-8 shadow-[0_30px_90px_-52px_rgba(32,26,19,0.5)] backdrop-blur-2xl">
          <div className="space-y-3 text-left">
            <div className="flex items-start justify-between gap-4">
              <h2 className="text-[1.85rem] font-semibold tracking-tight text-black">{props.copy.title}</h2>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-9 rounded-full border-black/10 bg-white text-[#2D2A26] hover:bg-white/90"
                onClick={props.onToggleLocale}
              >
                <Languages className="mr-2 h-4 w-4" />
                {props.locale === 'zh' ? 'English' : '中文'}
              </Button>
            </div>
            <p className="text-sm leading-7 text-black/72">{props.copy.subtitle}</p>
          </div>
          <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
            <Input
              value={token}
              onChange={(event) => setToken(event.target.value)}
              placeholder={props.copy.placeholder}
              autoFocus
              autoComplete="current-password"
              spellCheck={false}
              className="h-12 rounded-2xl border border-black/10 bg-white text-base text-black placeholder:text-black/40"
            />
            {props.error ? <div className="text-sm text-[#B42318]">{props.error}</div> : null}
            <Button
              type="submit"
              className="h-11 w-full rounded-2xl bg-[#D8D6D1] text-black hover:bg-[#CECBC5]"
              disabled={submitting || !token.trim()}
            >
              {submitting ? props.copy.loading : props.copy.submit}
            </Button>
          </form>
          <div className="mt-5 rounded-[22px] border border-black/8 bg-white/72 px-4 py-4 text-sm leading-6 text-black/78">
            <div className="font-medium text-black">{props.copy.helperTitle}</div>
            <div className="mt-2">{props.copy.helperViewToken}</div>
            <div className="mt-1">{props.copy.helperDisableAuth}</div>
          </div>
        </div>
      </div>
    </div>
  )
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const { locale, toggleLocale } = useI18n()
  const config = React.useMemo(() => runtimeAuthConfig(), [])
  const copy = React.useMemo(() => authCopy(locale), [locale])
  const [ready, setReady] = React.useState(!config.enabled)
  const [authenticated, setAuthenticated] = React.useState(!config.enabled)
  const [token, setToken] = React.useState<string | null>(() => readStoredBrowserAuthToken())
  const [error, setError] = React.useState<string | null>(null)
  const initialInputValueRef = React.useRef(readUrlBrowserAuthToken() || readStoredBrowserAuthToken() || '')

  const syncResolvedToken = React.useCallback(async (candidate?: string | null) => {
    const normalizedCandidate = typeof candidate === 'string' ? candidate.trim() : ''
    if (normalizedCandidate) {
      storeBrowserAuthToken(normalizedCandidate)
      setToken(normalizedCandidate)
      return normalizedCandidate
    }
    const fetched = await fetchBrowserAuthToken()
    if (fetched) {
      storeBrowserAuthToken(fetched)
      setToken(fetched)
    }
    return fetched
  }, [])

  React.useEffect(() => {
    if (!config.enabled) {
      setReady(true)
      setAuthenticated(true)
      return
    }
    let active = true
    const urlToken = readUrlBrowserAuthToken()
    const storedToken = readStoredBrowserAuthToken()
    const candidate = urlToken || storedToken

    void (async () => {
      try {
        const ok = await probeAuth(candidate)
        if (!active) return
        if (ok) {
          await syncResolvedToken(candidate)
          clearBrowserAuthTokenFromLocation()
          setAuthenticated(true)
          setError(null)
        } else {
          storeBrowserAuthToken(null)
          clearBrowserAuthTokenFromLocation()
          setAuthenticated(false)
          setError(null)
        }
      } catch {
        if (!active) return
        storeBrowserAuthToken(null)
        setAuthenticated(false)
        setError(copy.unavailable)
      } finally {
        if (active) {
          setReady(true)
        }
      }
    })()

    return () => {
      active = false
    }
  }, [config.enabled, copy.unavailable, syncResolvedToken])

  const handleLogin = React.useCallback(
    async (candidate: string) => {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ token: candidate.trim() }),
      })
      const payload = (await response.json().catch(() => ({}))) as { message?: string }
      if (!response.ok) {
        if (response.status === 401 || response.status === 400) {
          throw new Error(copy.invalid)
        }
        throw new Error(payload.message || copy.invalid)
      }
      await syncResolvedToken(candidate)
      clearBrowserAuthTokenFromLocation()
      setAuthenticated(true)
      setError(null)
    },
    [copy.invalid, syncResolvedToken]
  )

  const revealToken = React.useCallback(async () => {
    if (token) {
      return token
    }
    return await syncResolvedToken(null)
  }, [syncResolvedToken, token])

  const contextValue = React.useMemo<AuthContextValue>(
    () => ({
      enabled: config.enabled,
      authenticated,
      token,
      revealToken,
    }),
    [authenticated, config.enabled, revealToken, token]
  )

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_top,rgba(215,198,174,0.42),transparent_38%),linear-gradient(180deg,#f1efea_0%,#e7e3dc_100%)] px-6 text-sm text-black/70">
        {copy.loading}
      </div>
    )
  }

  if (config.enabled && !authenticated) {
    return (
      <AuthContext.Provider value={contextValue}>
        <AuthLockScreen
          copy={copy}
          locale={locale}
          initialValue={initialInputValueRef.current}
          error={error}
          onToggleLocale={toggleLocale}
          onSubmit={async (candidate) => {
            try {
              await handleLogin(candidate)
            } catch (caught) {
              setError(caught instanceof Error ? caught.message : copy.invalid)
            }
          }}
        />
      </AuthContext.Provider>
    )
  }

  return <AuthContext.Provider value={contextValue}>{children}</AuthContext.Provider>
}

export function useBrowserAuth() {
  return React.useContext(AuthContext)
}
