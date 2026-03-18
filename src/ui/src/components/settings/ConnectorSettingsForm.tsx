import {
  ArrowLeft,
  ArrowDownLeft,
  ArrowUpRight,
  Ban,
  BookOpenText,
  CheckCircle2,
  Link2,
  MessageSquareText,
  RadioTower,
  Save,
  ShieldCheck,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { HintDot } from '@/components/ui/hint-dot'
import { Input } from '@/components/ui/input'
import { Modal, ModalFooter } from '@/components/ui/modal'
import { Textarea } from '@/components/ui/textarea'
import { connectorTargetLabel, normalizeConnectorTargets, parseConversationId } from '@/lib/connectors'
import { getDocAssetUrl } from '@/lib/docs'
import { cn } from '@/lib/utils'
import type {
  ConnectorRecentEvent,
  ConnectorSnapshot,
  ConnectorTargetSnapshot,
  Locale,
} from '@/types'

import { connectorCatalog, type ConnectorCatalogEntry, type ConnectorField, type ConnectorName } from './connectorCatalog'
import {
  connectorGuideCatalog,
  connectorGuideDocHref,
  localizedGuideText,
  type ConnectorGuideEntry,
  type ConnectorGuideLink,
  type ConnectorGuideStep,
} from './connectorGuideCatalog'
import { translateSettingsCatalogText } from './settingsCatalogI18n'

type ConnectorConfigMap = Record<string, Record<string, unknown>>

const copy = {
  en: {
    title: 'Connectors',
    subtitle: 'Bind accounts and review runtime state from one place.',
    enabled: 'Enabled',
    disabled: 'Disabled',
    testTarget: 'Test target',
    chatType: 'Type',
    direct: 'Direct',
    group: 'Group',
    chatId: 'Chat ID',
    qqChatIdHint: 'Use QQ user `openid` or group `group_openid`, not a QQ number.',
    probeText: 'Message',
    probePlaceholder: 'Optional probe message…',
    save: 'Save',
    saving: 'Saving…',
    portal: 'Portal',
    emptyValidation: 'No issues.',
    emptyTest: 'No issues.',
    snapshot: 'Runtime',
    transportLabel: 'Transport',
    connection: 'Connection',
    auth: 'Auth',
    lastMode: 'Mode',
    queues: 'Queues',
    queueIn: 'in',
    queueOut: 'out',
    bindings: 'Bindings',
    boundTarget: 'Bound target',
    defaultTarget: 'Default target',
    discoveredTargets: 'Discovered targets',
    lastSeen: 'Last seen',
    noSnapshot: 'No snapshot.',
    noTargets: 'No runtime targets yet.',
    recentActivity: 'Recent activity',
    noEvents: 'No connector events yet.',
    inbound: 'Inbound',
    outbound: 'Outbound',
    ignored: 'Ignored',
    deliveryOk: 'Delivered',
    deliveryQueued: 'Queued',
    deliveryFailed: 'Failed',
    useTarget: 'Use',
    ok: 'Ready',
    needsWork: 'Needs work',
    showLegacy: 'Show legacy fields',
    hideLegacy: 'Hide legacy fields',
    routingTitle: 'Routing',
    routingSubtitle: 'Choose where milestone and decision updates go.',
    routingEmpty: 'Enable a connector first.',
    routingAutoSingle: 'One active connector. It becomes the default target automatically.',
    primaryConnector: 'Primary',
    deliveryPolicy: 'Policy',
    fanoutAll: 'All',
    primaryOnly: 'Primary',
    primaryPlusLocal: 'Primary + local',
    selected: 'Selected',
    localMirror: 'Local UI/TUI can still mirror updates in mixed mode.',
    fieldHintPrefix: 'How to fill:',
    overviewTitle: 'Connector catalog',
    overviewSubtitle: 'Open one connector at a time. Each detail page is reduced to a step-by-step setup flow.',
    openConnector: 'Open setup',
    backToCatalog: 'Back to connectors',
    docs: 'Docs',
    localGuide: 'Guide',
    quickChecks: 'Before you start',
    requiredFields: 'Key fields',
    openOfficialDocs: 'Official docs',
    openLocalDocs: 'Full guide',
    stepChecklist: 'What to do',
    stepFields: 'Fill in this step',
    stepSaveHint: 'Save after finishing this step.',
    stepProbeHint: 'After the platform-side action is done, return here and check the runtime snapshot.',
    blockedTitle: 'Before you continue',
    missingFields: 'Missing now',
    saveConnectorFirst: 'Save this connector before moving to the next step.',
    sendPlatformMessageFirst: 'Go to the platform, send one real message or mention, then return here.',
    enableConnectorFirst: 'Enable this connector and fill the missing credentials first.',
    detailSubtitle: 'Complete one connector from Step 1 onward instead of editing every platform in one long page.',
    stepSaveAction: 'Save this connector',
    connectorReference: 'Connector docs',
    useDiscoveredTargets: 'Use the runtime-discovered target whenever possible.',
    setupFlow: 'Setup flow',
    nextAction: 'Next action',
    bindConnectorTitle: 'Add connector',
    boundTargetsTitle: 'Detected IDs',
    boundTargetsHint: 'After the first real message reaches DeepScientist, detected conversation IDs will appear here for later selection.',
    openGuidedSetup: 'Start guided setup',
    wizardClose: 'Close',
    wizardBack: 'Back',
    wizardContinue: 'Continue',
    wizardDone: 'Done',
    wizardSaveContinue: 'Save and continue',
    boundQuestLabel: 'Quest',
    notBoundYet: 'Not currently bound to another project.',
    qqStepPlatform: 'Create QQ bot',
    qqStepCredentials: 'Save connector settings',
    qqStepBind: 'Send first private message',
    qqStepSuccess: 'Check and confirm',
    qqQuickSetup: 'Quick setup',
    qqStepAdvanced: 'Advanced',
    qqStepDone: 'Done',
    qqStepCurrent: 'Current',
    qqStepPending: 'Pending',
    qqPlatformHint: 'Create the QQ bot first, then copy the App ID and App Secret into Settings.',
    qqPlatformChecklist1: 'Open the QQ bot platform and create the bot.',
    qqPlatformChecklist2: 'Save the App ID and App Secret immediately.',
    qqPlatformChecklist3: 'Do not fill OpenID manually before the first private message arrives.',
    qqSaveNow: 'Save credentials',
    qqSaveFirst: 'Save the App ID and App Secret first.',
    qqAfterSave: 'After saving, send `/help` or any private message to the bot from QQ.',
    qqWaitingOpenId: 'Waiting for the first QQ private message.',
    qqOpenIdDetected: 'OpenID detected and saved automatically.',
    qqConnectedSummary: 'QQ is ready for direct chat, auto-binding, and milestone delivery.',
    qqMilestoneDefaults: 'Milestone delivery is enabled by default. Only change these switches if you want less outbound push.',
    qqAdvancedHint: 'Group mention policy, gateway restart, command prefix, auto-binding, and milestone delivery.',
    qqDetectedOpenId: 'Detected OpenID',
    qqDetectedOpenIdHint: 'This value appears after the first private QQ message reaches the built-in gateway.',
    qqBindChecklistTitle: 'What to do next',
    qqBindChecklist1: 'Open QQ and send one private message to the bot.',
    qqBindChecklist2: 'Wait for DeepScientist to detect the OpenID and save it.',
    qqBindChecklist3: 'Return here and confirm the detected OpenID is no longer empty.',
    qqProbeLockedUntilOpenId: 'The probe unlocks after the first QQ private message is detected.',
    qqNeedOpenIdFirst: 'Send the first QQ private message so DeepScientist can detect and save the OpenID.',
    lingzhuQuickSetup: 'Quick setup',
    lingzhuStepEndpoint: 'Gateway endpoint',
    lingzhuStepPlatform: 'Platform values',
    lingzhuStepProbe: 'Probe and verify',
    lingzhuNeedPublicIp: 'Lingzhu requires a public IP or public domain. `127.0.0.1` only works for local health checks.',
    lingzhuUseLocalDefaults: 'Use local defaults',
    lingzhuGenerateAk: 'Generate AK',
    lingzhuGeneratedValues: 'Generated values',
    lingzhuLocalHealthUrl: 'Local health URL',
    lingzhuLocalSseUrl: 'Local SSE URL',
    lingzhuPublicSseUrl: 'Public SSE URL',
    lingzhuPublicHint: 'Fill the public URL that the glasses can really reach.',
    lingzhuOpenclawConfig: 'OpenClaw config snippet',
    lingzhuCurl: 'Probe curl',
    lingzhuSupportedCommands: 'Supported commands',
    lingzhuSnapshotHint: 'The runtime probe checks local reachability only. It does not prove that your public IP is already exposed correctly.',
    lingzhuRunProbe: 'Run Lingzhu probe',
    lingzhuProbeResult: 'Lingzhu probe',
    lingzhuNoProbeYet: 'Run the probe after saving the AK and endpoint values.',
    lingzhuAgentIdHint: 'Use the same agent id on both OpenClaw and Lingzhu.',
    lingzhuPlatformReminder: 'Paste the generated public SSE URL and AK into the Lingzhu platform.',
    lingzhuCompleteEndpointFirst: 'Finish Step 1 and save the gateway endpoint values first.',
    lingzhuSavePlatformValuesFirst: 'Save the public URL, AK, and agent values before running the Lingzhu probe.',
  },
  zh: {
    title: '连接器',
    subtitle: '在一个面板里完成账号绑定，并查看运行时状态。',
    enabled: '已启用',
    disabled: '已禁用',
    testTarget: '测试目标',
    chatType: '类型',
    direct: '私聊',
    group: '群聊',
    chatId: '会话 ID',
    qqChatIdHint: '请填写 QQ 用户 `openid` 或群 `group_openid`，不要填写 QQ 号。',
    probeText: '消息',
    probePlaceholder: '可选探针消息…',
    save: '保存',
    saving: '保存中…',
    portal: '平台',
    emptyValidation: '没有问题。',
    emptyTest: '没有问题。',
    snapshot: '运行时',
    transportLabel: '传输方式',
    connection: '连接状态',
    auth: '鉴权状态',
    lastMode: '模式',
    queues: '队列',
    queueIn: '入',
    queueOut: '出',
    bindings: '绑定数',
    boundTarget: '已绑定目标',
    defaultTarget: '默认目标',
    discoveredTargets: '已发现目标',
    lastSeen: '最近会话',
    noSnapshot: '暂无快照。',
    noTargets: '暂未发现运行时目标。',
    recentActivity: '最近活动',
    noEvents: '暂时还没有连接器事件。',
    inbound: '收到',
    outbound: '发出',
    ignored: '忽略',
    deliveryOk: '已送达',
    deliveryQueued: '队列中',
    deliveryFailed: '发送失败',
    useTarget: '使用',
    ok: '就绪',
    needsWork: '需处理',
    showLegacy: '显示旧式字段',
    hideLegacy: '隐藏旧式字段',
    routingTitle: '路由',
    routingSubtitle: '决定里程碑和决策更新优先发往哪里。',
    routingEmpty: '请先启用一个连接器。',
    routingAutoSingle: '当前只有一个已启用连接器，它会自动成为默认目标。',
    primaryConnector: '首选',
    deliveryPolicy: '策略',
    fanoutAll: '全部',
    primaryOnly: '首选',
    primaryPlusLocal: '首选 + 本地',
    selected: '已选',
    localMirror: '混合模式下，本地 Web/TUI 仍会保留同步视图。',
    fieldHintPrefix: '填写方式:',
    overviewTitle: '连接器目录',
    overviewSubtitle: '先选一个 connector 进入，再按 Step 1 / Step 2 / Step 3 完成配置，不再把所有平台堆在一页里。',
    openConnector: '进入配置',
    backToCatalog: '返回连接器列表',
    docs: '文档',
    localGuide: '指南',
    quickChecks: '开始前先确认',
    requiredFields: '关键字段',
    openOfficialDocs: '官方文档',
    openLocalDocs: '完整指南',
    stepChecklist: '本步要做什么',
    stepFields: '本步填写项',
    stepSaveHint: '完成本步后先保存。',
    stepProbeHint: '先完成平台侧操作，再回来查看运行时快照。',
    blockedTitle: '继续前先完成这些',
    missingFields: '当前还缺',
    saveConnectorFirst: '进入下一步前，请先保存当前 connector。',
    sendPlatformMessageFirst: '请先回到平台侧发送一条真实消息或一次 @ 提及，再回来继续。',
    enableConnectorFirst: '请先启用当前 connector，并补齐缺少的凭据。',
    detailSubtitle: '一次只配置一个 connector，从 Step 1 开始，不再在一页里同时编辑所有平台。',
    stepSaveAction: '保存当前 connector',
    connectorReference: '连接器文档',
    useDiscoveredTargets: '能用运行时自动发现目标时，优先直接使用，不要盲填目标 id。',
    setupFlow: '配置流程',
    nextAction: '当前下一步',
    bindConnectorTitle: '新增 Connector',
    boundTargetsTitle: '已发现 ID',
    boundTargetsHint: '当第一条真实消息到达 DeepScientist 后，这里会显示后续可选用的会话 ID。',
    openGuidedSetup: '开始分步配置',
    wizardClose: '关闭',
    wizardBack: '上一步',
    wizardContinue: '继续',
    wizardDone: '完成',
    wizardSaveContinue: '保存并继续',
    boundQuestLabel: '项目',
    notBoundYet: '当前还没有绑定到其他项目。',
    qqStepPlatform: '创建 QQ 机器人',
    qqStepCredentials: '保存 connector 设置',
    qqStepBind: '发送第一条私聊',
    qqStepSuccess: '校验并确认',
    qqQuickSetup: '快速接入',
    qqStepAdvanced: '高级设置',
    qqStepDone: '已完成',
    qqStepCurrent: '当前',
    qqStepPending: '待完成',
    qqPlatformHint: '先在 QQ 平台创建机器人，再把 App ID 与 App Secret 复制回来。',
    qqPlatformChecklist1: '打开 QQ 机器人平台并创建机器人。',
    qqPlatformChecklist2: '立刻保存 App ID 和 App Secret。',
    qqPlatformChecklist3: '在第一条私聊到达前，不要手动填写 OpenID。',
    qqSaveNow: '保存凭据',
    qqSaveFirst: '请先保存 App ID 和 App Secret。',
    qqAfterSave: '保存后，请从 QQ 给机器人发送 `/help` 或任意一条私聊消息。',
    qqWaitingOpenId: '正在等待第一条 QQ 私聊消息。',
    qqOpenIdDetected: '已自动检测并保存 OpenID。',
    qqConnectedSummary: 'QQ 已可以用于直接沟通、自动绑定和里程碑投递。',
    qqMilestoneDefaults: '里程碑投递默认全部开启。只有在你想减少外发内容时才需要调整这些开关。',
    qqAdvancedHint: '群内 @ 规则、网关重启、命令前缀、自动绑定和里程碑投递。',
    qqDetectedOpenId: '已检测 OpenID',
    qqDetectedOpenIdHint: '当第一条 QQ 私聊到达内置网关后，这里会自动显示。',
    qqBindChecklistTitle: '下一步操作',
    qqBindChecklist1: '打开 QQ，给机器人发送一条私聊消息。',
    qqBindChecklist2: '等待 DeepScientist 自动检测并保存 OpenID。',
    qqBindChecklist3: '回到这里确认 OpenID 已不再为空。',
    qqProbeLockedUntilOpenId: '检测到第一条 QQ 私聊并拿到 OpenID 后，测试入口才会解锁。',
    qqNeedOpenIdFirst: '请先发送第一条 QQ 私聊，让 DeepScientist 自动检测并保存 OpenID。',
    lingzhuQuickSetup: '快速接入',
    lingzhuStepEndpoint: '网关端点',
    lingzhuStepPlatform: '平台填写值',
    lingzhuStepProbe: '探测与校验',
    lingzhuNeedPublicIp: 'Lingzhu 需要公网 IP 或公网域名。`127.0.0.1` 只能用于本地健康检查。',
    lingzhuUseLocalDefaults: '使用本地默认值',
    lingzhuGenerateAk: '生成 AK',
    lingzhuGeneratedValues: '自动生成值',
    lingzhuLocalHealthUrl: '本地健康检查 URL',
    lingzhuLocalSseUrl: '本地 SSE URL',
    lingzhuPublicSseUrl: '公网 SSE URL',
    lingzhuPublicHint: '这里应填写眼镜端真正能够访问到的公网地址。',
    lingzhuOpenclawConfig: 'OpenClaw 配置片段',
    lingzhuCurl: '探测 curl',
    lingzhuSupportedCommands: '支持的命令',
    lingzhuSnapshotHint: '运行时探测只能检查本地可达性，不能替代公网暴露是否正确的最终验证。',
    lingzhuRunProbe: '执行 Lingzhu 探测',
    lingzhuProbeResult: 'Lingzhu 探测结果',
    lingzhuNoProbeYet: '保存 AK 和端点后，再执行探测。',
    lingzhuAgentIdHint: 'OpenClaw 与 Lingzhu 两侧应使用同一个 agent id。',
    lingzhuPlatformReminder: '请把自动生成的公网 SSE URL 和 AK 填回到 Lingzhu 平台中。',
    lingzhuCompleteEndpointFirst: '请先完成 Step 1，并保存网关端点配置。',
    lingzhuSavePlatformValuesFirst: '执行 Lingzhu 探测前，请先保存公网地址、AK 和 agent 等平台值。',
  },
} satisfies Record<Locale, Record<string, string>>

function fieldValue(config: Record<string, unknown>, field: ConnectorField) {
  const raw = config[field.key]
  if (field.kind === 'boolean') {
    return Boolean(raw)
  }
  if (field.kind === 'list') {
    return Array.isArray(raw) ? raw.join(', ') : ''
  }
  return typeof raw === 'string' || typeof raw === 'number' ? String(raw) : ''
}

function normalizeFieldValue(field: ConnectorField, value: string | boolean) {
  if (field.kind === 'boolean') {
    return Boolean(value)
  }
  if (field.kind === 'list') {
    return String(value)
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
  }
  return String(value)
}

function snapshotByName(items: ConnectorSnapshot[]) {
  return new Map(items.map((item) => [item.name, item]))
}

function connectorEventLabel(event: ConnectorRecentEvent) {
  const label = String(event.label || '').trim()
  if (label) {
    return label
  }
  const chatType = String(event.chat_type || '').trim()
  const chatId = String(event.chat_id || '').trim()
  return [chatType, chatId].filter(Boolean).join(' · ')
}

function connectorEventPreview(event: ConnectorRecentEvent) {
  const message = String(event.message || '').trim()
  if (message) {
    return message
  }
  return String(event.reason || '').trim()
}

function connectorEventTime(value: string | null | undefined) {
  const normalized = String(value || '').trim()
  if (!normalized) {
    return ''
  }
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) {
    return normalized
  }
  return date.toLocaleString()
}

function connectorEventStatus(event: ConnectorRecentEvent, locale: Locale) {
  const t = copy[locale]
  if (event.event_type !== 'outbound') {
    return ''
  }
  if (event.queued) {
    return t.deliveryQueued
  }
  if (event.ok) {
    return t.deliveryOk
  }
  return t.deliveryFailed
}

function lingzhuConfigString(config: Record<string, unknown>, key: string, fallback = '') {
  const value = config[key]
  return typeof value === 'string' || typeof value === 'number' ? String(value).trim() : fallback
}

function lingzhuGatewayPort(config: Record<string, unknown>) {
  const parsed = Number.parseInt(lingzhuConfigString(config, 'gateway_port', '18789'), 10)
  return Number.isFinite(parsed) && parsed >= 1 && parsed <= 65535 ? parsed : 18789
}

function lingzhuLocalHost(config: Record<string, unknown>) {
  return lingzhuConfigString(config, 'local_host', '127.0.0.1') || '127.0.0.1'
}

function lingzhuLocalBaseUrl(config: Record<string, unknown>) {
  return `http://${lingzhuLocalHost(config)}:${lingzhuGatewayPort(config)}`
}

function normalizeBaseUrl(value: string) {
  const trimmed = value.trim()
  if (!trimmed) return ''
  try {
    const url = new URL(trimmed)
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return ''
    return trimmed.replace(/\/$/, '')
  } catch {
    return ''
  }
}

function lingzhuPublicBaseUrl(config: Record<string, unknown>) {
  return normalizeBaseUrl(lingzhuConfigString(config, 'public_base_url'))
}

function lingzhuLocalHealthUrl(config: Record<string, unknown>) {
  return `${lingzhuLocalBaseUrl(config)}/metis/agent/api/health`
}

function lingzhuLocalSseUrl(config: Record<string, unknown>) {
  return `${lingzhuLocalBaseUrl(config)}/metis/agent/api/sse`
}

function lingzhuPublicSseUrl(config: Record<string, unknown>) {
  const base = lingzhuPublicBaseUrl(config)
  return base ? `${base}/metis/agent/api/sse` : ''
}

function lingzhuAgentId(config: Record<string, unknown>) {
  return lingzhuConfigString(config, 'agent_id', 'main') || 'main'
}

function lingzhuBool(config: Record<string, unknown>, key: string, fallback = false) {
  const value = config[key]
  return typeof value === 'boolean' ? value : fallback
}

function lingzhuNumber(config: Record<string, unknown>, key: string, fallback: number) {
  const raw = Number.parseInt(lingzhuConfigString(config, key, String(fallback)), 10)
  return Number.isFinite(raw) ? raw : fallback
}

function createLingzhuAk() {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789'
  const segments = [8, 4, 4, 4, 12]
  const bytes =
    typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function'
      ? crypto.getRandomValues(new Uint8Array(segments.reduce((sum, item) => sum + item, 0)))
      : Uint8Array.from({ length: segments.reduce((sum, item) => sum + item, 0) }, () => Math.floor(Math.random() * 256))
  let index = 0
  return segments
    .map((size) => {
      let segment = ''
      for (let i = 0; i < size; i += 1) {
        segment += chars[bytes[index] % chars.length]
        index += 1
      }
      return segment
    })
    .join('-')
}

function lingzhuGeneratedOpenclawConfig(config: Record<string, unknown>) {
  return JSON.stringify(
    {
      gateway: {
        port: lingzhuGatewayPort(config),
        http: {
          endpoints: {
            chatCompletions: {
              enabled: true,
            },
          },
        },
      },
      plugins: {
        entries: {
          lingzhu: {
            enabled: lingzhuBool(config, 'enabled', false),
            config: {
              authAk: lingzhuConfigString(config, 'auth_ak'),
              agentId: lingzhuAgentId(config),
              includeMetadata: lingzhuBool(config, 'include_metadata', true),
              requestTimeoutMs: lingzhuNumber(config, 'request_timeout_ms', 60000),
              systemPrompt: lingzhuConfigString(config, 'system_prompt'),
              defaultNavigationMode: lingzhuConfigString(config, 'default_navigation_mode', '0') || '0',
              enableFollowUp: lingzhuBool(config, 'enable_follow_up', true),
              followUpMaxCount: lingzhuNumber(config, 'follow_up_max_count', 3),
              maxImageBytes: lingzhuNumber(config, 'max_image_bytes', 5242880),
              sessionMode: lingzhuConfigString(config, 'session_mode', 'per_user') || 'per_user',
              sessionNamespace: lingzhuConfigString(config, 'session_namespace', 'lingzhu') || 'lingzhu',
              autoReceiptAck: lingzhuBool(config, 'auto_receipt_ack', true),
              visibleProgressHeartbeat: lingzhuBool(config, 'visible_progress_heartbeat', true),
              visibleProgressHeartbeatSec: lingzhuNumber(config, 'visible_progress_heartbeat_sec', 10),
              debugLogging: lingzhuBool(config, 'debug_logging', false),
              debugLogPayloads: lingzhuBool(config, 'debug_log_payloads', false),
              debugLogDir: lingzhuConfigString(config, 'debug_log_dir'),
              enableExperimentalNativeActions: lingzhuBool(config, 'enable_experimental_native_actions', false),
            },
          },
        },
      },
    },
    null,
    2
  )
}

function lingzhuGeneratedCurl(config: Record<string, unknown>) {
  return [
    `curl -X POST '${lingzhuLocalSseUrl(config)}' \\`,
    `  --header 'Authorization: Bearer ${lingzhuConfigString(config, 'auth_ak')}' \\`,
    "  --header 'Content-Type: application/json' \\",
    `  --data '${JSON.stringify({
      message_id: 'ds-lingzhu-probe-001',
      agent_id: lingzhuAgentId(config),
      message: [{ role: 'user', type: 'text', text: '你好' }],
    })}'`,
  ].join('\n')
}

function routingConfig(value: ConnectorConfigMap): Record<string, unknown> {
  const raw = value._routing
  return raw && typeof raw === 'object' ? raw : {}
}

function fieldHint(field: ConnectorField, locale: Locale) {
  const t = copy[locale]
  const pieces = [
    translateSettingsCatalogText(locale, field.description),
    `${t.fieldHintPrefix} ${translateSettingsCatalogText(locale, field.whereToGet)}`,
  ]
  return pieces.filter(Boolean).join(' ')
}

function FieldHelp({ field, locale }: { field: ConnectorField; locale: Locale }) {
  const t = copy[locale]
  return (
    <div className="space-y-1 text-xs leading-5 text-muted-foreground">
      <div>{translateSettingsCatalogText(locale, field.description)}</div>
      <div>
        <span className="font-medium text-foreground/80">{t.fieldHintPrefix}</span>{' '}
        {translateSettingsCatalogText(locale, field.whereToGet)}
      </div>
    </div>
  )
}

function ConnectorEventRow({ event, locale }: { event: ConnectorRecentEvent; locale: Locale }) {
  const status = connectorEventStatus(event, locale)
  const label = connectorEventLabel(event)
  const preview = connectorEventPreview(event)
  const createdAt = connectorEventTime(event.created_at)
  const icon =
    event.event_type === 'outbound' ? (
      <ArrowUpRight className="h-3.5 w-3.5" />
    ) : event.event_type === 'ignored' ? (
      <Ban className="h-3.5 w-3.5" />
    ) : (
      <ArrowDownLeft className="h-3.5 w-3.5" />
    )
  const tone =
    event.event_type === 'outbound'
      ? event.ok || event.queued
        ? 'text-emerald-700 dark:text-emerald-300'
        : 'text-amber-700 dark:text-amber-300'
      : event.event_type === 'ignored'
        ? 'text-amber-700 dark:text-amber-300'
        : 'text-sky-700 dark:text-sky-300'

  return (
    <div className="rounded-[18px] border border-black/[0.08] bg-white/[0.42] px-3 py-3 dark:border-white/[0.12] dark:bg-white/[0.03]">
      <div className="flex items-start gap-3">
        <div className={cn('mt-0.5 flex h-7 w-7 items-center justify-center rounded-full bg-black/[0.04] dark:bg-white/[0.06]', tone)}>
          {icon}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-foreground">{label || event.event_type}</span>
            {status ? (
              <span className="rounded-full bg-black/[0.05] px-2 py-0.5 text-[10px] uppercase tracking-[0.14em] text-muted-foreground dark:bg-white/[0.06]">
                {status}
              </span>
            ) : null}
            {event.transport ? <span className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{event.transport}</span> : null}
          </div>
          {preview ? <div className="mt-1 break-words text-sm leading-6 text-muted-foreground">{preview}</div> : null}
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
            {createdAt ? <span>{createdAt}</span> : null}
            {event.kind ? <span>{event.kind}</span> : null}
          </div>
        </div>
      </div>
    </div>
  )
}

function ConnectorFieldControl({
  field,
  config,
  locale,
  onChange,
}: {
  field: ConnectorField
  config: Record<string, unknown>
  locale: Locale
  onChange: (key: string, value: unknown) => void
}) {
  const value = fieldValue(config, field)
  const controlClass = 'rounded-[18px] border-black/[0.08] bg-white/[0.44] shadow-none dark:bg-white/[0.03]'

  if (field.kind === 'boolean') {
    return (
      <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
        <label className="flex min-h-[44px] items-center justify-between gap-4">
          <span className="flex items-center gap-2 text-sm font-medium">
            <span>{translateSettingsCatalogText(locale, field.label)}</span>
            <HintDot label={fieldHint(field, locale)} />
          </span>
          <input
            type="checkbox"
            checked={Boolean(value)}
            onChange={(event) => onChange(field.key, event.target.checked)}
            disabled={Boolean(field.readOnly)}
            className="h-4 w-4 rounded border-black/20 text-foreground"
          />
        </label>
        <div className="mt-3">
          <FieldHelp field={field} locale={locale} />
        </div>
      </div>
    )
  }

  if (field.kind === 'select') {
    return (
      <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
        <label className="flex items-center gap-2 text-sm font-medium">
          <span>{translateSettingsCatalogText(locale, field.label)}</span>
          <HintDot label={fieldHint(field, locale)} />
        </label>
        <select
          value={String(value || '')}
          onChange={(event) => onChange(field.key, normalizeFieldValue(field, event.target.value))}
          disabled={Boolean(field.readOnly)}
          className={cn(
            'flex h-11 w-full rounded-[18px] border px-3 py-2 text-sm ring-offset-background transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50',
            controlClass
          )}
        >
          {(field.options || []).map((option) => (
            <option key={option.value} value={option.value}>
              {translateSettingsCatalogText(locale, option.label)}
            </option>
          ))}
        </select>
        <div className="mt-3">
          <FieldHelp field={field} locale={locale} />
        </div>
      </div>
    )
  }

  const sharedProps = {
    value: String(value || ''),
    onChange: (nextValue: string) => onChange(field.key, normalizeFieldValue(field, nextValue)),
    placeholder: field.placeholder,
    className: controlClass,
    disabled: Boolean(field.readOnly),
  }

  return (
    <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
      <label className="flex items-center gap-2 text-sm font-medium">
        <span>{translateSettingsCatalogText(locale, field.label)}</span>
        <HintDot label={fieldHint(field, locale)} />
      </label>
      {field.kind === 'list' ? (
        <Textarea
          value={sharedProps.value}
          onChange={(event) => sharedProps.onChange(event.target.value)}
          placeholder={translateSettingsCatalogText(locale, sharedProps.placeholder)}
          disabled={sharedProps.disabled}
          className={cn('min-h-[92px] resize-y', sharedProps.className)}
        />
      ) : (
        <Input
          type={field.kind === 'password' ? 'password' : field.kind === 'url' ? 'url' : 'text'}
          value={sharedProps.value}
          onChange={(event) => sharedProps.onChange(event.target.value)}
          placeholder={translateSettingsCatalogText(locale, sharedProps.placeholder)}
          disabled={sharedProps.disabled}
          className={sharedProps.className}
        />
      )}
      <div className="mt-3">
        <FieldHelp field={field} locale={locale} />
      </div>
    </div>
  )
}

function connectorAnchorId(name: ConnectorName) {
  return `connector-${name}`
}

function connectorSectionAnchorId(name: ConnectorName, sectionId: string) {
  return `${connectorAnchorId(name)}-section-${sectionId}`
}

function connectorGuideStepAnchorId(name: ConnectorName, stepId: string) {
  return `${connectorAnchorId(name)}-step-${stepId}`
}

function lingzhuStepAnchorId(step: 'endpoint' | 'platform' | 'probe' | 'advanced') {
  return `connector-lingzhu-step-${step}`
}

function findConnectorField(entry: ConnectorCatalogEntry, key: string) {
  for (const section of entry.sections) {
    const match = section.fields.find((field) => field.key === key)
    if (match) {
      return match
    }
  }
  return null
}

function findConnectorFields(entry: ConnectorCatalogEntry, keys: string[]) {
  return keys
    .map((key) => findConnectorField(entry, key))
    .filter(Boolean) as ConnectorField[]
}

function connectorFieldReady(field: ConnectorField | null, raw: unknown) {
  if (!field) {
    return String(raw || '').trim().length > 0
  }
  if (field.kind === 'boolean') {
    return typeof raw === 'boolean'
  }
  if (field.kind === 'list') {
    return Array.isArray(raw) ? raw.length > 0 : String(raw || '').trim().length > 0
  }
  return String(raw || '').trim().length > 0
}

function missingConnectorFields(entry: ConnectorCatalogEntry, keys: string[], config: Record<string, unknown>) {
  return findConnectorFields(entry, keys).filter((field) => !connectorFieldReady(field, config[field.key]))
}

function AnchorJumpButton({
  anchorId,
  onJumpToAnchor,
}: {
  anchorId: string
  onJumpToAnchor?: (anchorId: string) => void
}) {
  return (
    <button
      type="button"
      onClick={() => onJumpToAnchor?.(anchorId)}
      title={`#${anchorId}`}
      className="inline-flex h-7 min-w-7 items-center justify-center rounded-full border border-black/[0.08] bg-white/[0.44] px-2 text-[11px] text-muted-foreground transition hover:text-foreground dark:border-white/[0.12] dark:bg-white/[0.03]"
    >
      #
    </button>
  )
}

function StepStateBadge({
  state,
  locale,
}: {
  state: 'done' | 'current' | 'pending'
  locale: Locale
}) {
  const t = copy[locale]
  const label = state === 'done' ? t.qqStepDone : state === 'current' ? t.qqStepCurrent : t.qqStepPending
  return (
    <span
      className={cn(
        'rounded-full px-2.5 py-1 text-[10px] uppercase tracking-[0.14em]',
        state === 'done' && 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
        state === 'current' && 'bg-sky-500/10 text-sky-700 dark:text-sky-300',
        state === 'pending' && 'bg-black/[0.05] text-muted-foreground dark:bg-white/[0.06]'
      )}
    >
      {label}
    </span>
  )
}

function StepBlockerNotice({
  locale,
  description,
  fields,
}: {
  locale: Locale
  description: string
  fields?: ConnectorField[]
}) {
  const t = copy[locale]

  return (
    <div className="mt-5 rounded-[22px] border border-amber-500/25 bg-amber-500/8 px-4 py-4 dark:border-amber-300/20 dark:bg-amber-300/8">
      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-800 dark:text-amber-200">{t.blockedTitle}</div>
      <div className="mt-2 text-sm leading-6 text-amber-900 dark:text-amber-100">{description}</div>
      {fields?.length ? (
        <div className="mt-4">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-800/80 dark:text-amber-200/80">{t.missingFields}</div>
          <div className="mt-2 flex flex-wrap gap-2">
            {fields.map((field) => (
              <span
                key={field.key}
                className="rounded-full border border-amber-500/25 bg-white/70 px-3 py-1 text-xs text-amber-900 dark:border-amber-300/20 dark:bg-white/[0.05] dark:text-amber-100"
              >
                {translateSettingsCatalogText(locale, field.label)}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  )
}

function ConnectorGuideLinkButton({
  link,
  locale,
  className,
}: {
  link: ConnectorGuideLink
  locale: Locale
  className?: string
}) {
  const label = localizedGuideText(locale, link.label)
  const sharedClassName = cn(
    'inline-flex items-center gap-2 rounded-full border border-black/[0.08] bg-white/[0.52] px-3 py-2 text-sm transition hover:border-black/[0.14] hover:text-foreground dark:border-white/[0.12] dark:bg-white/[0.04]',
    className
  )

  if (link.kind === 'external') {
    return (
      <a href={link.href} target="_blank" rel="noreferrer" className={sharedClassName}>
        <ArrowUpRight className="h-4 w-4" />
        {label}
      </a>
    )
  }

  return (
    <Link to={connectorGuideDocHref(locale, link)} className={sharedClassName}>
      <BookOpenText className="h-4 w-4" />
      {label}
    </Link>
  )
}

function ConnectorGuideImageCard({
  image,
  locale,
}: {
  image: NonNullable<ConnectorGuideStep['image']>
  locale: Locale
}) {
  return (
    <div className="overflow-hidden rounded-[22px] border border-black/[0.08] bg-white/[0.52] dark:border-white/[0.12] dark:bg-white/[0.04]">
      <img
        src={getDocAssetUrl(image.assetPath)}
        alt={localizedGuideText(locale, image.alt)}
        className="block w-full bg-white object-cover"
        loading="lazy"
      />
      {image.caption ? (
        <div className="border-t border-black/[0.06] px-4 py-3 text-xs leading-5 text-muted-foreground dark:border-white/[0.08]">
          {localizedGuideText(locale, image.caption)}
        </div>
      ) : null}
    </div>
  )
}

type GuidedStepView = ConnectorGuideStep & {
  index: number
  state: 'done' | 'current' | 'pending'
}

type QqDraftProfile = {
  profile_id: string
  bot_name: string
  app_id: string
  app_secret: string
}

function slugifyQqProfileSeed(value: string) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

function resolveQqProfileIdSeed(item: Record<string, unknown>, index: number) {
  const explicitProfileId = String(item.profile_id || '').trim()
  if (explicitProfileId) {
    return explicitProfileId
  }
  const appId = String(item.app_id || '').trim()
  if (appId) {
    return `qq-${appId}`
  }
  const botName = slugifyQqProfileSeed(String(item.bot_name || '').trim())
  if (botName) {
    return `qq-profile-${botName}`
  }
  return `qq-profile-${index + 1}`
}

function createQqDraftProfile(): QqDraftProfile {
  const randomSuffix =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(36).slice(2, 10)
  return {
    profile_id: `qq-profile-${randomSuffix}`,
    bot_name: 'DeepScientist',
    app_id: '',
    app_secret: '',
  }
}

function normalizeQqProfilesConfig(config: Record<string, unknown>) {
  const rawProfiles = Array.isArray(config.profiles) ? config.profiles.filter((item) => item && typeof item === 'object') : []
  const usedProfileIds = new Set<string>()
  const normalizeProfile = (item: Record<string, unknown>, index: number) => {
    let profileId = resolveQqProfileIdSeed(item, index)
    let suffix = 2
    while (usedProfileIds.has(profileId)) {
      profileId = `${resolveQqProfileIdSeed(item, index)}-${suffix}`
      suffix += 1
    }
    usedProfileIds.add(profileId)
    return {
      profile_id: profileId,
      bot_name: String(item.bot_name || config.bot_name || 'DeepScientist').trim() || 'DeepScientist',
      app_id: String(item.app_id || '').trim(),
      app_secret: String(item.app_secret || '').trim(),
      main_chat_id: String(item.main_chat_id || '').trim(),
    }
  }
  const profiles = rawProfiles
    .map((item) => item as Record<string, unknown>)
    .map((item, index) => normalizeProfile(item, index))
    .filter((item) => item.profile_id)
  if (profiles.length > 0) return profiles
  const legacyAppId = String(config.app_id || '').trim()
  const legacyAppSecret = String(config.app_secret || '').trim()
  const legacyMainChatId = String(config.main_chat_id || '').trim()
  if (legacyAppId || legacyAppSecret || legacyMainChatId) {
    return [
      normalizeProfile(
        {
          bot_name: String(config.bot_name || 'DeepScientist').trim() || 'DeepScientist',
          app_id: legacyAppId,
          app_secret: legacyAppSecret,
          main_chat_id: legacyMainChatId,
        },
        0
      ),
    ]
  }
  return []
}

const genericProfileConnectorNames = ['telegram', 'discord', 'slack', 'feishu', 'whatsapp'] as const
type GenericProfileConnectorName = (typeof genericProfileConnectorNames)[number]

const genericConnectorProfileDefaults: Record<GenericProfileConnectorName, Record<string, unknown>> = {
  telegram: {
    transport: 'polling',
    bot_name: 'DeepScientist',
    bot_token: '',
  },
  discord: {
    transport: 'gateway',
    bot_name: 'DeepScientist',
    bot_token: '',
    application_id: '',
  },
  slack: {
    transport: 'socket_mode',
    bot_name: 'DeepScientist',
    bot_token: '',
    bot_user_id: '',
    app_token: '',
  },
  feishu: {
    transport: 'long_connection',
    bot_name: 'DeepScientist',
    app_id: '',
    app_secret: '',
    api_base_url: 'https://open.feishu.cn',
  },
  whatsapp: {
    transport: 'local_session',
    bot_name: 'DeepScientist',
    auth_method: 'qr_browser',
    session_dir: '',
  },
}

const genericConnectorProfileFieldKeys: Record<GenericProfileConnectorName, string[]> = {
  telegram: ['transport', 'bot_name', 'bot_token'],
  discord: ['transport', 'bot_name', 'bot_token', 'application_id'],
  slack: ['transport', 'bot_name', 'bot_token', 'bot_user_id', 'app_token'],
  feishu: ['transport', 'bot_name', 'app_id', 'app_secret', 'api_base_url'],
  whatsapp: ['transport', 'bot_name', 'auth_method', 'session_dir'],
}

function isGenericProfileConnectorName(value: ConnectorName): value is GenericProfileConnectorName {
  return (genericProfileConnectorNames as readonly string[]).includes(value)
}

function createGenericProfileId(name: GenericProfileConnectorName) {
  const randomSuffix =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(36).slice(2, 10)
  return `${name}-profile-${randomSuffix}`
}

function genericProfileLabel(connectorName: GenericProfileConnectorName, profile: Record<string, unknown>) {
  const text = (value: unknown) => String(value || '').trim()
  const candidates =
    connectorName === 'telegram'
      ? [text(profile.bot_name)]
      : connectorName === 'discord'
        ? [text(profile.bot_name), text(profile.application_id)]
        : connectorName === 'slack'
        ? [text(profile.bot_name), text(profile.bot_user_id)]
        : connectorName === 'feishu'
          ? [text(profile.bot_name), text(profile.app_id)]
          : [text(profile.bot_name), text(profile.session_dir)]
  const filtered = candidates.filter(Boolean)
  return filtered.length ? filtered.join(' · ') : connectorName
}

function normalizeGenericProfilesConfig(
  connectorName: GenericProfileConnectorName,
  config: Record<string, unknown>
) {
  const defaults = genericConnectorProfileDefaults[connectorName]
  const fieldKeys = genericConnectorProfileFieldKeys[connectorName]
  const rawProfiles = Array.isArray(config.profiles) ? config.profiles.filter((item) => item && typeof item === 'object') : []
  const normalizeProfile = (item: Record<string, unknown>, index: number) => {
    const profileId = String(item.profile_id || `${connectorName}-profile-${index + 1}`).trim() || `${connectorName}-profile-${index + 1}`
    const nextProfile: Record<string, unknown> = {
      profile_id: profileId,
      enabled: item.enabled !== false,
    }
    for (const key of fieldKeys) {
      const fallback = defaults[key]
      const rawValue = item[key] ?? config[key] ?? fallback ?? ''
      nextProfile[key] = typeof rawValue === 'boolean' ? rawValue : String(rawValue || '').trim()
    }
    if (connectorName === 'whatsapp' && !String(nextProfile.session_dir || '').trim()) {
      nextProfile.session_dir = `~/.deepscientist/connectors/whatsapp/${profileId}`
    }
    return nextProfile
  }
  const profiles = rawProfiles.map((item, index) => normalizeProfile(item as Record<string, unknown>, index))
  if (profiles.length > 0) return profiles
  const hasLegacyValue = fieldKeys.some((key) => String(config[key] || '').trim().length > 0)
  if (!hasLegacyValue) return []
  return [normalizeProfile(config, 0)]
}

function createGenericProfileDraft(
  connectorName: GenericProfileConnectorName,
  config: Record<string, unknown>
): Record<string, unknown> {
  const profileId = createGenericProfileId(connectorName)
  const defaults = genericConnectorProfileDefaults[connectorName]
  const draft: Record<string, unknown> = {
    profile_id: profileId,
  }
  for (const [key, value] of Object.entries(defaults)) {
    const fallback = key === 'session_dir' && connectorName === 'whatsapp' ? `~/.deepscientist/connectors/whatsapp/${profileId}` : value
    const currentValue = config[key]
    draft[key] = typeof currentValue === 'string' && currentValue.trim().length > 0 ? currentValue : fallback
  }
  return draft
}

function ConnectorTargetList({
  locale,
  targets,
  emptyText,
  showBindingDetails = true,
}: {
  locale: Locale
  targets: ConnectorTargetSnapshot[]
  emptyText: string
  showBindingDetails?: boolean
}) {
  const t = copy[locale]

  if (targets.length === 0) {
    return (
      <div className="rounded-[20px] border border-dashed border-black/[0.12] bg-white/[0.5] px-4 py-4 text-sm text-muted-foreground dark:border-white/[0.12] dark:bg-white/[0.04]">
        {emptyText}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {targets.map((target) => (
        <div
          key={target.conversation_id}
          className="rounded-[20px] border border-black/[0.06] bg-white/[0.62] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.04]"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-sm font-medium text-foreground">{connectorTargetLabel(target)}</div>
              <div className="mt-1 break-all font-mono text-xs text-muted-foreground">{target.conversation_id}</div>
            </div>
            <div className="flex shrink-0 flex-wrap justify-end gap-2">
              {target.is_default ? <Badge variant="default">{t.defaultTarget}</Badge> : null}
              {showBindingDetails && target.is_bound ? <Badge variant="secondary">{t.boundTarget}</Badge> : null}
            </div>
          </div>
          <div
            className={cn(
              'mt-3 grid gap-2 text-xs text-muted-foreground',
              showBindingDetails ? 'md:grid-cols-3' : 'md:grid-cols-2'
            )}
          >
            <div>
              <span className="text-foreground">{t.chatType}:</span> {target.chat_type || '—'}
            </div>
            <div>
              <span className="text-foreground">{t.lastSeen}:</span> {target.updated_at || '—'}
            </div>
            {showBindingDetails ? (
              <div>
                <span className="text-foreground">{t.boundQuestLabel}:</span>{' '}
                {target.bound_quest_id
                  ? `${target.bound_quest_id}${target.bound_quest_title ? ` · ${target.bound_quest_title}` : ''}`
                  : t.notBoundYet}
              </div>
            ) : null}
          </div>
          {showBindingDetails && target.warning ? (
            <div className="mt-3 text-xs text-amber-700 dark:text-amber-300">{target.warning}</div>
          ) : null}
        </div>
      ))}
    </div>
  )
}

function ConnectorOverviewCard({
  entry,
  locale,
  config,
  onOpenConnector,
}: {
  entry: ConnectorCatalogEntry
  locale: Locale
  config: Record<string, unknown>
  onOpenConnector: (connectorName: ConnectorName) => void
}) {
  const t = copy[locale]
  const Icon = entry.icon
  const enabled = Boolean(config.enabled)
  const needsPublicNetwork = entry.name === 'lingzhu'
  const publicRequirementLabel =
    locale === 'zh'
      ? needsPublicNetwork
        ? '公网：需要'
        : '公网：不需要'
      : needsPublicNetwork
        ? 'Public: required'
        : 'Public: not needed'

  return (
    <article className="rounded-[28px] border border-black/[0.08] bg-white/[0.5] p-5 dark:border-white/[0.12] dark:bg-white/[0.03]">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-[16px] border border-black/[0.08] bg-white/[0.56] dark:border-white/[0.12] dark:bg-white/[0.04]">
            <Icon className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h3 className="text-lg font-semibold tracking-tight">{translateSettingsCatalogText(locale, entry.label)}</h3>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span>{enabled ? t.enabled : t.disabled}</span>
              <span>{publicRequirementLabel}</span>
            </div>
          </div>
        </div>

        <Button onClick={() => onOpenConnector(entry.name)} className="shrink-0">
          {t.openConnector}
        </Button>
      </div>
    </article>
  )
}

function ConnectorCard({
  entry,
  locale,
  config,
  snapshot,
  saving,
  isDirty,
  onUpdateField,
  onUpdateConnector,
  onSave,
  onJumpToAnchor,
}: {
  entry: ConnectorCatalogEntry
  locale: Locale
  config: Record<string, unknown>
  snapshot?: ConnectorSnapshot
  saving: boolean
  isDirty: boolean
  onUpdateField: (connectorName: ConnectorName, key: string, value: unknown) => void
  onUpdateConnector: (connectorName: ConnectorName, patch: Record<string, unknown>) => void
  onSave: () => void
  onJumpToAnchor?: (anchorId: string) => void
}) {
  const t = copy[locale]
  const Icon = entry.icon
  const enabled = Boolean(config.enabled)
  const guide = connectorGuideCatalog[entry.name]
  const [legacyExpanded, setLegacyExpanded] = useState(false)
  const [qqWizardOpen, setQqWizardOpen] = useState(false)
  const [qqWizardStep, setQqWizardStep] = useState<1 | 2 | 3>(1)
  const [qqWizardProfileId, setQqWizardProfileId] = useState<string | null>(null)
  const [qqWizardDraft, setQqWizardDraft] = useState<QqDraftProfile>(() => createQqDraftProfile())
  const [qqWizardPendingSaveProfileId, setQqWizardPendingSaveProfileId] = useState<string | null>(null)
  const [guidedWizardOpen, setGuidedWizardOpen] = useState(false)
  const [guidedWizardStep, setGuidedWizardStep] = useState(1)
  const [lingzhuWizardOpen, setLingzhuWizardOpen] = useState(false)
  const [lingzhuWizardStep, setLingzhuWizardStep] = useState<1 | 2 | 3>(1)
  const [profileWizardOpen, setProfileWizardOpen] = useState(false)
  const [profileWizardStep, setProfileWizardStep] = useState<1 | 2 | 3>(1)
  const [profileWizardProfileId, setProfileWizardProfileId] = useState<string | null>(null)
  const [profileWizardDraft, setProfileWizardDraft] = useState<Record<string, unknown>>({})
  const cardAnchorId = connectorAnchorId(entry.name)
  const useCompactGuidedLayout = entry.name !== 'qq'
  const connectorModalClassName = 'w-[min(92vw,1100px)] max-w-[calc(100vw-1.5rem)] overflow-y-auto lg:w-[50vw]'

  useEffect(() => {
    if (entry.name !== 'qq' || !qqWizardPendingSaveProfileId || saving) {
      return
    }
    const normalizedQqConfig =
      config && typeof config === 'object' ? (config as Record<string, unknown>) : {}
    const hasPendingProfile = normalizeQqProfilesConfig(normalizedQqConfig).some(
      (profile) => profile.profile_id === qqWizardPendingSaveProfileId
    )
    if (!hasPendingProfile) {
      return
    }
    setQqWizardPendingSaveProfileId(null)
    onSave()
  }, [config, entry.name, onSave, qqWizardPendingSaveProfileId, saving])

  const renderGuidedSetup = () => {
    const missingRequiredFields = missingConnectorFields(entry, guide.requiredFieldKeys, config)
    const requiredReady = missingRequiredFields.length === 0
    const settingsReady = Boolean(enabled && requiredReady)
    const savedReady = Boolean(settingsReady && !isDirty)
    const targets = snapshot ? normalizeConnectorTargets(snapshot) : []
    const interactionReady = Boolean(targets.length > 0 || snapshot?.main_chat_id)
    const verificationReady = interactionReady
    const stepSummaries: GuidedStepView[] = guide.steps.map((step, index) => {
      const state: 'done' | 'current' | 'pending' =
        index === 0
          ? requiredReady
            ? 'done'
            : 'current'
          : index < guide.steps.length - 1
            ? !requiredReady
              ? 'pending'
              : savedReady
                ? 'done'
                : 'current'
            : !savedReady
              ? 'pending'
              : verificationReady
                ? 'done'
                : 'current'
      return {
        ...step,
        index,
        state,
      }
    })
    const nextStep = stepSummaries.find((step) => step.state !== 'done') || stepSummaries[stepSummaries.length - 1]
    const maxReachableStep = savedReady ? stepSummaries.length : Math.min(stepSummaries.length, 2)
    const verifyBlockedDescription = !savedReady ? t.saveConnectorFirst : !interactionReady ? t.sendPlatformMessageFirst : ''
    const activeWizardStep =
      stepSummaries[Math.min(Math.max(guidedWizardStep, 1), stepSummaries.length) - 1] || null
    const activeStepFields = activeWizardStep ? findConnectorFields(entry, activeWizardStep.fieldKeys || []) : []
    const activeStepLinks =
      activeWizardStep && activeWizardStep.links && activeWizardStep.links.length > 0
        ? activeWizardStep.links
        : activeWizardStep?.index === 0
          ? guide.links
          : []

    const openWizard = () => {
      setGuidedWizardStep((nextStep?.index || 0) + 1)
      setGuidedWizardOpen(true)
    }

    return (
      <div className="space-y-5">
        <section className="rounded-[24px] border border-black/[0.08] bg-white/[0.48] p-5 dark:border-white/[0.12] dark:bg-white/[0.03]">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.bindConnectorTitle}</div>
              <h4 className="mt-2 text-lg font-semibold tracking-tight">{localizedGuideText(locale, guide.summary)}</h4>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">{translateSettingsCatalogText(locale, entry.subtitle)}</p>
            </div>
            {nextStep ? <StepStateBadge state={nextStep.state} locale={locale} /> : null}
          </div>

          <div className="mt-5 grid gap-3 lg:grid-cols-3">
            {stepSummaries.map((step) => (
              <div
                key={`summary:${step.id}`}
                className="rounded-[20px] border border-black/[0.06] bg-white/[0.62] px-4 py-3 dark:border-white/[0.08] dark:bg-white/[0.04]"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                    Step {step.index + 1}
                  </span>
                  <StepStateBadge state={step.state} locale={locale} />
                </div>
                <div className="mt-2 text-sm font-medium text-foreground">{localizedGuideText(locale, step.title)}</div>
              </div>
            ))}
          </div>

          {nextStep ? (
            <div className="mt-5 rounded-[20px] border border-black/[0.06] bg-black/[0.02] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.03]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.nextAction}</div>
              <div className="mt-2 text-sm font-medium text-foreground">{localizedGuideText(locale, nextStep.title)}</div>
              <div className="mt-1 text-sm leading-6 text-muted-foreground">{localizedGuideText(locale, nextStep.description)}</div>
              {nextStep.id === 'platform' && missingRequiredFields.length ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  {missingRequiredFields.map((field) => (
                    <span
                      key={`missing:${field.key}`}
                      className="rounded-full border border-black/[0.08] bg-white/[0.58] px-3 py-1.5 text-xs dark:border-white/[0.12] dark:bg-white/[0.04]"
                    >
                      {translateSettingsCatalogText(locale, field.label)}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
          <div className="mt-5 flex flex-wrap gap-2">
            {guide.links.map((link) => (
              <ConnectorGuideLinkButton
                key={`guide-link:${link.kind}:${localizedGuideText(locale, link.label)}`}
                link={link}
                locale={locale}
              />
            ))}
          </div>

          <div className="mt-5 flex flex-col gap-3 rounded-[20px] border border-black/[0.06] bg-black/[0.02] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.03] md:flex-row md:items-center md:justify-between">
            <div className="text-sm text-muted-foreground">
              {nextStep ? localizedGuideText(locale, nextStep.description) : localizedGuideText(locale, guide.summary)}
            </div>
            <Button
              size="lg"
              className="rounded-full px-6"
              onClick={openWizard}
            >
              <RadioTower className="h-4 w-4" />
              {t.openGuidedSetup}
            </Button>
          </div>
        </section>

        <section className="rounded-[24px] border border-black/[0.08] bg-white/[0.48] p-5 dark:border-white/[0.12] dark:bg-white/[0.03]">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.boundTargetsTitle}</div>
              <h4 className="mt-2 text-lg font-semibold tracking-tight">{t.discoveredTargets}</h4>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">{t.boundTargetsHint}</p>
            </div>
            <Badge variant="secondary" className="shrink-0">
              {targets.length}
            </Badge>
          </div>

          <div className="mt-5">
            <ConnectorTargetList locale={locale} targets={targets} emptyText={t.noTargets} showBindingDetails={false} />
          </div>
        </section>

        <Modal
          open={guidedWizardOpen}
          onClose={() => setGuidedWizardOpen(false)}
          title={`${translateSettingsCatalogText(locale, entry.label)} Connector`}
          description={localizedGuideText(locale, guide.summary)}
          size="xl"
          className={connectorModalClassName}
        >
          <div className="space-y-5">
            <div className="grid gap-3 md:grid-cols-3">
              {stepSummaries.map((step) => (
                <button
                  key={`guided-wizard-step:${step.id}`}
                  type="button"
                  onClick={() => {
                    if (step.index + 1 <= maxReachableStep) {
                      setGuidedWizardStep(step.index + 1)
                    }
                  }}
                  disabled={step.index + 1 > maxReachableStep}
                  className={cn(
                    'rounded-[18px] border px-4 py-3 text-left disabled:cursor-not-allowed disabled:opacity-60',
                    guidedWizardStep === step.index + 1
                      ? 'border-black/[0.14] bg-black/[0.04] dark:border-white/[0.18] dark:bg-white/[0.05]'
                      : 'border-black/[0.08] bg-white/[0.52] dark:border-white/[0.08] dark:bg-white/[0.03]'
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                      Step {step.index + 1}
                    </span>
                    <StepStateBadge state={step.state} locale={locale} />
                  </div>
                  <div className="mt-2 text-sm font-medium text-foreground">{localizedGuideText(locale, step.title)}</div>
                </button>
              ))}
            </div>

            {activeWizardStep ? (
              <div className="space-y-5 pt-2">
                <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                      Step {activeWizardStep.index + 1}
                    </div>
                    <h4 className="mt-2 text-lg font-semibold tracking-tight">
                      {localizedGuideText(locale, activeWizardStep.title)}
                    </h4>
                    <p className="mt-1 text-sm leading-6 text-muted-foreground">
                      {localizedGuideText(locale, activeWizardStep.description)}
                    </p>
                  </div>
                  <StepStateBadge state={activeWizardStep.state} locale={locale} />
                </div>

                {activeStepLinks.length ? (
                  <div className="flex flex-wrap gap-2">
                    {activeStepLinks.map((link) => (
                      <ConnectorGuideLinkButton
                        key={`${activeWizardStep.id}:${link.kind}:${localizedGuideText(locale, link.label)}`}
                        link={link}
                        locale={locale}
                      />
                    ))}
                  </div>
                ) : null}

                {activeWizardStep.image ? <ConnectorGuideImageCard image={activeWizardStep.image} locale={locale} /> : null}

                {activeWizardStep.checklist?.length ? (
                  <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.stepChecklist}</div>
                    <ol className="mt-3 space-y-2 text-sm leading-6 text-muted-foreground">
                      {activeWizardStep.checklist.map((item, checklistIndex) => (
                        <li key={`${activeWizardStep.id}:${checklistIndex}`}>
                          {checklistIndex + 1}. {localizedGuideText(locale, item)}
                        </li>
                      ))}
                    </ol>
                  </div>
                ) : null}

                {activeWizardStep.id === 'settings' && !settingsReady ? (
                  <StepBlockerNotice locale={locale} description={t.enableConnectorFirst} fields={missingRequiredFields} />
                ) : null}

                {activeWizardStep.id === 'verify' && verifyBlockedDescription ? (
                  <StepBlockerNotice locale={locale} description={verifyBlockedDescription} />
                ) : null}

                {activeWizardStep.includeEnabledToggle || activeStepFields.length ? (
                  <div>
                    <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.stepFields}</div>
                    <div className="grid gap-4 md:grid-cols-2">
                      {activeWizardStep.includeEnabledToggle ? (
                        <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
                          <label className="flex min-h-[44px] items-center justify-between gap-4">
                            <span className="text-sm font-medium">{t.enabled}</span>
                            <input
                              type="checkbox"
                              checked={enabled}
                              onChange={(event) => onUpdateField(entry.name, 'enabled', event.target.checked)}
                              className="h-4 w-4 rounded border-black/20 text-foreground"
                            />
                          </label>
                          <div className="mt-3 text-xs leading-5 text-muted-foreground">
                            {translateSettingsCatalogText(locale, entry.deliveryNote)}
                          </div>
                        </div>
                      ) : null}
                      {activeStepFields.map((field) => (
                        <ConnectorFieldControl
                          key={`${activeWizardStep.id}:${field.key}`}
                          field={field}
                          config={config}
                          locale={locale}
                          onChange={(key, value) => onUpdateField(entry.name, key, value)}
                        />
                      ))}
                    </div>
                  </div>
                ) : null}

                {activeWizardStep.id === 'verify' ? (
                  <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
                    <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
                      <div className="flex items-center gap-2 text-sm font-medium">
                        <MessageSquareText className="h-4 w-4 text-muted-foreground" />
                        <span>{t.discoveredTargets}</span>
                      </div>
                      <div className="mt-2 text-xs leading-5 text-muted-foreground">{t.useDiscoveredTargets}</div>
                      <div className="mt-4">
                        <ConnectorTargetList locale={locale} targets={targets} emptyText={t.noTargets} showBindingDetails={false} />
                      </div>
                    </div>
                    <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
                      <div className="text-sm font-medium">{t.snapshot}</div>
                      <div className="mt-2 text-xs leading-5 text-muted-foreground">{t.stepProbeHint}</div>
                      <div className="mt-4 space-y-2 text-sm text-muted-foreground">
                        <div>
                          <span className="text-foreground">{t.transportLabel}:</span>{' '}
                          {translateSettingsCatalogText(locale, snapshot?.transport || snapshot?.display_mode || snapshot?.mode || 'default')}
                        </div>
                        <div>
                          <span className="text-foreground">{t.connection}:</span>{' '}
                          {translateSettingsCatalogText(locale, snapshot?.connection_state || 'idle')}
                        </div>
                        <div>
                          <span className="text-foreground">{t.auth}:</span>{' '}
                          {translateSettingsCatalogText(locale, snapshot?.auth_state || 'idle')}
                        </div>
                        <div>
                          <span className="text-foreground">{t.discoveredTargets}:</span> {targets.length}
                        </div>
                        {interactionReady ? (
                          <div className="text-emerald-700 dark:text-emerald-300">{t.ok}</div>
                        ) : (
                          <div>{t.noTargets}</div>
                        )}
                      </div>
                    </div>
                  </div>
                ) : null}

              </div>
            ) : null}

            <ModalFooter className="-mx-6 -mb-4 mt-2">
              <Button variant="secondary" onClick={() => setGuidedWizardOpen(false)}>
                {t.wizardClose}
              </Button>
              {guidedWizardStep > 1 ? (
                <Button variant="secondary" onClick={() => setGuidedWizardStep((current) => Math.max(1, current - 1))}>
                  {t.wizardBack}
                </Button>
              ) : null}
              {guidedWizardStep < stepSummaries.length ? (
                <Button
                  onClick={() => {
                    if (activeWizardStep?.id === 'settings') {
                      onSave()
                    }
                    setGuidedWizardStep((current) => Math.min(stepSummaries.length, current + 1))
                  }}
                  disabled={
                    saving ||
                    (activeWizardStep?.id === 'settings' && !settingsReady) ||
                    (activeWizardStep?.id === 'verify' && !verificationReady)
                  }
                >
                  {activeWizardStep?.id === 'settings'
                    ? saving
                      ? t.saving
                      : t.stepSaveAction
                    : t.wizardContinue}
                </Button>
              ) : (
                <Button
                  onClick={() => {
                    if (isDirty) {
                      onSave()
                    }
                    setGuidedWizardOpen(false)
                  }}
                  disabled={saving}
                >
                  {saving ? t.saving : isDirty ? t.save : t.wizardDone}
                </Button>
              )}
            </ModalFooter>
          </div>
        </Modal>
      </div>
    )
  }

  const renderQqSetup = () => {
    const qqCopy = {
      bots: locale === 'zh' ? 'QQ 机器人' : 'QQ bots',
      configured: locale === 'zh' ? '已配置的 QQ Connector' : 'Configured QQ connectors',
      configuredHint:
        locale === 'zh'
          ? '每一个 QQ bot 都是独立的。新增时始终从空白表单开始，不会覆盖已有 bot 的凭据。'
          : 'Each QQ bot is independent. Adding a new one always starts from an empty form and never edits the existing bot credentials.',
      empty: locale === 'zh' ? '当前还没有添加任何 QQ bot。' : 'No QQ bot has been added yet.',
      addBot: locale === 'zh' ? '新增 QQ Bot' : 'Add QQ bot',
      createConnector: locale === 'zh' ? '创建 QQ Connector' : 'Create QQ Connector',
      createHint:
        locale === 'zh'
          ? '先保存 App ID 和 App Secret，再从 QQ 给该 bot 发送一条私聊，DeepScientist 就会自动检测 OpenID。'
          : 'Save App ID and App Secret first. Then send one private QQ message to that bot and DeepScientist will detect the OpenID automatically.',
      waiting: locale === 'zh' ? '等待绑定' : 'Waiting',
      bound: locale === 'zh' ? '已绑定' : 'Bound',
      profileId: locale === 'zh' ? 'Profile ID' : 'Profile ID',
      currentBot: locale === 'zh' ? '当前 Bot' : 'Current bot',
      savedTargets: locale === 'zh' ? '已保存的 QQ 目标' : 'Saved QQ targets',
      bindNotice:
        locale === 'zh'
          ? '当第一条私聊到达后，DeepScientist 会自动保存 OpenID，并且 QQ bot 会在该会话里回复绑定成功提示。'
          : 'After the first private message arrives, DeepScientist saves the OpenID automatically and the QQ bot replies with a binding-success notice in that same chat.',
      botName: locale === 'zh' ? 'Bot 名称' : 'Bot name',
      close: locale === 'zh' ? '关闭' : 'Close',
      back: locale === 'zh' ? '返回' : 'Back',
      continue: locale === 'zh' ? '继续' : 'Continue',
      next: locale === 'zh' ? '下一步' : 'Next',
      done: locale === 'zh' ? '完成' : 'Done',
    }
    const qqProfiles = normalizeQqProfilesConfig(config)
    const qqGuide = connectorGuideCatalog.qq
    const qqPlatformStep = qqGuide.steps.find((step) => step.id === 'platform') || qqGuide.steps[0]
    const qqBindStep = qqGuide.steps.find((step) => step.id === 'bind') || qqGuide.steps[2] || qqGuide.steps[0]
    const qqPlatformLink = qqGuide.links.find((link) => link.kind === 'external') || null
    const profileSnapshots = new Map((snapshot?.profiles || []).map((item) => [item.profile_id, item]))
    const allQqTargets = normalizeConnectorTargets(
      snapshot || ({
        name: entry.name,
        discovered_targets: [],
        recent_conversations: [],
        bindings: [],
      } as ConnectorSnapshot)
    )
    const targetMatchesProfile = (target: ConnectorTargetSnapshot, profileId: string) =>
      String(target.profile_id || '').trim() === profileId || (!String(target.profile_id || '').trim() && qqProfiles.length === 1)
    const activeProfileSnapshot =
      (qqWizardProfileId ? profileSnapshots.get(qqWizardProfileId) : null) || null
    const activeProfileTargets = qqWizardProfileId ? allQqTargets.filter((item) => targetMatchesProfile(item, qqWizardProfileId)) : []
    const hasDetectedTarget = Boolean(activeProfileSnapshot?.main_chat_id || activeProfileTargets.length > 0)
    const qqMissingFields = [qqWizardDraft.bot_name, qqWizardDraft.app_id, qqWizardDraft.app_secret].some((item) => !String(item || '').trim())
    const maxReachableStep = qqMissingFields ? 1 : hasDetectedTarget ? 3 : 2
    const stepState = {
      1: qqMissingFields ? 'current' : 'done',
      2: qqMissingFields ? 'pending' : hasDetectedTarget ? 'done' : 'current',
      3: qqMissingFields ? 'pending' : hasDetectedTarget ? 'current' : 'pending',
    } as const

    const openQqWizard = () => {
      const nextDraft = createQqDraftProfile()
      setQqWizardDraft(nextDraft)
      setQqWizardProfileId(nextDraft.profile_id)
      setQqWizardStep(1)
      setQqWizardPendingSaveProfileId(null)
      setQqWizardOpen(true)
    }

    const saveNewQqProfile = () => {
      const nextProfile = {
        profile_id: qqWizardDraft.profile_id,
        bot_name: qqWizardDraft.bot_name.trim() || 'DeepScientist',
        app_id: qqWizardDraft.app_id.trim(),
        app_secret: qqWizardDraft.app_secret.trim(),
        app_secret_env: 'QQ_APP_SECRET',
        main_chat_id: null,
      }
      onUpdateConnector(entry.name, {
        enabled: true,
        profiles: [...qqProfiles, nextProfile],
      })
      setQqWizardPendingSaveProfileId(nextProfile.profile_id)
    }

    const closeQqWizard = () => {
      setQqWizardPendingSaveProfileId(null)
      setQqWizardOpen(false)
    }

    return (
      <div className="space-y-5">
        <section className="rounded-[24px] border border-black/[0.08] bg-white/[0.48] p-5 dark:border-white/[0.12] dark:bg-white/[0.03]">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{qqCopy.bots}</div>
              <h4 className="mt-2 text-lg font-semibold tracking-tight">{qqCopy.configured}</h4>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">
                {qqCopy.configuredHint}
              </p>
            </div>
            <Badge variant="secondary" className="shrink-0">
              {qqProfiles.length}
            </Badge>
          </div>

          <div className="mt-5 space-y-3">
            {qqProfiles.length === 0 ? (
              <div className="rounded-[20px] border border-dashed border-black/[0.12] bg-white/[0.5] px-4 py-4 text-sm text-muted-foreground dark:border-white/[0.12] dark:bg-white/[0.04]">
                {qqCopy.empty}
              </div>
            ) : (
              qqProfiles.map((profile) => {
                const profileSnapshot = profileSnapshots.get(profile.profile_id)
                const mainChatId = String(profileSnapshot?.main_chat_id || profile.main_chat_id || '').trim()
                const profileTargets = allQqTargets.filter((item) => targetMatchesProfile(item, profile.profile_id))
                const selectedTarget =
                  profileTargets.find((item) => item.chat_id === mainChatId) ||
                  profileTargets[0] ||
                  null
                return (
                <div
                  key={profile.profile_id}
                  className="rounded-[20px] border border-black/[0.06] bg-white/[0.62] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.04]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-foreground">{profile.bot_name || 'DeepScientist'}</div>
                      <div className="mt-1 break-all font-mono text-xs text-muted-foreground">{profile.app_id || '—'}</div>
                    </div>
                    <Badge variant={mainChatId ? 'default' : 'secondary'}>{mainChatId ? qqCopy.bound : qqCopy.waiting}</Badge>
                  </div>
                  <div className="mt-3 grid gap-2 text-xs text-muted-foreground md:grid-cols-3">
                    <div>
                      <span className="text-foreground">{qqCopy.profileId}:</span> {profile.profile_id}
                    </div>
                    <div>
                      <span className="text-foreground">{t.qqDetectedOpenId}:</span> {mainChatId || '—'}
                    </div>
                    <div>
                      <span className="text-foreground">{t.boundQuestLabel}:</span>{' '}
                      {selectedTarget?.bound_quest_id
                        ? `${selectedTarget.bound_quest_id}${selectedTarget.bound_quest_title ? ` · ${selectedTarget.bound_quest_title}` : ''}`
                        : t.notBoundYet}
                    </div>
                  </div>
                  {selectedTarget ? (
                    <div className="mt-3 rounded-[14px] border border-black/[0.06] bg-black/[0.02] px-3 py-2 text-xs text-muted-foreground dark:border-white/[0.08] dark:bg-white/[0.03]">
                      <div className="font-medium text-foreground">{connectorTargetLabel(selectedTarget)}</div>
                      <div className="mt-1 break-all font-mono">{selectedTarget.conversation_id}</div>
                    </div>
                  ) : null}
                </div>
                )
              })
            )}
          </div>
        </section>

        <section className="rounded-[24px] border border-black/[0.08] bg-white/[0.48] p-5 dark:border-white/[0.12] dark:bg-white/[0.03]">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{qqCopy.addBot}</div>
              <h4 className="mt-2 text-lg font-semibold tracking-tight">{qqCopy.createConnector}</h4>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">
                {qqCopy.createHint}
              </p>
            </div>
            <Button size="lg" className="rounded-full px-6" onClick={openQqWizard}>
              <RadioTower className="h-4 w-4" />
              {qqCopy.createConnector}
            </Button>
          </div>
        </section>

        <Modal
          open={qqWizardOpen}
          onClose={closeQqWizard}
          title={qqCopy.createConnector}
          description={
            locale === 'zh'
              ? 'Step 1 先打开 QQ 平台并填写 App ID / App Secret；Step 2 等待第一条 QQ 私聊；Step 3 确认检测到的 OpenID 并展示最终绑定结果。'
              : 'Step 1 opens the QQ platform first and fills App ID / App Secret. Step 2 waits for the first QQ private message. Step 3 confirms the detected OpenID and shows the final binding state.'
          }
          size="xl"
          className={connectorModalClassName}
        >
          <div className="space-y-5">
            <div className="grid gap-3 md:grid-cols-3">
              {[
                { step: 1 as const, title: t.qqStepPlatform, state: stepState[1] },
                { step: 2 as const, title: t.qqStepBind, state: stepState[2] },
                { step: 3 as const, title: t.qqStepSuccess, state: stepState[3] },
              ].map((item) => (
                <button
                  key={`qq-wizard-step:${item.step}`}
                  type="button"
                  onClick={() => {
                    if (item.step <= maxReachableStep) {
                      setQqWizardStep(item.step)
                    }
                  }}
                  disabled={item.step > maxReachableStep}
                  className={cn(
                    'rounded-[18px] border px-4 py-3 text-left disabled:cursor-not-allowed disabled:opacity-60',
                    qqWizardStep === item.step
                      ? 'border-black/[0.14] bg-black/[0.04] dark:border-white/[0.18] dark:bg-white/[0.05]'
                      : 'border-black/[0.08] bg-white/[0.52] dark:border-white/[0.08] dark:bg-white/[0.03]'
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Step {item.step}</span>
                    <StepStateBadge state={item.state} locale={locale} />
                  </div>
                  <div className="mt-2 text-sm font-medium text-foreground">{item.title}</div>
                </button>
              ))}
            </div>

            {qqWizardStep === 1 ? (
              <div className="space-y-4 pt-2">
                {qqPlatformLink ? (
                  <a
                    href={qqPlatformLink.href}
                    target="_blank"
                    rel="noreferrer"
                    className="flex w-full items-center justify-between gap-4 rounded-[20px] border border-black/[0.08] bg-white/[0.6] px-4 py-4 text-left transition hover:border-black/[0.14] hover:text-foreground dark:border-white/[0.12] dark:bg-white/[0.04]"
                  >
                    <div className="min-w-0">
                      <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                        {localizedGuideText(locale, qqPlatformLink.label)}
                      </div>
                      <div className="mt-2 break-all text-sm text-muted-foreground">{qqPlatformLink.href}</div>
                    </div>
                    <ArrowUpRight className="h-4 w-4 shrink-0" />
                  </a>
                ) : null}
                {qqPlatformStep?.image ? <ConnectorGuideImageCard image={qqPlatformStep.image} locale={locale} /> : null}
                <div className="rounded-[20px] border border-black/[0.06] bg-white/[0.62] p-4 text-sm text-muted-foreground dark:border-white/[0.08] dark:bg-white/[0.04]">
                  <div className="font-medium text-foreground">{localizedGuideText(locale, qqPlatformStep?.title) || t.qqStepPlatform}</div>
                  <div className="mt-2 leading-6">{localizedGuideText(locale, qqPlatformStep?.description)}</div>
                  <ol className="mt-3 space-y-2 leading-6">
                    <li>1. {t.qqPlatformChecklist1}</li>
                    <li>2. {t.qqPlatformChecklist2}</li>
                    <li>3. {t.qqPlatformChecklist3}</li>
                  </ol>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-[20px] border border-black/[0.06] bg-white/[0.62] p-4 dark:border-white/[0.08] dark:bg-white/[0.04]">
                    <label className="flex items-center justify-between gap-3">
                      <span className="text-sm font-medium">{t.enabled}</span>
                      <input
                        type="checkbox"
                        checked={enabled}
                        onChange={(event) => onUpdateField(entry.name, 'enabled', event.target.checked)}
                        className="h-4 w-4 rounded border-black/20 text-foreground"
                      />
                    </label>
                    <div className="mt-3 text-xs leading-5 text-muted-foreground">{t.qqPlatformHint}</div>
                  </div>
                  <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
                    <label className="flex items-center gap-2 text-sm font-medium">
                      <span>{qqCopy.botName}</span>
                    </label>
                    <Input
                      value={qqWizardDraft.bot_name}
                      onChange={(event) => setQqWizardDraft((current) => ({ ...current, bot_name: event.target.value }))}
                      placeholder="DeepScientist"
                      className="rounded-[18px] border-black/[0.08] bg-white/[0.44] shadow-none dark:bg-white/[0.03]"
                    />
                  </div>
                  <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
                    <label className="flex items-center gap-2 text-sm font-medium">
                      <span>App ID</span>
                    </label>
                    <Input
                      value={qqWizardDraft.app_id}
                      onChange={(event) => setQqWizardDraft((current) => ({ ...current, app_id: event.target.value }))}
                      placeholder="1903299925"
                      className="rounded-[18px] border-black/[0.08] bg-white/[0.44] shadow-none dark:bg-white/[0.03]"
                    />
                    <div className="mt-3 text-xs leading-5 text-muted-foreground">
                      {locale === 'zh'
                        ? '这里填写 QQ 平台控制台中的 App ID。通常在机器人或应用详情页可以直接复制。'
                        : 'Paste the App ID from the QQ platform console here. It is usually shown on the bot or application details page.'}
                    </div>
                  </div>
                  <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04] md:col-span-2">
                    <label className="flex items-center gap-2 text-sm font-medium">
                      <span>App Secret</span>
                    </label>
                    <Input
                      type="password"
                      value={qqWizardDraft.app_secret}
                      onChange={(event) => setQqWizardDraft((current) => ({ ...current, app_secret: event.target.value }))}
                      placeholder="QQ App Secret"
                      className="rounded-[18px] border-black/[0.08] bg-white/[0.44] shadow-none dark:bg-white/[0.03]"
                    />
                    <div className="mt-3 text-xs leading-5 text-muted-foreground">
                      {locale === 'zh'
                        ? '这里填写同一页面里的 App Secret。复制后立即保存，不要把 OpenID 填在这个步骤。'
                        : 'Paste the App Secret from the same console page here. Save it right away, and do not fill OpenID in this step.'}
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

            {qqWizardStep === 2 ? (
              <div className="space-y-4 pt-2">
                {qqBindStep?.image ? <ConnectorGuideImageCard image={qqBindStep.image} locale={locale} /> : null}
                <div className="rounded-[20px] border border-black/[0.06] bg-white/[0.62] p-4 text-sm text-muted-foreground dark:border-white/[0.08] dark:bg-white/[0.04]">
                  <div className="font-medium text-foreground">{localizedGuideText(locale, qqBindStep?.title) || t.qqStepBind}</div>
                  <div className="mt-2 leading-6">{localizedGuideText(locale, qqBindStep?.description)}</div>
                </div>
                <div className="rounded-[20px] border border-black/[0.06] bg-white/[0.62] p-4 text-sm text-muted-foreground dark:border-white/[0.08] dark:bg-white/[0.04]">
                  <div className="flex items-center gap-2 text-foreground">
                    <MessageSquareText className="h-4 w-4" />
                    <span className="font-medium">{t.qqBindChecklistTitle}</span>
                  </div>
                  <ol className="mt-3 space-y-2 leading-6">
                    <li>1. {t.qqBindChecklist1}</li>
                    <li>2. {t.qqBindChecklist2}</li>
                    <li>3. {t.qqBindChecklist3}</li>
                  </ol>
                </div>
                <div className="rounded-[20px] border border-black/[0.06] bg-white/[0.62] p-4 dark:border-white/[0.08] dark:bg-white/[0.04]">
                  <div className="text-sm font-medium text-foreground">{t.qqDetectedOpenId}</div>
                  <div className="mt-1 text-xs text-muted-foreground">{t.qqDetectedOpenIdHint}</div>
                  <div className="mt-3 rounded-[14px] border border-black/[0.06] bg-black/[0.02] px-4 py-3 font-mono text-sm dark:border-white/[0.08] dark:bg-white/[0.03]">
                    {activeProfileSnapshot?.main_chat_id || '—'}
                  </div>
                </div>
                <div className="rounded-[20px] border border-black/[0.06] bg-white/[0.62] p-4 dark:border-white/[0.08] dark:bg-white/[0.04]">
                  <div className="text-sm font-medium text-foreground">{qqCopy.currentBot}</div>
                  <div className="mt-2 text-xs text-muted-foreground">
                    {activeProfileSnapshot?.label || qqWizardDraft.bot_name || 'DeepScientist'} · {qqWizardDraft.app_id || activeProfileSnapshot?.app_id || '—'}
                  </div>
                </div>
              </div>
            ) : null}

            {qqWizardStep === 3 ? (
              <div className="space-y-4 pt-2">
                <div className="rounded-[20px] border border-black/[0.06] bg-white/[0.62] p-4 dark:border-white/[0.08] dark:bg-white/[0.04]">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className={cn('h-4 w-4', hasDetectedTarget ? 'text-emerald-600' : 'text-muted-foreground')} />
                    <span className="text-sm font-medium text-foreground">
                      {hasDetectedTarget ? t.qqConnectedSummary : t.qqWaitingOpenId}
                    </span>
                  </div>
                  <div className="mt-3 grid gap-3 text-sm text-muted-foreground md:grid-cols-3">
                    <div>
                      <span className="text-foreground">{t.transportLabel}:</span> gateway_direct
                    </div>
                    <div>
                      <span className="text-foreground">{t.boundTarget}:</span> {activeProfileSnapshot?.main_chat_id || '—'}
                    </div>
                    <div>
                      <span className="text-foreground">{t.discoveredTargets}:</span> {activeProfileTargets.length}
                    </div>
                  </div>
                </div>
                {activeProfileTargets.length > 0 ? (
                  <div className="rounded-[20px] border border-black/[0.06] bg-white/[0.62] p-4 dark:border-white/[0.08] dark:bg-white/[0.04]">
                    <div className="text-sm font-medium text-foreground">{qqCopy.savedTargets}</div>
                    <div className="mt-3 space-y-2">
                      {activeProfileTargets.map((target) => (
                        <div
                          key={`qq-summary-target:${target.conversation_id}`}
                          className="flex items-center justify-between gap-3 rounded-[14px] border border-black/[0.06] bg-black/[0.02] px-3 py-2 text-sm dark:border-white/[0.08] dark:bg-white/[0.03]"
                        >
                          <div className="min-w-0">
                            <div className="truncate font-medium text-foreground">{connectorTargetLabel(target)}</div>
                            <div className="truncate font-mono text-xs text-muted-foreground">{target.conversation_id}</div>
                          </div>
                          <div className="shrink-0">{target.bound_quest_id ? <Badge variant="secondary">{target.bound_quest_id}</Badge> : null}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
                <div className="rounded-[20px] border border-emerald-500/20 bg-emerald-500/8 px-4 py-4 text-sm text-emerald-900 dark:text-emerald-100">
                  {qqCopy.bindNotice}
                </div>
              </div>
            ) : null}

            <ModalFooter className="-mx-6 -mb-4 mt-2">
              <Button
                variant="secondary"
                onClick={closeQqWizard}
              >
                {qqCopy.close}
              </Button>
              {qqWizardStep > 1 ? (
                <Button variant="secondary" onClick={() => setQqWizardStep((current) => Math.max(1, current - 1) as 1 | 2 | 3)}>
                  {qqCopy.back}
                </Button>
              ) : null}
              {qqWizardStep < 3 ? (
                <Button
                  onClick={() => {
                    if (qqWizardStep === 1) {
                      saveNewQqProfile()
                      setQqWizardStep(2)
                      return
                    }
                    if (qqWizardStep === 2 && hasDetectedTarget) {
                      setQqWizardStep(3)
                    }
                  }}
                  disabled={saving || (qqWizardStep === 1 && qqMissingFields) || (qqWizardStep === 2 && !hasDetectedTarget)}
                >
                  {qqWizardStep === 1 ? (saving ? t.saving : t.qqSaveNow) : qqWizardStep === 2 ? qqCopy.continue : qqCopy.next}
                </Button>
              ) : (
                <Button
                  onClick={() => {
                    if (isDirty) {
                      onSave()
                    }
                    setQqWizardOpen(false)
                  }}
                  disabled={saving}
                >
                  {isDirty ? <Save className="h-4 w-4" /> : null}
                  {saving ? t.saving : isDirty ? t.save : qqCopy.done}
                </Button>
              )}
            </ModalFooter>
          </div>
        </Modal>
      </div>
    )
  }

  const renderProfileConnectorSetup = () => {
    if (!isGenericProfileConnectorName(entry.name)) {
      return renderGuidedSetup()
    }
    const connectorName = entry.name
    const guide = connectorGuideCatalog[connectorName]
    const profiles = normalizeGenericProfilesConfig(connectorName, config)
    const profileSnapshots = new Map((snapshot?.profiles || []).map((item) => [item.profile_id, item]))
    const targets = snapshot ? normalizeConnectorTargets(snapshot) : []
    const platformStep = guide.steps.find((step) => step.id === 'platform') || guide.steps[0]
    const settingsStep = guide.steps.find((step) => step.id === 'settings') || guide.steps[1] || guide.steps[0]
    const verifyStep = guide.steps.find((step) => step.id === 'verify') || guide.steps[2] || guide.steps[guide.steps.length - 1]
    const profileFields = genericConnectorProfileFieldKeys[connectorName]
      .map((key) => findConnectorField(entry, key))
      .filter(Boolean) as ConnectorField[]
    const requiredFields = findConnectorFields(
      entry,
      guide.requiredFieldKeys.filter((key) => genericConnectorProfileFieldKeys[connectorName].includes(key))
    )
    const missingRequiredFields = requiredFields.filter((field) => !connectorFieldReady(field, profileWizardDraft[field.key]))
    const hasSavedProfile = Boolean(profileWizardProfileId && profiles.some((item) => String(item.profile_id || '').trim() === profileWizardProfileId))
    const activeProfileSnapshot = profileWizardProfileId ? profileSnapshots.get(profileWizardProfileId) || null : null
    const targetMatchesProfile = (target: ConnectorTargetSnapshot, profileId: string) =>
      String(target.profile_id || '').trim() === profileId || (!String(target.profile_id || '').trim() && profiles.length === 1)
    const activeProfileTargets = profileWizardProfileId ? targets.filter((item) => targetMatchesProfile(item, profileWizardProfileId)) : []
    const hasDetectedTarget = activeProfileTargets.length > 0 || Boolean(activeProfileSnapshot?.last_conversation_id)
    const labels =
      locale === 'zh'
        ? {
            configuredTitle: '已添加的 Connector',
            configuredHint: '每个实例都是独立的 connector。点击 Add 会从空白表单开始新增，不会修改已有实例。',
            noConnector: '当前还没有新增任何 connector 实例。',
            addTitle: '新增 Connector',
            addHint: '先保存当前实例，然后去平台侧发送第一条真实消息，DeepScientist 才能自动识别目标 ID。',
            waiting: '等待第一条消息',
            ready: '已就绪',
            profileId: 'Profile ID',
          }
        : {
            configuredTitle: 'Configured connectors',
            configuredHint: 'Each profile is an independent connector. Add always starts from a blank draft and never edits an existing one.',
            noConnector: 'No connector profile has been added yet.',
            addTitle: 'Add connector',
            addHint: 'Save this profile first, then send one real platform message so DeepScientist can discover the target id automatically.',
            waiting: 'Waiting for first message',
            ready: 'Ready',
            profileId: 'Profile ID',
          }
    const profileStepState = {
      1: (profileWizardStep > 1 || hasSavedProfile ? 'done' : 'current') as const,
      2: (hasSavedProfile ? 'done' : profileWizardStep === 2 ? 'current' : 'pending') as const,
      3: (!hasSavedProfile ? 'pending' : hasDetectedTarget ? 'done' : 'current') as const,
    }

    const openProfileWizard = () => {
      const nextDraft = createGenericProfileDraft(connectorName, config)
      setProfileWizardDraft(nextDraft)
      setProfileWizardProfileId(String(nextDraft.profile_id || ''))
      setProfileWizardStep(1)
      setProfileWizardOpen(true)
    }

    const saveNewProfile = () => {
      const fieldDefaults = genericConnectorProfileDefaults[connectorName]
      const requestedProfileId = String(profileWizardDraft.profile_id || '').trim() || createGenericProfileId(connectorName)
      let profileId = requestedProfileId
      let suffix = 2
      while (profiles.some((item) => String(item.profile_id || '').trim() === profileId)) {
        profileId = `${requestedProfileId}-${suffix}`
        suffix += 1
      }
      const nextProfile: Record<string, unknown> = {
        profile_id: profileId,
        enabled: true,
      }
      for (const [key, fallbackValue] of Object.entries(fieldDefaults)) {
        const rawValue = profileWizardDraft[key]
        const fallback =
          key === 'session_dir' && connectorName === 'whatsapp'
            ? `~/.deepscientist/connectors/whatsapp/${profileId}`
            : fallbackValue
        nextProfile[key] = typeof rawValue === 'boolean' ? rawValue : String(rawValue ?? fallback ?? '').trim()
      }
      onUpdateConnector(entry.name, {
        enabled: true,
        profiles: [...profiles, nextProfile],
      })
      setProfileWizardDraft(nextProfile)
      setProfileWizardProfileId(profileId)
      onSave()
    }

    return (
      <div className="space-y-5">
        <section className="rounded-[24px] border border-black/[0.08] bg-white/[0.48] p-5 dark:border-white/[0.12] dark:bg-white/[0.03]">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{labels.configuredTitle}</div>
              <h4 className="mt-2 text-lg font-semibold tracking-tight">{translateSettingsCatalogText(locale, entry.label)} Connector</h4>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">{labels.configuredHint}</p>
            </div>
            <Badge variant="secondary" className="shrink-0">
              {profiles.length}
            </Badge>
          </div>

          <div className="mt-5 space-y-3">
            {profiles.length === 0 ? (
              <div className="rounded-[20px] border border-dashed border-black/[0.12] bg-white/[0.5] px-4 py-4 text-sm text-muted-foreground dark:border-white/[0.12] dark:bg-white/[0.04]">
                {labels.noConnector}
              </div>
            ) : (
              profiles.map((profile) => {
                const profileId = String(profile.profile_id || '').trim()
                const profileSnapshot = profileSnapshots.get(profileId)
                const profileTargets = targets.filter((item) => targetMatchesProfile(item, profileId))
                const ready = Boolean(profileTargets.length || profileSnapshot?.last_conversation_id)
                const identifier =
                  connectorName === 'discord'
                    ? String(profile.application_id || '').trim()
                    : connectorName === 'slack'
                      ? String(profile.bot_user_id || '').trim()
                        : connectorName === 'feishu'
                          ? String(profile.app_id || '').trim()
                        : connectorName === 'whatsapp'
                          ? String(profile.session_dir || '').trim()
                          : String(profile.bot_name || '').trim()
                return (
                  <div
                    key={profileId}
                    className="rounded-[20px] border border-black/[0.06] bg-white/[0.62] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.04]"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-foreground">{profileSnapshot?.label || genericProfileLabel(connectorName, profile)}</div>
                        <div className="mt-1 break-all font-mono text-xs text-muted-foreground">{identifier || profileId}</div>
                      </div>
                      <Badge variant={ready ? 'default' : 'secondary'}>{ready ? labels.ready : labels.waiting}</Badge>
                    </div>
                    <div className="mt-3 grid gap-2 text-xs text-muted-foreground md:grid-cols-4">
                      <div>
                        <span className="text-foreground">{labels.profileId}:</span> {profileId}
                      </div>
                      <div>
                        <span className="text-foreground">{t.connection}:</span>{' '}
                        {translateSettingsCatalogText(locale, profileSnapshot?.connection_state || 'idle')}
                      </div>
                      <div>
                        <span className="text-foreground">{t.auth}:</span>{' '}
                        {translateSettingsCatalogText(locale, profileSnapshot?.auth_state || 'idle')}
                      </div>
                      <div>
                        <span className="text-foreground">{t.discoveredTargets}:</span> {profileTargets.length}
                      </div>
                    </div>
                  </div>
                )
              })
            )}
          </div>

          <div className="mt-5 flex flex-col gap-3 rounded-[20px] border border-black/[0.06] bg-black/[0.02] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.03] md:flex-row md:items-center md:justify-between">
            <div className="text-sm text-muted-foreground">{labels.addHint}</div>
            <Button size="lg" className="rounded-full px-6" onClick={openProfileWizard}>
              <RadioTower className="h-4 w-4" />
              {labels.addTitle}
            </Button>
          </div>
        </section>

        <section className="rounded-[24px] border border-black/[0.08] bg-white/[0.48] p-5 dark:border-white/[0.12] dark:bg-white/[0.03]">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.boundTargetsTitle}</div>
              <h4 className="mt-2 text-lg font-semibold tracking-tight">{t.discoveredTargets}</h4>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">{t.boundTargetsHint}</p>
            </div>
            <Badge variant="secondary" className="shrink-0">
              {targets.length}
            </Badge>
          </div>

          <div className="mt-5">
            <ConnectorTargetList locale={locale} targets={targets} emptyText={t.noTargets} showBindingDetails={false} />
          </div>
        </section>

        <Modal
          open={profileWizardOpen}
          onClose={() => setProfileWizardOpen(false)}
          title={`${translateSettingsCatalogText(locale, entry.label)} Connector`}
          description={localizedGuideText(locale, guide.summary)}
          size="xl"
          className={connectorModalClassName}
        >
          <div className="space-y-5">
            <div className="grid gap-3 md:grid-cols-3">
              {[
                { step: 1 as const, title: localizedGuideText(locale, platformStep?.title), state: profileStepState[1] },
                { step: 2 as const, title: localizedGuideText(locale, settingsStep?.title), state: profileStepState[2] },
                { step: 3 as const, title: localizedGuideText(locale, verifyStep?.title), state: profileStepState[3] },
              ].map((item) => (
                <button
                  key={`profile-wizard-step:${item.step}`}
                  type="button"
                  onClick={() => {
                    if (item.step < 3 || hasSavedProfile) {
                      setProfileWizardStep(item.step)
                    }
                  }}
                  disabled={item.step === 3 && !hasSavedProfile}
                  className={cn(
                    'rounded-[18px] border px-4 py-3 text-left disabled:cursor-not-allowed disabled:opacity-60',
                    profileWizardStep === item.step
                      ? 'border-black/[0.14] bg-black/[0.04] dark:border-white/[0.18] dark:bg-white/[0.05]'
                      : 'border-black/[0.08] bg-white/[0.52] dark:border-white/[0.08] dark:bg-white/[0.03]'
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Step {item.step}</span>
                    <StepStateBadge state={item.state} locale={locale} />
                  </div>
                  <div className="mt-2 text-sm font-medium text-foreground">{item.title}</div>
                </button>
              ))}
            </div>

            {profileWizardStep === 1 ? (
              <div className="space-y-5 pt-2">
                <div className="flex flex-wrap gap-2">
                  {(platformStep?.links?.length ? platformStep.links : guide.links).map((link) => (
                    <ConnectorGuideLinkButton
                      key={`profile-step1:${link.kind}:${localizedGuideText(locale, link.label)}`}
                      link={link}
                      locale={locale}
                    />
                  ))}
                </div>
                {platformStep?.image ? <ConnectorGuideImageCard image={platformStep.image} locale={locale} /> : null}
                {platformStep?.checklist?.length ? (
                  <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.stepChecklist}</div>
                    <ol className="mt-3 space-y-2 text-sm leading-6 text-muted-foreground">
                      {platformStep.checklist.map((item, index) => (
                        <li key={`profile-platform:${index}`}>
                          {index + 1}. {localizedGuideText(locale, item)}
                        </li>
                      ))}
                    </ol>
                  </div>
                ) : null}
              </div>
            ) : null}

            {profileWizardStep === 2 ? (
              <div className="space-y-5 pt-2">
                <div className="flex flex-wrap gap-2">
                  {(settingsStep?.links?.length ? settingsStep.links : guide.links).map((link) => (
                    <ConnectorGuideLinkButton
                      key={`profile-step2:${link.kind}:${localizedGuideText(locale, link.label)}`}
                      link={link}
                      locale={locale}
                    />
                  ))}
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
                    <label className="flex min-h-[44px] items-center justify-between gap-4">
                      <span className="text-sm font-medium">{t.enabled}</span>
                      <input
                        type="checkbox"
                        checked={enabled}
                        onChange={(event) => onUpdateField(entry.name, 'enabled', event.target.checked)}
                        className="h-4 w-4 rounded border-black/20 text-foreground"
                      />
                    </label>
                    <div className="mt-3 text-xs leading-5 text-muted-foreground">{localizedGuideText(locale, settingsStep?.description)}</div>
                  </div>
                  {profileFields.map((field) => (
                    <ConnectorFieldControl
                      key={`profile-draft:${field.key}`}
                      field={field}
                      config={profileWizardDraft}
                      locale={locale}
                      onChange={(key, value) => setProfileWizardDraft((current) => ({ ...current, [key]: value }))}
                    />
                  ))}
                </div>
                {missingRequiredFields.length ? (
                  <StepBlockerNotice locale={locale} description={t.enableConnectorFirst} fields={missingRequiredFields} />
                ) : null}
              </div>
            ) : null}

            {profileWizardStep === 3 ? (
              <div className="space-y-5 pt-2">
                <div className="flex flex-wrap gap-2">
                  {(verifyStep?.links?.length ? verifyStep.links : guide.links).map((link) => (
                    <ConnectorGuideLinkButton
                      key={`profile-step3:${link.kind}:${localizedGuideText(locale, link.label)}`}
                      link={link}
                      locale={locale}
                    />
                  ))}
                </div>
                {verifyStep?.checklist?.length ? (
                  <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.stepChecklist}</div>
                    <ol className="mt-3 space-y-2 text-sm leading-6 text-muted-foreground">
                      {verifyStep.checklist.map((item, index) => (
                        <li key={`profile-verify:${index}`}>
                          {index + 1}. {localizedGuideText(locale, item)}
                        </li>
                      ))}
                    </ol>
                  </div>
                ) : null}
                {!hasDetectedTarget ? (
                  <StepBlockerNotice locale={locale} description={t.sendPlatformMessageFirst} />
                ) : null}
                <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
                  <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
                    <div className="flex items-center gap-2 text-sm font-medium">
                      <MessageSquareText className="h-4 w-4 text-muted-foreground" />
                      <span>{t.discoveredTargets}</span>
                    </div>
                    <div className="mt-2 text-xs leading-5 text-muted-foreground">{t.useDiscoveredTargets}</div>
                    <div className="mt-4">
                      <ConnectorTargetList locale={locale} targets={activeProfileTargets} emptyText={t.noTargets} showBindingDetails={false} />
                    </div>
                  </div>
                  <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
                    <div className="text-sm font-medium">{activeProfileSnapshot?.label || genericProfileLabel(connectorName, profileWizardDraft)}</div>
                    <div className="mt-4 space-y-2 text-sm text-muted-foreground">
                      <div>
                        <span className="text-foreground">{labels.profileId}:</span> {profileWizardProfileId || '—'}
                      </div>
                      <div>
                        <span className="text-foreground">{t.connection}:</span>{' '}
                        {translateSettingsCatalogText(locale, activeProfileSnapshot?.connection_state || snapshot?.connection_state || 'idle')}
                      </div>
                      <div>
                        <span className="text-foreground">{t.auth}:</span>{' '}
                        {translateSettingsCatalogText(locale, activeProfileSnapshot?.auth_state || snapshot?.auth_state || 'idle')}
                      </div>
                      <div>
                        <span className="text-foreground">{t.discoveredTargets}:</span> {activeProfileTargets.length}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

            <ModalFooter className="-mx-6 -mb-4 mt-2">
              <Button variant="secondary" onClick={() => setProfileWizardOpen(false)}>
                {t.wizardClose}
              </Button>
              {profileWizardStep > 1 ? (
                <Button variant="secondary" onClick={() => setProfileWizardStep((current) => Math.max(1, current - 1) as 1 | 2 | 3)}>
                  {t.wizardBack}
                </Button>
              ) : null}
              {profileWizardStep === 1 ? (
                <Button onClick={() => setProfileWizardStep(2)}>{t.wizardContinue}</Button>
              ) : profileWizardStep === 2 ? (
                <Button
                  onClick={() => {
                    if (hasSavedProfile) {
                      setProfileWizardStep(3)
                      return
                    }
                    saveNewProfile()
                    setProfileWizardStep(3)
                  }}
                  disabled={saving || (!hasSavedProfile && missingRequiredFields.length > 0)}
                >
                  {hasSavedProfile ? t.wizardContinue : saving ? t.saving : t.wizardSaveContinue}
                </Button>
              ) : (
                <Button onClick={() => setProfileWizardOpen(false)}>{t.wizardDone}</Button>
              )}
            </ModalFooter>
          </div>
        </Modal>
      </div>
    )
  }

  const renderLingzhuSetup = () => {
    const lingzhuGuide = connectorGuideCatalog.lingzhu
    const endpointGuideStep = lingzhuGuide.steps.find((step) => step.id === 'endpoint') || null
    const platformGuideStep = lingzhuGuide.steps.find((step) => step.id === 'platform') || null
    const probeGuideStep = lingzhuGuide.steps.find((step) => step.id === 'probe') || null
    const localHostField = findConnectorField(entry, 'local_host')
    const gatewayPortField = findConnectorField(entry, 'gateway_port')
    const publicBaseUrlField = findConnectorField(entry, 'public_base_url')
    const authAkField = findConnectorField(entry, 'auth_ak')
    const agentIdField = findConnectorField(entry, 'agent_id')
    const systemPromptField = findConnectorField(entry, 'system_prompt')
    const behaviorFields = [
      findConnectorField(entry, 'include_metadata'),
      findConnectorField(entry, 'request_timeout_ms'),
      findConnectorField(entry, 'default_navigation_mode'),
      findConnectorField(entry, 'enable_follow_up'),
      findConnectorField(entry, 'follow_up_max_count'),
      findConnectorField(entry, 'session_mode'),
      findConnectorField(entry, 'session_namespace'),
      findConnectorField(entry, 'auto_receipt_ack'),
      findConnectorField(entry, 'visible_progress_heartbeat'),
      findConnectorField(entry, 'visible_progress_heartbeat_sec'),
      findConnectorField(entry, 'max_image_bytes'),
    ].filter(Boolean) as ConnectorField[]
    const advancedFields = [
      findConnectorField(entry, 'debug_logging'),
      findConnectorField(entry, 'debug_log_payloads'),
      findConnectorField(entry, 'debug_log_dir'),
      findConnectorField(entry, 'enable_experimental_native_actions'),
    ].filter(Boolean) as ConnectorField[]
    const snapshotDetails =
      snapshot?.details && typeof snapshot.details === 'object' ? (snapshot.details as Record<string, unknown>) : {}
    const localHealthUrl =
      typeof snapshotDetails.health_url === 'string' && snapshotDetails.health_url
        ? String(snapshotDetails.health_url)
        : lingzhuLocalHealthUrl(config)
    const localSseUrl =
      typeof snapshotDetails.endpoint_url === 'string' && snapshotDetails.endpoint_url
        ? String(snapshotDetails.endpoint_url)
        : lingzhuLocalSseUrl(config)
    const publicSseUrl =
      typeof snapshotDetails.public_endpoint_url === 'string' && snapshotDetails.public_endpoint_url
        ? String(snapshotDetails.public_endpoint_url)
        : lingzhuPublicSseUrl(config)
    const generatedConfig =
      typeof snapshotDetails.generated_openclaw_config === 'string' && snapshotDetails.generated_openclaw_config
        ? String(snapshotDetails.generated_openclaw_config)
        : lingzhuGeneratedOpenclawConfig(config)
    const generatedCurl =
      typeof snapshotDetails.generated_curl === 'string' && snapshotDetails.generated_curl
        ? String(snapshotDetails.generated_curl)
        : lingzhuGeneratedCurl(config)
    const supportedCommandsRaw =
      (Array.isArray(snapshotDetails.supported_commands) ? snapshotDetails.supported_commands : null) || []
    const supportedCommands = supportedCommandsRaw.map((item) => String(item)).filter(Boolean)
    const targets = snapshot ? normalizeConnectorTargets(snapshot) : []
    const authAk = lingzhuConfigString(config, 'auth_ak')
    const publicReady = Boolean(lingzhuPublicBaseUrl(config))
    const endpointReady = Boolean(enabled && publicReady)
    const platformReady = Boolean(endpointReady && authAk)
    const runtimeReady = Boolean(
      platformReady && (
        targets.length > 0
        || (typeof snapshot?.connection_state === 'string' && snapshot.connection_state.trim() && snapshot.connection_state !== 'idle')
        || (typeof snapshot?.auth_state === 'string' && snapshot.auth_state.trim() && snapshot.auth_state !== 'idle')
      )
    )
    const lingzhuStepSummaries: Array<{ step: 1 | 2 | 3; title: string; state: 'done' | 'current' | 'pending' }> = [
      {
        step: 1,
        title: endpointGuideStep ? localizedGuideText(locale, endpointGuideStep.title) : t.lingzhuStepEndpoint,
        state: endpointReady ? 'done' : 'current',
      },
      {
        step: 2,
        title: platformGuideStep ? localizedGuideText(locale, platformGuideStep.title) : t.lingzhuStepPlatform,
        state: !endpointReady ? 'pending' : platformReady ? 'done' : 'current',
      },
      {
        step: 3,
        title: probeGuideStep ? localizedGuideText(locale, probeGuideStep.title) : t.lingzhuStepProbe,
        state: !platformReady ? 'pending' : runtimeReady ? 'done' : 'current',
      },
    ]
    const nextLingzhuStep = lingzhuStepSummaries.find((item) => item.state !== 'done') || lingzhuStepSummaries[lingzhuStepSummaries.length - 1]
    const maxLingzhuStep = !endpointReady ? 1 : !platformReady ? 2 : 3
    const openLingzhuWizard = () => {
      setLingzhuWizardStep(nextLingzhuStep.step)
      setLingzhuWizardOpen(true)
    }

    return (
      <div className="space-y-5">
        <section className="rounded-[24px] border border-black/[0.08] bg-white/[0.48] p-5 dark:border-white/[0.12] dark:bg-white/[0.03]">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.bindConnectorTitle}</div>
              <h4 className="mt-2 text-lg font-semibold tracking-tight">{localizedGuideText(locale, lingzhuGuide.summary)}</h4>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">{t.lingzhuNeedPublicIp}</p>
            </div>
            <StepStateBadge state={nextLingzhuStep.state} locale={locale} />
          </div>

          <div className="mt-5 grid gap-3 lg:grid-cols-3">
            {lingzhuStepSummaries.map((item) => (
              <div
                key={`lingzhu-summary:${item.step}`}
                className="rounded-[20px] border border-black/[0.06] bg-white/[0.62] px-4 py-3 dark:border-white/[0.08] dark:bg-white/[0.04]"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Step {item.step}</span>
                  <StepStateBadge state={item.state} locale={locale} />
                </div>
                <div className="mt-2 text-sm font-medium text-foreground">{item.title}</div>
              </div>
            ))}
          </div>

          <div className="mt-5 rounded-[20px] border border-black/[0.06] bg-black/[0.02] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.03]">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.nextAction}</div>
            <div className="mt-2 text-sm font-medium text-foreground">{nextLingzhuStep.title}</div>
            <div className="mt-1 text-sm leading-6 text-muted-foreground">
              {nextLingzhuStep.step === 1
                ? localizedGuideText(locale, endpointGuideStep?.description)
                : nextLingzhuStep.step === 2
                  ? localizedGuideText(locale, platformGuideStep?.description)
                  : localizedGuideText(locale, probeGuideStep?.description)}
            </div>
          </div>

          <div className="mt-5 flex flex-wrap gap-2">
            {lingzhuGuide.links.map((link) => (
              <ConnectorGuideLinkButton
                key={`lingzhu-endpoint:${link.kind}:${localizedGuideText(locale, link.label)}`}
                link={link}
                locale={locale}
              />
            ))}
          </div>

          <div className="mt-5 flex flex-col gap-3 rounded-[20px] border border-black/[0.06] bg-black/[0.02] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.03] md:flex-row md:items-center md:justify-between">
            <div className="text-sm text-muted-foreground">
              {nextLingzhuStep.step === 1
                ? t.lingzhuNeedPublicIp
                : nextLingzhuStep.step === 2
                  ? t.lingzhuPlatformReminder
                  : t.lingzhuSnapshotHint}
            </div>
            <Button size="lg" className="rounded-full px-6" onClick={openLingzhuWizard}>
              <RadioTower className="h-4 w-4" />
              {t.openGuidedSetup}
            </Button>
          </div>
        </section>

        <section className="rounded-[24px] border border-black/[0.08] bg-white/[0.48] p-5 dark:border-white/[0.12] dark:bg-white/[0.03]">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.boundTargetsTitle}</div>
              <h4 className="mt-2 text-lg font-semibold tracking-tight">{t.discoveredTargets}</h4>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">{t.boundTargetsHint}</p>
            </div>
            <Badge variant="secondary" className="shrink-0">
              {targets.length}
            </Badge>
          </div>

          <div className="mt-5">
            <ConnectorTargetList locale={locale} targets={targets} emptyText={t.noTargets} showBindingDetails={false} />
          </div>

          <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-[20px] border border-black/[0.06] bg-white/[0.62] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.04]">
              <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{t.connection}</div>
              <div className="mt-2 text-sm font-medium">{translateSettingsCatalogText(locale, snapshot?.connection_state || 'idle')}</div>
            </div>
            <div className="rounded-[20px] border border-black/[0.06] bg-white/[0.62] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.04]">
              <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{t.auth}</div>
              <div className="mt-2 text-sm font-medium">{translateSettingsCatalogText(locale, snapshot?.auth_state || 'idle')}</div>
            </div>
            <div className="rounded-[20px] border border-black/[0.06] bg-white/[0.62] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.04]">
              <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{t.lingzhuLocalHealthUrl}</div>
              <div className="mt-2 break-all text-sm font-medium">{localHealthUrl}</div>
            </div>
            <div className="rounded-[20px] border border-black/[0.06] bg-white/[0.62] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.04]">
              <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{t.lingzhuPublicSseUrl}</div>
              <div className="mt-2 break-all text-sm font-medium">{publicSseUrl || '—'}</div>
            </div>
          </div>
        </section>

        <Modal
          open={lingzhuWizardOpen}
          onClose={() => setLingzhuWizardOpen(false)}
          title={`${translateSettingsCatalogText(locale, entry.label)} Connector`}
          description={localizedGuideText(locale, lingzhuGuide.summary)}
          size="xl"
          className={connectorModalClassName}
        >
          <div className="space-y-5">
            <div className="grid gap-3 md:grid-cols-3">
              {lingzhuStepSummaries.map((item) => (
                <button
                  key={`lingzhu-wizard-step:${item.step}`}
                  type="button"
                  onClick={() => {
                    if (item.step <= maxLingzhuStep) {
                      setLingzhuWizardStep(item.step)
                    }
                  }}
                  disabled={item.step > maxLingzhuStep}
                  className={cn(
                    'rounded-[18px] border px-4 py-3 text-left disabled:cursor-not-allowed disabled:opacity-60',
                    lingzhuWizardStep === item.step
                      ? 'border-black/[0.14] bg-black/[0.04] dark:border-white/[0.18] dark:bg-white/[0.05]'
                      : 'border-black/[0.08] bg-white/[0.52] dark:border-white/[0.08] dark:bg-white/[0.03]'
                  )}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Step {item.step}</span>
                    <StepStateBadge state={item.state} locale={locale} />
                  </div>
                  <div className="mt-2 text-sm font-medium text-foreground">{item.title}</div>
                </button>
              ))}
            </div>

            {lingzhuWizardStep === 1 ? (
              <div className="space-y-5 pt-2">
                <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Step 1</div>
                    <h4 className="mt-2 text-lg font-semibold tracking-tight">{t.lingzhuStepEndpoint}</h4>
                    <p className="mt-1 text-sm leading-6 text-muted-foreground">
                      {localizedGuideText(locale, endpointGuideStep?.description) || t.lingzhuNeedPublicIp}
                    </p>
                  </div>
                  <StepStateBadge state={lingzhuStepSummaries[0].state} locale={locale} />
                </div>

                <div className="flex flex-wrap gap-2">
                  {lingzhuGuide.links.map((link) => (
                    <ConnectorGuideLinkButton
                      key={`lingzhu-step1:${link.kind}:${localizedGuideText(locale, link.label)}`}
                      link={link}
                      locale={locale}
                    />
                  ))}
                </div>

                {endpointGuideStep?.image ? <ConnectorGuideImageCard image={endpointGuideStep.image} locale={locale} /> : null}

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
                    <label className="flex min-h-[44px] items-center justify-between gap-4">
                      <span className="text-sm font-medium">{t.enabled}</span>
                      <input
                        type="checkbox"
                        checked={enabled}
                        onChange={(event) => onUpdateField(entry.name, 'enabled', event.target.checked)}
                        className="h-4 w-4 rounded border-black/20 text-foreground"
                      />
                    </label>
                    <div className="mt-3 text-xs leading-5 text-muted-foreground">{t.lingzhuNeedPublicIp}</div>
                  </div>
                  {localHostField ? (
                    <ConnectorFieldControl
                      field={localHostField}
                      config={config}
                      locale={locale}
                      onChange={(key, value) => onUpdateField(entry.name, key, value)}
                    />
                  ) : null}
                  {gatewayPortField ? (
                    <ConnectorFieldControl
                      field={gatewayPortField}
                      config={config}
                      locale={locale}
                      onChange={(key, value) => onUpdateField(entry.name, key, value)}
                    />
                  ) : null}
                  {publicBaseUrlField ? (
                    <ConnectorFieldControl
                      field={publicBaseUrlField}
                      config={config}
                      locale={locale}
                      onChange={(key, value) => onUpdateField(entry.name, key, value)}
                    />
                  ) : null}
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="secondary"
                    onClick={() => onUpdateConnector(entry.name, { local_host: '127.0.0.1', gateway_port: '18789' })}
                  >
                    {t.lingzhuUseLocalDefaults}
                  </Button>
                </div>
              </div>
            ) : null}

            {lingzhuWizardStep === 2 ? (
              <div className="space-y-5 pt-2">
                <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Step 2</div>
                    <h4 className="mt-2 text-lg font-semibold tracking-tight">{t.lingzhuGeneratedValues}</h4>
                    <p className="mt-1 text-sm leading-6 text-muted-foreground">
                      {localizedGuideText(locale, platformGuideStep?.description) || t.lingzhuPlatformReminder}
                    </p>
                  </div>
                  <StepStateBadge state={lingzhuStepSummaries[1].state} locale={locale} />
                </div>

                {!endpointReady ? <StepBlockerNotice locale={locale} description={t.lingzhuCompleteEndpointFirst} /> : null}

                {platformGuideStep?.image ? <ConnectorGuideImageCard image={platformGuideStep.image} locale={locale} /> : null}

                <div className="grid gap-4 md:grid-cols-2">
                  {authAkField ? (
                    <ConnectorFieldControl
                      field={authAkField}
                      config={config}
                      locale={locale}
                      onChange={(key, value) => onUpdateField(entry.name, key, value)}
                    />
                  ) : null}
                  <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
                    <div className="text-sm font-medium">{t.lingzhuGenerateAk}</div>
                    <div className="mt-2 text-xs leading-5 text-muted-foreground">{t.lingzhuPublicHint}</div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <Button
                        variant="secondary"
                        onClick={() => onUpdateField(entry.name, 'auth_ak', createLingzhuAk())}
                      >
                        <ShieldCheck className="h-4 w-4" />
                        {t.lingzhuGenerateAk}
                      </Button>
                    </div>
                  </div>
                  {agentIdField ? (
                    <ConnectorFieldControl
                      field={agentIdField}
                      config={config}
                      locale={locale}
                      onChange={(key, value) => onUpdateField(entry.name, key, value)}
                    />
                  ) : null}
                  {systemPromptField ? (
                    <ConnectorFieldControl
                      field={systemPromptField}
                      config={config}
                      locale={locale}
                      onChange={(key, value) => onUpdateField(entry.name, key, value)}
                    />
                  ) : null}
                </div>

                <div className="grid gap-4 md:grid-cols-3">
                  <div className="rounded-[20px] border border-black/[0.06] bg-white/[0.62] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.04]">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{t.lingzhuLocalHealthUrl}</div>
                    <div className="mt-2 break-all text-sm font-medium">{localHealthUrl}</div>
                  </div>
                  <div className="rounded-[20px] border border-black/[0.06] bg-white/[0.62] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.04]">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{t.lingzhuLocalSseUrl}</div>
                    <div className="mt-2 break-all text-sm font-medium">{localSseUrl}</div>
                  </div>
                  <div className="rounded-[20px] border border-black/[0.06] bg-white/[0.62] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.04]">
                    <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{t.lingzhuPublicSseUrl}</div>
                    <div className="mt-2 break-all text-sm font-medium">{publicSseUrl || '—'}</div>
                  </div>
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
                    <div className="text-sm font-medium">{t.lingzhuOpenclawConfig}</div>
                    <Textarea value={generatedConfig} readOnly className="mt-3 min-h-[240px] rounded-[18px] border-black/[0.08] bg-white/[0.44] font-mono text-xs shadow-none dark:bg-white/[0.03]" />
                  </div>
                  <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
                    <div className="text-sm font-medium">{t.lingzhuCurl}</div>
                    <Textarea value={generatedCurl} readOnly className="mt-3 min-h-[240px] rounded-[18px] border-black/[0.08] bg-white/[0.44] font-mono text-xs shadow-none dark:bg-white/[0.03]" />
                  </div>
                </div>
              </div>
            ) : null}

            {lingzhuWizardStep === 3 ? (
              <div className="space-y-5 pt-2">
                <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">Step 3</div>
                    <h4 className="mt-2 text-lg font-semibold tracking-tight">{t.lingzhuProbeResult}</h4>
                    <p className="mt-1 text-sm leading-6 text-muted-foreground">
                      {localizedGuideText(locale, probeGuideStep?.description) || t.lingzhuSnapshotHint}
                    </p>
                  </div>
                  <StepStateBadge state={lingzhuStepSummaries[2].state} locale={locale} />
                </div>

                {!platformReady ? <StepBlockerNotice locale={locale} description={t.lingzhuSavePlatformValuesFirst} /> : null}

                {probeGuideStep?.image ? <ConnectorGuideImageCard image={probeGuideStep.image} locale={locale} /> : null}

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
                    <div className="text-sm font-medium">{t.discoveredTargets}</div>
                    <div className="mt-2 text-xs leading-5 text-muted-foreground">{t.useDiscoveredTargets}</div>
                    <div className="mt-4">
                      <ConnectorTargetList locale={locale} targets={targets} emptyText={t.noTargets} showBindingDetails={false} />
                    </div>
                  </div>
                  <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
                    <div className="text-sm font-medium">{t.snapshot}</div>
                    <div className="mt-2 text-xs leading-5 text-muted-foreground">{t.lingzhuSnapshotHint}</div>
                    <div className="mt-4 space-y-2 text-sm text-muted-foreground">
                      <div>
                        <span className="text-foreground">{t.connection}:</span>{' '}
                        {translateSettingsCatalogText(locale, snapshot?.connection_state || 'idle')}
                      </div>
                      <div>
                        <span className="text-foreground">{t.auth}:</span>{' '}
                        {translateSettingsCatalogText(locale, snapshot?.auth_state || 'idle')}
                      </div>
                      <div>
                        <span className="text-foreground">{t.discoveredTargets}:</span> {targets.length}
                      </div>
                      <div>
                        <span className="text-foreground">{t.lingzhuPublicSseUrl}:</span> {publicSseUrl || '—'}
                      </div>
                      <div className={runtimeReady ? 'text-emerald-700 dark:text-emerald-300' : 'text-muted-foreground'}>
                        {runtimeReady ? t.ok : t.stepProbeHint}
                      </div>
                    </div>
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
                    <div className="text-sm font-medium">{t.lingzhuSupportedCommands}</div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {supportedCommands.length ? (
                        supportedCommands.map((command) => (
                          <span key={command} className="rounded-full border border-black/[0.08] bg-white/[0.44] px-3 py-1 text-xs dark:border-white/[0.12] dark:bg-white/[0.03]">
                            {command}
                          </span>
                        ))
                      ) : (
                        <span className="text-sm text-muted-foreground">—</span>
                      )}
                    </div>
                  </div>
                  <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
                    <div className="text-sm font-medium">{t.lingzhuAgentIdHint}</div>
                    <div className="mt-2 text-sm text-muted-foreground">{lingzhuAgentId(config)}</div>
                  </div>
                </div>

                <div className="border-t border-black/[0.06] pt-5 dark:border-white/[0.08]">
                  <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.stepFields}</div>
                  <div className="grid gap-4 md:grid-cols-2">
                    {behaviorFields.map((field) => (
                      <ConnectorFieldControl
                        key={field.key}
                        field={field}
                        config={config}
                        locale={locale}
                        onChange={(key, value) => onUpdateField(entry.name, key, value)}
                      />
                    ))}
                  </div>
                </div>

                {advancedFields.length ? (
                  <section className="rounded-[24px] border border-black/[0.08] bg-white/[0.48] p-5 dark:border-white/[0.12] dark:bg-white/[0.03]">
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.showLegacy}</div>
                        <h4 className="mt-2 text-lg font-semibold tracking-tight">{translateSettingsCatalogText(locale, 'Advanced debug')}</h4>
                      </div>
                      <Button variant="secondary" onClick={() => setLegacyExpanded((current) => !current)}>
                        {legacyExpanded ? t.hideLegacy : t.showLegacy}
                      </Button>
                    </div>
                    {legacyExpanded ? (
                      <div className="mt-5 grid gap-4 md:grid-cols-2">
                        {advancedFields.map((field) => (
                          <ConnectorFieldControl
                            key={field.key}
                            field={field}
                            config={config}
                            locale={locale}
                            onChange={(key, value) => onUpdateField(entry.name, key, value)}
                          />
                        ))}
                      </div>
                    ) : null}
                  </section>
                ) : null}
              </div>
            ) : null}

            <ModalFooter className="-mx-6 -mb-4 mt-2">
              <Button variant="secondary" onClick={() => setLingzhuWizardOpen(false)}>
                {t.wizardClose}
              </Button>
              {lingzhuWizardStep > 1 ? (
                <Button variant="secondary" onClick={() => setLingzhuWizardStep((current) => Math.max(1, current - 1) as 1 | 2 | 3)}>
                  {t.wizardBack}
                </Button>
              ) : null}
              {lingzhuWizardStep < 3 ? (
                <Button
                  onClick={() => {
                    onSave()
                    setLingzhuWizardStep((current) => Math.min(3, current + 1) as 1 | 2 | 3)
                  }}
                  disabled={
                    saving ||
                    (lingzhuWizardStep === 1 && !endpointReady) ||
                    (lingzhuWizardStep === 2 && !platformReady)
                  }
                >
                  {saving ? t.saving : t.wizardSaveContinue}
                </Button>
              ) : (
                <Button
                  onClick={() => {
                    if (isDirty) {
                      onSave()
                    }
                    setLingzhuWizardOpen(false)
                  }}
                  disabled={saving}
                >
                  {saving ? t.saving : isDirty ? t.save : t.wizardDone}
                </Button>
              )}
            </ModalFooter>
          </div>
        </Modal>
      </div>
    )
  }

  return (
    <section id={cardAnchorId} className="border-t border-black/[0.08] pt-6 dark:border-white/[0.08]">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-[16px] border border-black/[0.08] bg-white/[0.44] dark:border-white/[0.12] dark:bg-white/[0.03]">
              <Icon className="h-4.5 w-4.5" />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-xl font-semibold tracking-tight">
                  {translateSettingsCatalogText(locale, entry.label)}
                </h3>
                <AnchorJumpButton anchorId={cardAnchorId} onJumpToAnchor={onJumpToAnchor} />
                <HintDot
                  label={`${translateSettingsCatalogText(locale, entry.subtitle)} ${translateSettingsCatalogText(locale, entry.deliveryNote)}`.trim()}
                />
                <span className="text-xs text-muted-foreground">{enabled ? t.enabled : t.disabled}</span>
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <label className="inline-flex items-center gap-2 rounded-full border border-black/[0.08] bg-white/[0.52] px-3 py-2 text-sm dark:border-white/[0.12] dark:bg-white/[0.04]">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(event) => onUpdateField(entry.name, 'enabled', event.target.checked)}
              className="h-4 w-4 rounded border-black/20"
            />
            {t.enabled}
          </label>
          <a
            href={entry.portalUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-full border border-black/[0.08] bg-white/[0.52] px-3 py-2 text-sm transition hover:border-black/[0.14] hover:text-foreground dark:border-white/[0.12] dark:bg-white/[0.04]"
          >
            <ArrowUpRight className="h-4 w-4" />
            {t.portal}
          </a>
        </div>
      </div>

      {useCompactGuidedLayout ? (
        <div className="mt-6">
          {entry.name === 'lingzhu'
            ? renderLingzhuSetup()
            : isGenericProfileConnectorName(entry.name)
              ? renderProfileConnectorSetup()
              : renderGuidedSetup()}
        </div>
      ) : (
        <div className="mt-6 grid gap-8 xl:grid-cols-[minmax(0,1fr)_300px]">
          <div className="space-y-5">
            {renderQqSetup()}
          </div>

          <aside className="space-y-6 xl:border-l xl:border-black/[0.08] xl:pl-6 xl:dark:border-white/[0.08]">
            <section>
              <div className="mb-3 flex items-center gap-2 text-sm font-medium">
                <Link2 className="h-4 w-4 text-muted-foreground" />
                <span>{t.snapshot}</span>
              </div>
              {snapshot ? (
                <div className="space-y-2 text-sm text-muted-foreground">
                  <div>
                    <span className="text-foreground">{t.transportLabel}:</span>{' '}
                    {translateSettingsCatalogText(locale, snapshot.transport || snapshot.display_mode || snapshot.mode || 'default')}
                  </div>
                  <div>
                    <span className="text-foreground">{t.connection}:</span>{' '}
                    {translateSettingsCatalogText(locale, snapshot.connection_state || 'idle')}
                  </div>
                  <div>
                    <span className="text-foreground">{t.auth}:</span>{' '}
                    {translateSettingsCatalogText(locale, snapshot.auth_state || 'idle')}
                  </div>
                  <div>
                    <span className="text-foreground">{t.lastMode}:</span>{' '}
                    {translateSettingsCatalogText(locale, snapshot.display_mode || snapshot.mode || 'default')}
                  </div>
                  <div>
                    <span className="text-foreground">{t.queues}:</span> {t.queueIn} {snapshot.inbox_count ?? 0} · {t.queueOut} {snapshot.outbox_count ?? 0}
                  </div>
                  <div>
                    <span className="text-foreground">{t.bindings}:</span> {snapshot.binding_count ?? 0}
                  </div>
                  <div>
                    <span className="text-foreground">{t.discoveredTargets}:</span>{' '}
                    {entry.name === 'qq' ? normalizeConnectorTargets(snapshot).length : snapshot.target_count ?? snapshot.discovered_targets?.length ?? 0}
                  </div>
                  {snapshot.default_target ? (
                    <div className="break-all">
                      <span className="text-foreground">{t.defaultTarget}:</span> {connectorTargetLabel(snapshot.default_target)}
                    </div>
                  ) : null}
                  {snapshot.main_chat_id ? (
                    <div className="break-all">
                      <span className="text-foreground">{t.boundTarget}:</span> {snapshot.main_chat_id}
                    </div>
                  ) : null}
                  {snapshot.last_conversation_id ? (
                    <div className="break-all">
                      <span className="text-foreground">{t.lastSeen}:</span> {snapshot.last_conversation_id}
                    </div>
                  ) : null}
                  {entry.name === 'lingzhu' && snapshot.details ? (
                    <>
                      {typeof snapshot.details.health_url === 'string' ? (
                        <div className="break-all">
                          <span className="text-foreground">{t.lingzhuLocalHealthUrl}:</span> {String(snapshot.details.health_url)}
                        </div>
                      ) : null}
                      {typeof snapshot.details.public_endpoint_url === 'string' && snapshot.details.public_endpoint_url ? (
                        <div className="break-all">
                          <span className="text-foreground">{t.lingzhuPublicSseUrl}:</span> {String(snapshot.details.public_endpoint_url)}
                        </div>
                      ) : null}
                    </>
                  ) : null}
                </div>
              ) : (
                <div className="text-sm text-muted-foreground">{t.noSnapshot}</div>
              )}
            </section>

            {entry.name !== 'lingzhu' ? (
              <section className="border-t border-black/[0.08] pt-4 dark:border-white/[0.08]">
                <div className="mb-3 flex items-center gap-2 text-sm font-medium">
                  <RadioTower className="h-4 w-4 text-muted-foreground" />
                  <span>{t.recentActivity}</span>
                </div>
                {snapshot?.recent_events?.length ? (
                  <div className="feed-scrollbar max-h-[320px] space-y-2 overflow-auto pr-1">
                    {snapshot.recent_events.map((event, index) => (
                      <ConnectorEventRow
                        key={`${event.event_type}:${event.created_at || index}:${event.conversation_id || index}`}
                        event={event}
                        locale={locale}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-muted-foreground">{t.noEvents}</div>
                )}
              </section>
            ) : null}
          </aside>
        </div>
      )}
    </section>
  )
}

export function ConnectorSettingsForm({
  locale,
  value,
  connectors,
  saving,
  isDirty,
  selectedConnectorName,
  onChange,
  onSave,
  onSelectConnector,
  onBackToConnectorCatalog,
  onJumpToAnchor,
}: {
  locale: Locale
  value: ConnectorConfigMap
  connectors: ConnectorSnapshot[]
  saving: boolean
  isDirty: boolean
  selectedConnectorName?: ConnectorName | null
  onChange: (next: ConnectorConfigMap) => void
  onSave: () => void
  onSelectConnector: (connectorName: ConnectorName) => void
  onBackToConnectorCatalog: () => void
  onJumpToAnchor?: (anchorId: string) => void
}) {
  const t = copy[locale]
  const snapshots = useMemo(() => snapshotByName(connectors), [connectors])
  const routing = useMemo(() => routingConfig(value), [value])
  const enabledEntries = useMemo(
    () => connectorCatalog.filter((entry) => Boolean(value[entry.name]?.enabled)),
    [value]
  )
  const preferredConnector = typeof routing.primary_connector === 'string' ? routing.primary_connector : ''
  const deliveryPolicy =
    typeof routing.artifact_delivery_policy === 'string' ? routing.artifact_delivery_policy : 'fanout_all'
  const selectedEntry =
    selectedConnectorName ? connectorCatalog.find((entry) => entry.name === selectedConnectorName) || null : null

  useEffect(() => {
    const nextPreferred =
      enabledEntries.length === 1
        ? enabledEntries[0].name
        : enabledEntries.some((entry) => entry.name === preferredConnector)
          ? preferredConnector
          : ''
    if (nextPreferred === preferredConnector) {
      return
    }
    onChange({
      ...value,
      _routing: {
        ...routing,
        primary_connector: nextPreferred || null,
      },
    })
  }, [enabledEntries, onChange, preferredConnector, routing, value])

  const updateConnectorField = (connectorName: ConnectorName, key: string, fieldValue: unknown) => {
    const current = value[connectorName] || {}
    onChange({
      ...value,
      [connectorName]: {
        ...current,
        [key]: fieldValue,
      },
    })
  }

  const updateConnectorFields = (connectorName: ConnectorName, patch: Record<string, unknown>) => {
    const current = value[connectorName] || {}
    onChange({
      ...value,
      [connectorName]: {
        ...current,
        ...patch,
      },
    })
  }

  const updateRouting = (patch: Record<string, unknown>) => {
    onChange({
      ...value,
      _routing: {
        ...routing,
        ...patch,
      },
    })
  }

  const renderRoutingSection = () => (
    <section className="border-b border-black/[0.08] pb-6 dark:border-white/[0.08]">
      <div id="connectors-routing" className="mb-3 flex items-center gap-2 text-sm font-medium">
        <span>{t.routingTitle}</span>
        <HintDot label={t.routingSubtitle} />
        <AnchorJumpButton anchorId="connectors-routing" onJumpToAnchor={onJumpToAnchor} />
      </div>

      {enabledEntries.length === 0 ? (
        <div className="text-sm text-muted-foreground">{t.routingEmpty}</div>
      ) : (
        <div className="space-y-5">
          <div>
            <div className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">{t.primaryConnector}</div>
            <div className="flex flex-wrap gap-2">
              {enabledEntries.map((entry) => {
                const selected = preferredConnector === entry.name
                return (
                  <button
                    key={entry.name}
                    type="button"
                    onClick={() => updateRouting({ primary_connector: entry.name })}
                    className={cn(
                      'rounded-full border px-3 py-2 text-sm transition',
                      selected
                        ? 'border-black/[0.14] bg-black/[0.05] text-foreground dark:border-white/[0.18] dark:bg-white/[0.08]'
                        : 'border-black/[0.08] bg-white/[0.44] text-muted-foreground hover:text-foreground dark:border-white/[0.12] dark:bg-white/[0.03]'
                    )}
                  >
                    {translateSettingsCatalogText(locale, entry.label)}
                  </button>
                )
              })}
            </div>
            {enabledEntries.length === 1 ? <div className="mt-2 text-xs text-muted-foreground">{t.routingAutoSingle}</div> : null}
          </div>

          <div>
            <div className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">{t.deliveryPolicy}</div>
            <div className="flex flex-wrap gap-2">
              {[
                { value: 'fanout_all', label: t.fanoutAll },
                { value: 'primary_only', label: t.primaryOnly },
                { value: 'primary_plus_local', label: t.primaryPlusLocal },
              ].map((option) => {
                const selected = deliveryPolicy === option.value
                return (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => updateRouting({ artifact_delivery_policy: option.value })}
                    className={cn(
                      'rounded-full border px-3 py-2 text-sm transition',
                      selected
                        ? 'border-black/[0.14] bg-black/[0.05] text-foreground dark:border-white/[0.18] dark:bg-white/[0.08]'
                        : 'border-black/[0.08] bg-white/[0.44] text-muted-foreground hover:text-foreground dark:border-white/[0.12] dark:bg-white/[0.03]'
                    )}
                  >
                    {translateSettingsCatalogText(locale, option.label)}
                  </button>
                )
              })}
            </div>
            <div className="mt-2 text-xs text-muted-foreground">{t.localMirror}</div>
          </div>
        </div>
      )}
    </section>
  )

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-4 border-b border-black/[0.08] pb-5 lg:flex-row lg:items-start lg:justify-between dark:border-white/[0.08]">
        <div className="min-w-0">
          {selectedEntry ? (
            <>
              <Button variant="secondary" onClick={onBackToConnectorCatalog} className="mb-3">
                <ArrowLeft className="h-4 w-4" />
                {t.backToCatalog}
              </Button>
              <div className="flex items-center gap-2">
                <h2 className="text-2xl font-semibold tracking-tight">{translateSettingsCatalogText(locale, selectedEntry.label)}</h2>
                <HintDot label={localizedGuideText(locale, connectorGuideCatalog[selectedEntry.name].summary)} />
              </div>
              <div className="mt-2 text-sm text-muted-foreground">{t.detailSubtitle}</div>
            </>
          ) : (
            <div className="flex items-center gap-2">
              <h2 className="text-2xl font-semibold tracking-tight">{t.overviewTitle}</h2>
              <HintDot label={t.overviewSubtitle} />
            </div>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button onClick={onSave} disabled={saving}>
            <Save className="h-4 w-4" />
            {saving ? t.saving : selectedEntry ? t.stepSaveAction : t.save}
          </Button>
        </div>
      </header>

      <div className="space-y-8">
        <div className="space-y-8">
          {selectedEntry ? (
            <ConnectorCard
              key={selectedEntry.name}
              entry={selectedEntry}
              locale={locale}
              config={value[selectedEntry.name] || {}}
              snapshot={snapshots.get(selectedEntry.name)}
              saving={saving}
              isDirty={isDirty}
              onUpdateField={updateConnectorField}
              onUpdateConnector={updateConnectorFields}
              onSave={onSave}
              onJumpToAnchor={onJumpToAnchor}
            />
          ) : (
            <>
              {renderRoutingSection()}
              <div className="grid gap-5 xl:grid-cols-2">
                {connectorCatalog.map((entry) => (
                  <ConnectorOverviewCard
                    key={entry.name}
                    entry={entry}
                    locale={locale}
                    config={value[entry.name] || {}}
                    onOpenConnector={onSelectConnector}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
