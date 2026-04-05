import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'

import { AuthProvider } from '@/components/auth/AuthProvider'
import { DocsPage } from '@/components/docs/DocsPage'
import { OnboardingOverlay } from '@/components/onboarding/OnboardingOverlay'
import { SettingsPage, type ConfigDocumentName } from '@/components/settings/SettingsPage'
import type { ConnectorName } from '@/components/settings/connectorCatalog'
import { I18nProvider, useI18n } from '@/lib/i18n'
import { LandingPage } from '@/pages/LandingPage'
import { ProjectWorkspacePage } from '@/pages/ProjectWorkspacePage'

function normalizeConfigName(value?: string): ConfigDocumentName | null {
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

function settingsRoutePath(name?: ConfigDocumentName | null, connectorName?: ConnectorName | null) {
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
  const { configName, connectorName } = useParams()
  const { locale } = useI18n()
  const state = (location.state as { configName?: ConfigDocumentName | null } | null) ?? null
  const routeConfigName = normalizeConfigName(configName || (location.pathname.startsWith('/settings/connector') ? 'connector' : undefined))
  const routeConnectorName = normalizeConnectorName(connectorName)

  return (
    <SettingsPage
      requestedConfigName={routeConfigName ?? state?.configName ?? null}
      requestedConnectorName={routeConnectorName}
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

function AppRoutes() {
  return (
    <>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/projects" element={<LandingDialogRedirect dialog="quests" />} />
        <Route path="/projects/new/auto" element={<LandingDialogRedirect dialog="autonomous" />} />
        <Route path="/projects/new/copilot" element={<LandingDialogRedirect dialog="copilot" />} />
        <Route path="/projects/:projectId" element={<ProjectWorkspacePage />} />
        <Route path="/tutorial/demo/:scenarioId" element={<Navigate to="/projects/demo-memory" replace />} />
        <Route path="/docs/*" element={<DocsRoutePage />} />
        <Route path="/settings/connector" element={<SettingsRoutePage />} />
        <Route path="/settings/connector/:connectorName" element={<SettingsRoutePage />} />
        <Route path="/settings/connectors" element={<SettingsRoutePage />} />
        <Route path="/settings" element={<SettingsRoutePage />} />
        <Route path="/settings/:configName" element={<SettingsRoutePage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <OnboardingOverlay />
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
          <AppRoutes />
        </BrowserRouter>
      </AuthProvider>
    </I18nProvider>
  )
}
