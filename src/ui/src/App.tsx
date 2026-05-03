import { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'

import { AuthProvider } from '@/components/auth/AuthProvider'
import { WebDebugInspector } from '@/components/debug/WebDebugInspector'
import { DocsPage } from '@/components/docs/DocsPage'
import { OnboardingOverlay } from '@/components/onboarding/OnboardingOverlay'
import { SettingsPage, type ConfigDocumentName, type SettingsSectionName } from '@/components/settings/SettingsPage'
import type { ConnectorName } from '@/components/settings/connectorCatalog'
import { WebDebugProvider } from '@/lib/debug/useWebDebug'
import { I18nProvider, useI18n } from '@/lib/i18n'
import { LandingPage } from '@/pages/LandingPage'
import { ProjectWorkspacePage } from '@/pages/ProjectWorkspacePage'

function normalizeSettingsSectionName(value?: string): SettingsSectionName | null {
  if (value === 'summary') {
    return 'summary'
  }
  if (value === 'runtime') {
    return 'runtime'
  }
  if (value === 'deepxiv') {
    return 'deepxiv'
  }
  if (value === 'connectors-health') return 'connectors_health'
  if (value === 'diagnostics') return 'diagnostics'
  if (value === 'errors') return 'errors'
  if (value === 'issues') return 'issues'
  if (value === 'logs') return 'logs'
  if (value === 'quests') return 'quests'
  if (value === 'repairs') return 'repairs'
  if (value === 'controllers') return 'controllers'
  if (value === 'stats') return 'stats'
  if (value === 'search') return 'search'
  if (value === 'connector' || value === 'connectors') {
    return 'connectors'
  }
  if (value && ['config', 'runners', 'plugins', 'mcp_servers', 'baselines'].includes(value)) {
    return value as ConfigDocumentName
  }
  return null
}

function normalizeConnectorName(value?: string): ConnectorName | null {
  if (value && ['qq', 'weixin', 'telegram', 'discord', 'slack', 'feishu', 'whatsapp', 'lingzhu'].includes(value)) {
    return value as ConnectorName
  }
  return null
}

function settingsRoutePath(name?: SettingsSectionName | null, connectorName?: ConnectorName | null) {
  if (!name) {
    return '/settings'
  }
  if (name === 'summary') {
    return '/settings/summary'
  }
  if (name === 'runtime') {
    return '/settings/runtime'
  }
  if (name === 'deepxiv') {
    return '/settings/deepxiv'
  }
  if (name === 'connectors') {
    return connectorName ? `/settings/connector/${connectorName}` : '/settings/connector'
  }
  return name ? `/settings/${name}` : '/settings'
}

function normalizeRequestedDocSlug(pathname: string): string | null {
  const marker = '/docs'
  if (!pathname.startsWith(marker)) {
    return null
  }
  const raw = pathname.slice(marker.length).replace(/^\/+/, '').trim()
  if (!raw) {
    return null
  }
  return raw
    .split('/')
    .filter(Boolean)
    .map((segment) => decodeURIComponent(segment))
    .join('/')
}

function DocsRoutePage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { locale } = useI18n()

  return (
    <DocsPage
      locale={locale}
      requestedDocumentSlug={normalizeRequestedDocSlug(location.pathname)}
      onOpenSettings={(name?: ConfigDocumentName, hash?: string) =>
        navigate(
          {
            pathname: settingsRoutePath(name),
            hash: hash ? (hash.startsWith('#') ? hash : `#${hash}`) : '',
          },
          { state: name && !hash ? { configName: name } : null }
        )
      }
    />
  )
}

function SettingsRoutePage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { configName, connectorName, questId } = useParams()
  const { locale } = useI18n()
  const state = (location.state as { configName?: SettingsSectionName | null } | null) ?? null
  const routeHint = location.pathname.startsWith('/settings/summary')
    ? 'summary'
    : location.pathname.startsWith('/settings/runtime')
    ? 'runtime'
    : location.pathname.startsWith('/settings/deepxiv')
      ? 'deepxiv'
    : location.pathname.startsWith('/settings/connectors-health')
      ? 'connectors-health'
      : location.pathname.startsWith('/settings/diagnostics')
        ? 'diagnostics'
        : location.pathname.startsWith('/settings/errors')
          ? 'errors'
          : location.pathname.startsWith('/settings/issues')
            ? 'issues'
            : location.pathname.startsWith('/settings/logs')
              ? 'logs'
              : location.pathname.startsWith('/settings/quests')
                ? 'quests'
                : location.pathname.startsWith('/settings/repairs')
                  ? 'repairs'
                  : location.pathname.startsWith('/settings/controllers')
                    ? 'controllers'
                    : location.pathname.startsWith('/settings/stats')
                      ? 'stats'
                      : location.pathname.startsWith('/settings/search')
                        ? 'search'
    : location.pathname.startsWith('/settings/connector')
      ? 'connector'
      : configName
  const routeConfigName = normalizeSettingsSectionName(routeHint || undefined)
  const routeConnectorName = normalizeConnectorName(connectorName)

  return (
    <SettingsPage
      requestedConfigName={routeConfigName ?? state?.configName ?? null}
      requestedConnectorName={routeConnectorName}
      requestedQuestId={questId ?? null}
      onRequestedConfigConsumed={state?.configName ? () => navigate('.', { replace: true, state: null }) : undefined}
      runtimeAddress={window.location.origin}
      locale={locale}
    />
  )
}

function LandingDialogRedirect(props: {
  dialog: 'quests' | 'copilot' | 'autonomous'
}) {
  return <Navigate to="/" replace state={{ landingDialog: props.dialog }} />
}

function AdminQuestRedirect() {
  const { questId = '' } = useParams()
  return <Navigate to={`/settings/quests/${encodeURIComponent(questId)}`} replace />
}

function RouteEffectListener() {
  const navigate = useNavigate()

  useEffect(() => {
    const handleNavigate = (event: Event) => {
      const detail = (event as CustomEvent<{ to?: string; replace?: boolean }>).detail
      const to = typeof detail?.to === 'string' ? detail.to.trim() : ''
      if (!to) return
      navigate(to, { replace: Boolean(detail?.replace) })
    }

    window.addEventListener('ds:route:navigate', handleNavigate as EventListener)
    return () => window.removeEventListener('ds:route:navigate', handleNavigate as EventListener)
  }, [navigate])

  return null
}

function AppRoutes() {
  return (
    <>
      <RouteEffectListener />
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/projects" element={<LandingDialogRedirect dialog="quests" />} />
        <Route path="/projects/new/auto" element={<LandingDialogRedirect dialog="autonomous" />} />
        <Route path="/projects/new/copilot" element={<LandingDialogRedirect dialog="copilot" />} />
        <Route path="/projects/:projectId" element={<ProjectWorkspacePage />} />
        <Route path="/admin" element={<Navigate to="/settings/summary" replace />} />
        <Route path="/admin/quests" element={<Navigate to="/settings/quests" replace />} />
        <Route path="/admin/quests/:questId" element={<AdminQuestRedirect />} />
        <Route path="/admin/connectors" element={<Navigate to="/settings/connectors-health" replace />} />
        <Route path="/admin/config" element={<Navigate to="/settings/config" replace />} />
        <Route path="/admin/runtime" element={<Navigate to="/settings/runtime" replace />} />
        <Route path="/admin/logs" element={<Navigate to="/settings/logs" replace />} />
        <Route path="/admin/diagnostics" element={<Navigate to="/settings/diagnostics" replace />} />
        <Route path="/admin/errors" element={<Navigate to="/settings/errors" replace />} />
        <Route path="/admin/issues" element={<Navigate to="/settings/issues" replace />} />
        <Route path="/admin/controllers" element={<Navigate to="/settings/controllers" replace />} />
        <Route path="/admin/stats" element={<Navigate to="/settings/stats" replace />} />
        <Route path="/admin/search" element={<Navigate to="/settings/search" replace />} />
        <Route path="/admin/repairs" element={<Navigate to="/settings/repairs" replace />} />
        <Route path="/tutorial/demo/:scenarioId" element={<Navigate to="/projects/demo-memory" replace />} />
        <Route path="/docs/*" element={<DocsRoutePage />} />
        <Route path="/settings/summary" element={<SettingsRoutePage />} />
        <Route path="/settings/connector" element={<SettingsRoutePage />} />
        <Route path="/settings/connector/:connectorName" element={<SettingsRoutePage />} />
        <Route path="/settings/connectors" element={<SettingsRoutePage />} />
        <Route path="/settings/connectors-health" element={<SettingsRoutePage />} />
        <Route path="/settings/diagnostics" element={<SettingsRoutePage />} />
        <Route path="/settings/errors" element={<SettingsRoutePage />} />
        <Route path="/settings/issues" element={<SettingsRoutePage />} />
        <Route path="/settings/logs" element={<SettingsRoutePage />} />
        <Route path="/settings/quests" element={<SettingsRoutePage />} />
        <Route path="/settings/quests/:questId" element={<SettingsRoutePage />} />
        <Route path="/settings/repairs" element={<SettingsRoutePage />} />
        <Route path="/settings/controllers" element={<SettingsRoutePage />} />
        <Route path="/settings/stats" element={<SettingsRoutePage />} />
        <Route path="/settings/search" element={<SettingsRoutePage />} />
        <Route path="/settings/runtime" element={<SettingsRoutePage />} />
        <Route path="/settings/deepxiv" element={<SettingsRoutePage />} />
        <Route path="/settings" element={<SettingsRoutePage />} />
        <Route path="/settings/:configName" element={<SettingsRoutePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <OnboardingOverlay />
      <WebDebugInspector />
    </>
  )
}

function resolveRouterBasename(): string {
  if (typeof window === 'undefined') {
    return '/'
  }
  return window.location.pathname.startsWith('/ui/') ? '/ui' : '/'
}

export default function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <BrowserRouter basename={resolveRouterBasename()}>
          <WebDebugProvider>
            <AppRoutes />
          </WebDebugProvider>
        </BrowserRouter>
      </AuthProvider>
    </I18nProvider>
  )
}
