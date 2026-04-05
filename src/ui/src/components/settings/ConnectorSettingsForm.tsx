import {
  ArrowLeft,
  ArrowDownLeft,
  ArrowUpRight,
  Ban,
  BookOpenText,
  Check,
  CheckCircle2,
  Copy,
  Link2,
  Loader2,
  MessageSquareText,
  RadioTower,
  Save,
  Settings2,
  Trash2,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { flushSync } from 'react-dom'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { HintDot } from '@/components/ui/hint-dot'
import { Input } from '@/components/ui/input'
import { ConfirmModal, Modal, ModalFooter } from '@/components/ui/modal'
import { Textarea } from '@/components/ui/textarea'
import { useToast } from '@/components/ui/toast'
import { client } from '@/lib/api'
import { connectorTargetLabel, conversationIdentityKey, normalizeConnectorTargets } from '@/lib/connectors'
import { getDocAssetUrl } from '@/lib/docs'
import { normalizeZhUiCopy } from '@/lib/i18n/normalizeZhUiCopy'
import { copyToClipboard } from '@/lib/clipboard'
import { cn } from '@/lib/utils'
import type {
  ConnectorProfileSnapshot,
  ConnectorRecentEvent,
  ConnectorSnapshot,
  ConnectorTargetSnapshot,
  Locale,
  QuestSummary,
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
import {
  connectorConfigAutoEnabled,
  lingzhuAuthAkNeedsRotation,
  qqProfileDisplayLabel,
  qqProfileStatus,
  resolveLingzhuAuthAk,
  selectQqProfileTarget,
} from './connectorSettingsHelpers'
import { translateSettingsCatalogText } from './settingsCatalogI18n'

function TruncatedLine({
  value,
  className,
  mono = false,
}: {
  value: string | null | undefined
  className?: string
  mono?: boolean
}) {
  const text = String(value || '').trim()
  return (
    <div
      className={cn('truncate', mono && 'font-mono', className)}
      title={text || undefined}
    >
      {text || '—'}
    </div>
  )
}

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
    enableConnectorFirst: 'Fill the missing credentials first.',
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
    weixinAddConnector: 'Bind WeChat',
    weixinRebindConnector: 'Rebind WeChat',
    weixinBindHint: 'DeepScientist generates a QR code, you scan it with WeChat, and the connector is saved automatically after confirmation.',
    weixinCurrentBinding: 'Current WeChat binding',
    weixinAccountId: 'Bot account',
    weixinLoginUserId: 'Owner account',
    weixinNotBoundYet: 'Not bound yet.',
    weixinQrModalTitle: 'Scan With WeChat',
    weixinQrLoading: 'Generating WeChat QR code…',
    weixinQrHint1: 'Open WeChat on the phone that will own this binding and scan this QR code.',
    weixinQrHint2: 'Confirm the login inside WeChat. DeepScientist saves the connector automatically after success.',
    weixinQrHint3: '',
    weixinBindingSuccessTitle: 'WeChat connected',
    weixinBindingSuccessBody: 'The WeChat connector was saved automatically.',
    weixinBindingFailedTitle: 'WeChat binding failed',
    weixinDeleteAction: 'Delete WeChat',
    weixinDeleteTitle: 'Delete WeChat binding',
    weixinDeleteConfirm: 'This will clear the saved WeChat bot token and account binding from DeepScientist.',
    weixinDeleteSuccessTitle: 'WeChat deleted',
    weixinDeleteSuccessBody: 'The WeChat connector binding was removed.',
    lingzhuQuickSetup: 'Quick setup',
    lingzhuStepEndpoint: 'Gateway endpoint',
    lingzhuStepPlatform: 'Generate binding values',
    lingzhuStepProbe: 'Test, verify, and save',
    lingzhuNeedPublicIp: 'Lingzhu requires a public IP or public domain. The popup auto-generates values from the current DeepScientist web address, but only a public URL can be registered on Rokid.',
    lingzhuUseLocalDefaults: 'Use current web address',
    lingzhuGenerateAk: 'Generate AK',
    lingzhuGeneratedValues: 'Generated values',
    lingzhuLocalHealthUrl: 'DeepScientist health URL',
    lingzhuLocalSseUrl: 'DeepScientist SSE URL',
    lingzhuPublicSseUrl: 'External SSE URL',
    lingzhuPublicHint: 'The custom agent URL is generated from the current DeepScientist web address. Only a public URL can be registered on Rokid.',
    lingzhuOpenclawConfig: 'OpenClaw config snippet',
    lingzhuCurl: 'Probe curl',
    lingzhuSupportedCommands: 'Supported commands',
    lingzhuSnapshotHint: 'The runtime probe checks local reachability only. It does not prove that your public IP is already exposed correctly.',
    lingzhuRunProbe: 'Run Lingzhu probe',
    lingzhuProbeResult: 'Lingzhu probe',
    lingzhuNoProbeYet: 'Run the probe after saving the AK and endpoint values.',
    lingzhuAgentIdHint: 'Use the same agent id on both OpenClaw and Lingzhu.',
    lingzhuPlatformReminder: 'Open the popup, copy the generated values into the Rokid form, then click Save here to finish.',
    lingzhuCompleteEndpointFirst: 'The current DeepScientist web address has not been generated yet.',
    lingzhuSavePlatformValuesFirst: 'Save the generated URL, AK, and agent values before checking the runtime snapshot.',
    lingzhuAddConnector: 'Add Lingzhu (Rokid Glasses)',
    lingzhuPlatformUrl: 'Rokid platform',
    lingzhuOpenPlatform: 'Open platform',
    lingzhuGeneratedForRokid: 'Generated fields for Rokid binding',
    lingzhuRokidBindHint: 'DeepScientist generates these values automatically. Copy them into the Rokid custom agent form, then click Save here to finish binding.',
    lingzhuCurrentBindingValues: 'Current Lingzhu values',
    lingzhuAkPersistenceHint: 'The Custom agent AK is generated randomly. Click Save to persist it, and keep the same AK on the Rokid platform and DeepScientist.',
    lingzhuCustomAgentId: 'Custom agent ID',
    lingzhuCustomAgentUrl: 'Custom agent URL',
    lingzhuCustomAgentAk: 'Custom agent AK',
    lingzhuAgentName: 'Agent name',
    lingzhuCategory: 'Category',
    lingzhuCapabilitySummary: 'Capability summary',
    lingzhuOpeningMessage: 'Opening message',
    lingzhuInputType: 'Input type',
    lingzhuIcon: 'Icon',
    lingzhuCategoryWork: 'Work',
    lingzhuInputTypeText: 'Text',
    lingzhuCopyValue: 'Copy',
    lingzhuCopiedValue: 'Copied',
    lingzhuIconHint: 'Upload the DeepScientist logo on the Rokid platform. If the platform accepts a URL, you can copy the logo URL below.',
    lingzhuCopyLogoUrl: 'Copy logo URL',
    lingzhuBindingGuideTitle: 'How to bind Rokid Glasses',
    lingzhuBindingGuide1: 'Open the Rokid platform and go to Project Development -> Third-party Agent -> Create.',
    lingzhuBindingGuide2: 'Choose `Custom Agent`, then paste the generated agent ID, public URL, and AK.',
    lingzhuBindingGuide3: 'Use the default values below for agent name, category, capability summary, opening message, and input type.',
    lingzhuBindingGuide4: 'Upload the DeepScientist logo as the icon. The custom agent URL must be publicly reachable.',
    lingzhuBindingGuide5: 'After the Rokid form is filled, return here and click Save to finish binding.',
    lingzhuBindingGuide6: 'When giving a new task from the glasses, start with `我现在的任务是 ...`. Only that prefix is treated as a fresh DeepScientist instruction.',
    lingzhuBindingGuide7: 'If the connection drops, ask again without that prefix, such as `找DeepScientist` or `继续`. DeepScientist will replay buffered progress updates instead of resubmitting the task.',
    lingzhuCurrentAddress: 'Current DeepScientist web address',
    lingzhuManualOverrides: 'Manual overrides and debug',
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
    enableConnectorFirst: '请先补齐缺少的凭据。',
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
    weixinAddConnector: '绑定微信',
    weixinRebindConnector: '重新绑定微信',
    weixinBindHint: 'DeepScientist 会自动生成二维码。你只需要用微信扫码并确认，之后 connector 会自动保存。',
    weixinCurrentBinding: '当前微信绑定',
    weixinAccountId: '机器人账号',
    weixinLoginUserId: '扫码账号',
    weixinNotBoundYet: '当前还没有绑定。',
    weixinQrModalTitle: '请使用微信扫码',
    weixinQrLoading: '正在生成微信二维码…',
    weixinQrHint1: '请在将要持有这个绑定的手机微信上扫码。',
    weixinQrHint2: '扫码后在微信里确认登录。成功后 DeepScientist 会自动保存 connector。',
    weixinQrHint3: '',
    weixinBindingSuccessTitle: '微信已连接',
    weixinBindingSuccessBody: '微信 connector 已自动保存。',
    weixinBindingFailedTitle: '微信绑定失败',
    weixinDeleteAction: '删除微信',
    weixinDeleteTitle: '删除微信绑定',
    weixinDeleteConfirm: '这会清掉 DeepScientist 中保存的微信 bot token 和账号绑定信息。',
    weixinDeleteSuccessTitle: '微信已删除',
    weixinDeleteSuccessBody: '微信 connector 绑定已移除。',
    lingzhuQuickSetup: '快速接入',
    lingzhuStepEndpoint: '网关端点',
    lingzhuStepPlatform: '生成绑定信息',
    lingzhuStepProbe: '测试验证并保存',
    lingzhuNeedPublicIp: 'Lingzhu 需要公网 IP 或公网域名。弹窗会基于当前 DeepScientist 网页地址自动生成绑定值，但 Rokid 平台只能注册公网 URL。',
    lingzhuUseLocalDefaults: '使用当前网页地址',
    lingzhuGenerateAk: '生成 AK',
    lingzhuGeneratedValues: '自动生成值',
    lingzhuLocalHealthUrl: 'DeepScientist 健康检查 URL',
    lingzhuLocalSseUrl: 'DeepScientist SSE URL',
    lingzhuPublicSseUrl: '外部 SSE URL',
    lingzhuPublicHint: '自定义智能体 URL 会按当前 DeepScientist 网页地址自动生成，但只有公网 URL 才能在 Rokid 平台注册。',
    lingzhuOpenclawConfig: 'OpenClaw 配置片段',
    lingzhuCurl: '探测 curl',
    lingzhuSupportedCommands: '支持的命令',
    lingzhuSnapshotHint: '运行时探测只能检查本地可达性，不能替代公网暴露是否正确的最终验证。',
    lingzhuRunProbe: '执行 Lingzhu 探测',
    lingzhuProbeResult: 'Lingzhu 探测结果',
    lingzhuNoProbeYet: '保存 AK 和端点后，再执行探测。',
    lingzhuAgentIdHint: 'OpenClaw 与 Lingzhu 两侧应使用同一个 agent id。',
    lingzhuPlatformReminder: '打开弹窗后，把自动生成的值复制到 Rokid 表单里，随后在这里点保存即可完成。',
    lingzhuCompleteEndpointFirst: '当前 DeepScientist 网页地址还没有成功生成。',
    lingzhuSavePlatformValuesFirst: '查看运行时快照前，请先保存自动生成的 URL、AK 和 agent 等平台值。',
    lingzhuAddConnector: 'Add Lingzhu（Rokid Glasses）',
    lingzhuPlatformUrl: 'Rokid 平台',
    lingzhuOpenPlatform: '打开平台',
    lingzhuGeneratedForRokid: 'Rokid 平台自动生成字段',
    lingzhuRokidBindHint: '下面这些值由 DeepScientist 自动生成。复制到 Rokid 自定义智能体表单后，再回到这里点保存即可完成绑定。自定义智能体 URL 必须是公网地址，不能填写 `127.0.0.1`。',
    lingzhuCurrentBindingValues: '当前 Lingzhu 绑定值',
    lingzhuAkPersistenceHint: '自定义智能体 AK 会随机生成。点击保存后才会真正持久化，之后 Rokid 平台和 DeepScientist 都必须使用同一个 AK。',
    lingzhuCustomAgentId: '自定义智能体ID',
    lingzhuCustomAgentUrl: '自定义智能体url',
    lingzhuCustomAgentAk: '自定义智能体AK',
    lingzhuAgentName: '智能体名称',
    lingzhuCategory: '类别',
    lingzhuCapabilitySummary: '功能介绍',
    lingzhuOpeningMessage: '开场白',
    lingzhuInputType: '入参类型',
    lingzhuIcon: '图标',
    lingzhuCategoryWork: '工作',
    lingzhuInputTypeText: '文字',
    lingzhuCopyValue: '复制',
    lingzhuCopiedValue: '已复制',
    lingzhuIconHint: '请在 Rokid 平台上传 DeepScientist logo。如果平台支持 URL，也可以直接复制下面的 logo 地址。',
    lingzhuCopyLogoUrl: '复制 logo URL',
    lingzhuBindingGuideTitle: '如何绑定 Rokid Glasses',
    lingzhuBindingGuide1: '打开 Rokid 平台，进入 项目开发 -> 三方智能体 -> 创建。',
    lingzhuBindingGuide2: '选择“自定义智能体”，然后粘贴自动生成的智能体 ID、公网 URL 和 AK。',
    lingzhuBindingGuide3: '智能体名称、类别、功能介绍、开场白、入参类型可以直接使用下方默认值。',
    lingzhuBindingGuide4: '图标上传 DeepScientist logo。自定义智能体 URL 必须是公网可访问地址。',
    lingzhuBindingGuide5: 'Rokid 表单填写完成后，回到这里点保存即可完成绑定。',
    lingzhuBindingGuide6: '眼镜侧下发新任务时，必须以“我现在的任务是 ...”开头；只有这个前缀会被当作新的 DeepScientist 指令。',
    lingzhuBindingGuide7: '如果中途断开，下一次直接再唤起即可，不要重复任务前缀；例如说“找DeepScientist”或“继续”，系统会优先补发中间进展，而不是重复提交任务。',
    lingzhuCurrentAddress: '当前 DeepScientist 网页地址',
    lingzhuManualOverrides: '手动覆盖与调试',
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

const normalizedCopy = {
  en: copy.en,
  zh: normalizeZhUiCopy(copy.zh),
} as const

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
  const t = normalizedCopy[locale]
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

const LINGZHU_PUBLIC_AGENT_ID = 'DeepScientist'

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

function isPrivateIpv4Host(hostname: string) {
  const octets = hostname.split('.').map((item) => Number.parseInt(item, 10))
  if (octets.length !== 4 || octets.some((item) => Number.isNaN(item) || item < 0 || item > 255)) {
    return false
  }
  const [first, second] = octets
  if (first === 0 || first === 10 || first === 127) return true
  if (first === 169 && second === 254) return true
  if (first === 172 && second >= 16 && second <= 31) return true
  if (first === 192 && second === 168) return true
  if (first === 100 && second >= 64 && second <= 127) return true
  return false
}

function isPublicBaseUrl(value: string) {
  const normalized = normalizeBaseUrl(value)
  if (!normalized) {
    return false
  }
  try {
    const url = new URL(normalized)
    const hostname = url.hostname.trim().toLowerCase()
    if (!hostname) {
      return false
    }
    if (hostname === 'localhost' || hostname === '0.0.0.0' || hostname === '::' || hostname === '::1') {
      return false
    }
    if (hostname.endsWith('.local')) {
      return false
    }
    if (/^\d+\.\d+\.\d+\.\d+$/.test(hostname)) {
      return !isPrivateIpv4Host(hostname)
    }
    const normalizedIpv6 = hostname.replace(/^\[|\]$/g, '')
    if (normalizedIpv6.includes(':')) {
      const lowered = normalizedIpv6.toLowerCase()
      if (lowered === '::1' || lowered === '::') {
        return false
      }
      if (lowered.startsWith('fc') || lowered.startsWith('fd') || lowered.startsWith('fe80')) {
        return false
      }
    }
    return true
  } catch {
    return false
  }
}

function lingzhuBrowserBaseUrl() {
  if (typeof window === 'undefined' || !window.location?.origin) {
    return ''
  }
  return normalizeBaseUrl(window.location.origin)
}

function lingzhuResolvedPublicBaseUrl(config: Record<string, unknown>) {
  const browserBaseUrl = lingzhuBrowserBaseUrl()
  if (isPublicBaseUrl(browserBaseUrl)) {
    return browserBaseUrl
  }
  const savedBaseUrl = lingzhuPublicBaseUrl(config)
  if (isPublicBaseUrl(savedBaseUrl)) {
    return savedBaseUrl
  }
  return ''
}

function lingzhuPublicSseUrl(config: Record<string, unknown>) {
  const base = lingzhuResolvedPublicBaseUrl(config)
  return base ? `${base}/metis/agent/api/sse` : ''
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

function lingzhuLogoUrl() {
  if (typeof window !== 'undefined' && window.location?.origin) {
    return new URL('/assets/branding/logo-rokid.png', window.location.origin).toString()
  }
  return '/assets/branding/logo-rokid.png'
}

function lingzhuDefaultAgentName(locale: Locale) {
  return locale === 'zh' ? 'DeepScientist' : 'DeepScientist'
}

function lingzhuDefaultCapabilitySummary(locale: Locale) {
  return locale === 'zh'
    ? 'DeepScientist 是一个本地优先的研究智能体，适合处理科研规划、实验执行、结果分析、论文写作与任务跟进。'
    : 'DeepScientist is a local-first research agent for planning, experiments, analysis, writing, and execution follow-up.'
}

function lingzhuDefaultOpeningMessage(locale: Locale) {
  return locale === 'zh'
    ? '你好，我是 DeepScientist。你可以直接告诉我研究目标、实验问题或需要推进的任务。'
    : 'Hello, I am DeepScientist. Tell me the research goal, experiment question, or task you want to move forward.'
}

function resolveWeixinQrContent(payload: { qrcode_content?: unknown; qrcode_url?: unknown }) {
  const explicit = String(payload.qrcode_content || '').trim()
  if (explicit) {
    return explicit
  }
  return String(payload.qrcode_url || '').trim()
}

function resolveWeixinQrImageUrl(payload: { qrcode_url?: unknown }) {
  const explicit = String(payload.qrcode_url || '').trim()
  if (!explicit) {
    return ''
  }
  if (explicit.startsWith('data:image/')) {
    return explicit
  }
  if (explicit.startsWith('blob:')) {
    return explicit
  }
  if (/^https?:\/\/.+\.(png|jpg|jpeg|gif|webp|svg)(?:$|[?#])/i.test(explicit)) {
    return explicit
  }
  return ''
}

function routingConfig(value: ConnectorConfigMap): Record<string, unknown> {
  const raw = value._routing
  return raw && typeof raw === 'object' ? raw : {}
}

function fieldHint(field: ConnectorField, locale: Locale) {
  const t = normalizedCopy[locale]
  const pieces = [
    translateSettingsCatalogText(locale, field.description),
    `${t.fieldHintPrefix} ${translateSettingsCatalogText(locale, field.whereToGet)}`,
  ]
  return pieces.filter(Boolean).join(' ')
}

function FieldHelp({ field, locale }: { field: ConnectorField; locale: Locale }) {
  const t = normalizedCopy[locale]
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
  const t = normalizedCopy[locale]
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
  const t = normalizedCopy[locale]

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

function CopyableValueCard({
  label,
  value,
  hint,
  copyLabel,
  copiedLabel,
  copied,
  onCopy,
  multiline = false,
}: {
  label: string
  value: string
  hint?: string
  copyLabel: string
  copiedLabel: string
  copied: boolean
  onCopy: () => void
  multiline?: boolean
}) {
  return (
    <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
      <div className="flex items-start justify-between gap-3">
        <div className="text-sm font-medium">{label}</div>
        <Button variant="secondary" size="sm" onClick={onCopy} className="shrink-0">
          {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          {copied ? copiedLabel : copyLabel}
        </Button>
      </div>
      {multiline ? (
        <Textarea
          value={value}
          readOnly
          className="mt-3 min-h-[120px] rounded-[18px] border-black/[0.08] bg-white/[0.44] text-sm shadow-none dark:bg-white/[0.03]"
        />
      ) : (
        <div
          className="mt-3 truncate rounded-[18px] border border-black/[0.06] bg-white/[0.44] px-3 py-3 text-sm dark:border-white/[0.08] dark:bg-white/[0.03]"
          title={value || undefined}
        >
          {value || '—'}
        </div>
      )}
      {hint ? <div className="mt-3 text-xs leading-5 text-muted-foreground">{hint}</div> : null}
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
  const t = normalizedCopy[locale]

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
              <TruncatedLine
                value={connectorTargetLabel(target)}
                className="text-sm font-medium text-foreground"
              />
              <TruncatedLine
                value={target.conversation_id}
                mono
                className="mt-1 text-xs text-muted-foreground"
              />
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
                {target.bound_quest_id || t.notBoundYet}
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
  const t = normalizedCopy[locale]
  const Icon = entry.icon
  const enabled = connectorConfigAutoEnabled(entry.name, config)
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

type ConnectorProfileBindingAction = {
  connectorName: ConnectorName
  profileId: string
  conversationId: string
  currentQuestId?: string | null
  nextQuestId?: string | null
}

function ConnectorProfileSettingsModal({
  open,
  locale,
  connectorName,
  profileId,
  profileLabel,
  preferredConversationId,
  profileSnapshot,
  targets,
  quests,
  busy,
  isDirty,
  onClose,
  onSaveBinding,
  onRequestDelete,
}: {
  open: boolean
  locale: Locale
  connectorName: ConnectorName
  profileId: string
  profileLabel: string
  preferredConversationId?: string | null
  profileSnapshot?: ConnectorProfileSnapshot | null
  targets: ConnectorTargetSnapshot[]
  quests: QuestSummary[]
  busy?: boolean
  isDirty?: boolean
  onClose: () => void
  onSaveBinding: (payload: ConnectorProfileBindingAction) => Promise<void> | void
  onRequestDelete: () => void
}) {
  const text =
    locale === 'zh'
      ? {
          title: 'Connector 设置',
          description: '管理当前 connector 实例的目标、绑定项目和运行统计。',
          target: '目标会话',
          targetPlaceholder: '选择一个已发现的目标',
          quest: '绑定项目',
          questPlaceholder: '不绑定任何项目',
          unbound: '不绑定项目',
          noTargets: '这个 connector 还没有发现可绑定的会话。先从平台侧发来一条真实消息。',
          currentBinding: '当前绑定',
          notBound: '当前未绑定到任何项目。',
          stats: '运行统计',
          received: '接收总数',
          sent: '发送总数',
          bindings: '绑定数',
          targets: '目标数',
          status: '状态',
          auth: '鉴权',
          save: '保存绑定',
          saving: '保存中…',
          delete: '删除 Connector',
          dirty: '请先保存当前未保存的 connector 配置，再修改绑定或删除。',
          bindHint: '保存时会自动把旧 quest 解绑，并重绑到新的 quest。',
          close: '关闭',
        }
      : {
          title: 'Connector settings',
          description: 'Manage the target conversation, bound quest, and runtime stats for this connector profile.',
          target: 'Target conversation',
          targetPlaceholder: 'Select a discovered target',
          quest: 'Bound quest',
          questPlaceholder: 'Keep this target unbound',
          unbound: 'Not bound',
          noTargets: 'No runtime target has been discovered for this connector yet. Send one real platform message first.',
          currentBinding: 'Current binding',
          notBound: 'This target is not currently bound to any quest.',
          stats: 'Runtime stats',
          received: 'Received',
          sent: 'Sent',
          bindings: 'Bindings',
          targets: 'Targets',
          status: 'Status',
          auth: 'Auth',
          save: 'Save binding',
          saving: 'Saving…',
          delete: 'Delete connector',
          dirty: 'Save the current connector config changes before changing bindings or deleting this profile.',
          bindHint: 'Saving here automatically unbinds the old quest and rebinds this target to the new quest.',
          close: 'Close',
        }

  const targetOptions = useMemo(() => {
    const seen = new Set<string>()
    return targets.filter((item) => {
      const key = conversationIdentityKey(item.conversation_id)
      if (!key || seen.has(key)) {
        return false
      }
      seen.add(key)
      return true
    })
  }, [targets])
  const defaultConversationId = useMemo(() => {
    const preferredKey = conversationIdentityKey(preferredConversationId || '')
    if (preferredKey) {
      const preferred = targetOptions.find((item) => conversationIdentityKey(item.conversation_id) === preferredKey)
      if (preferred) {
        return preferred.conversation_id
      }
    }
    return targetOptions.find((item) => item.bound_quest_id)?.conversation_id || targetOptions[0]?.conversation_id || ''
  }, [preferredConversationId, targetOptions])
  const [selectedConversationId, setSelectedConversationId] = useState('')
  const [selectedQuestId, setSelectedQuestId] = useState('')
  const [errorMessage, setErrorMessage] = useState('')

  useEffect(() => {
    if (!open) {
      return
    }
    setSelectedConversationId(defaultConversationId)
    const initialTarget = targetOptions.find(
      (item) => conversationIdentityKey(item.conversation_id) === conversationIdentityKey(defaultConversationId)
    )
    setSelectedQuestId(String(initialTarget?.bound_quest_id || '').trim())
    setErrorMessage('')
  }, [defaultConversationId, open, targetOptions])

  const selectedTarget =
    targetOptions.find((item) => conversationIdentityKey(item.conversation_id) === conversationIdentityKey(selectedConversationId)) || null
  const currentQuestId = String(selectedTarget?.bound_quest_id || '').trim()
  const hasBindingChange =
    Boolean(selectedConversationId) &&
    (selectedQuestId !== currentQuestId ||
      ((selectedQuestId || currentQuestId) &&
        conversationIdentityKey(selectedConversationId) !== conversationIdentityKey(defaultConversationId)))

  const handleSave = async () => {
    if (!selectedConversationId || busy || isDirty || !hasBindingChange) {
      return
    }
    setErrorMessage('')
    try {
      await onSaveBinding({
        connectorName,
        profileId,
        conversationId: selectedConversationId,
        currentQuestId: currentQuestId || null,
        nextQuestId: selectedQuestId || null,
      })
      onClose()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : String(error || 'Failed to update connector binding.'))
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={`${profileLabel} · ${text.title}`}
      description={`${connectorName} · ${profileId}. ${text.description}`}
      size="lg"
    >
      <div className="space-y-5">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="rounded-[20px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
            <label className="flex items-center gap-2 text-sm font-medium">
              <span>{text.target}</span>
            </label>
            <select
              value={selectedConversationId || ''}
              onChange={(event) => {
                const nextConversationId = event.target.value
                setSelectedConversationId(nextConversationId)
                const nextTarget =
                  targetOptions.find(
                    (item) => conversationIdentityKey(item.conversation_id) === conversationIdentityKey(nextConversationId)
                  ) || null
                setSelectedQuestId(String(nextTarget?.bound_quest_id || '').trim())
              }}
              className="mt-3 flex h-11 w-full rounded-[18px] border border-black/[0.08] bg-white/[0.44] px-3 py-2 text-sm shadow-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring dark:border-white/[0.12] dark:bg-white/[0.03]"
              disabled={busy || targetOptions.length === 0}
            >
              {targetOptions.length === 0 ? <option value="">{text.targetPlaceholder}</option> : null}
              {targetOptions.map((item) => (
                <option key={item.conversation_id} value={item.conversation_id}>
                  {connectorTargetLabel(item) || item.conversation_id}
                </option>
              ))}
            </select>
            {selectedTarget ? (
              <div className="mt-3 rounded-[14px] border border-black/[0.06] bg-black/[0.02] px-3 py-2 text-xs text-muted-foreground dark:border-white/[0.08] dark:bg-white/[0.03]">
                <TruncatedLine
                  value={connectorTargetLabel(selectedTarget)}
                  className="font-medium text-foreground"
                />
                <TruncatedLine
                  value={selectedTarget.conversation_id}
                  mono
                  className="mt-1"
                />
              </div>
            ) : (
              <div className="mt-3 text-xs leading-5 text-muted-foreground">{text.noTargets}</div>
            )}
          </div>

          <div className="rounded-[20px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
            <label className="flex items-center gap-2 text-sm font-medium">
              <span>{text.quest}</span>
            </label>
            <select
              value={selectedQuestId}
              onChange={(event) => setSelectedQuestId(event.target.value)}
              className="mt-3 flex h-11 w-full rounded-[18px] border border-black/[0.08] bg-white/[0.44] px-3 py-2 text-sm shadow-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring dark:border-white/[0.12] dark:bg-white/[0.03]"
              disabled={busy || !selectedConversationId}
            >
              <option value="">{text.unbound}</option>
              {quests.map((quest) => (
                <option key={quest.quest_id} value={quest.quest_id}>
                  {quest.quest_id}
                </option>
              ))}
            </select>
            <div className="mt-3 rounded-[14px] border border-black/[0.06] bg-black/[0.02] px-3 py-2 text-xs text-muted-foreground dark:border-white/[0.08] dark:bg-white/[0.03]">
              <div className="font-medium text-foreground">{text.currentBinding}</div>
              <div className="mt-1">{selectedTarget?.bound_quest_id || text.notBound}</div>
            </div>
            <div className="mt-3 text-xs leading-5 text-muted-foreground">{text.bindHint}</div>
          </div>
        </div>

        <div className="rounded-[20px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
          <div className="text-sm font-medium text-foreground">{text.stats}</div>
          <div className="mt-3 grid gap-3 text-sm text-muted-foreground sm:grid-cols-2 xl:grid-cols-4">
            <div>
              <span className="text-foreground">{text.received}:</span> {profileSnapshot?.inbox_count ?? 0}
            </div>
            <div>
              <span className="text-foreground">{text.sent}:</span> {profileSnapshot?.outbox_count ?? 0}
            </div>
            <div>
              <span className="text-foreground">{text.bindings}:</span> {profileSnapshot?.binding_count ?? targetOptions.filter((item) => item.bound_quest_id).length}
            </div>
            <div>
              <span className="text-foreground">{text.targets}:</span> {profileSnapshot?.target_count ?? targetOptions.length}
            </div>
            <div>
              <span className="text-foreground">{text.status}:</span>{' '}
              {translateSettingsCatalogText(locale, profileSnapshot?.connection_state || 'idle')}
            </div>
            <div>
              <span className="text-foreground">{text.auth}:</span>{' '}
              {translateSettingsCatalogText(locale, profileSnapshot?.auth_state || 'idle')}
            </div>
          </div>
        </div>

        {isDirty ? <div className="text-sm text-amber-700 dark:text-amber-300">{text.dirty}</div> : null}
        {errorMessage ? <div className="text-sm text-red-600 dark:text-red-300">{errorMessage}</div> : null}

        <ModalFooter className="-mx-6 -mb-4 mt-2 justify-between">
          <Button
            variant="secondary"
            onClick={onRequestDelete}
            disabled={busy || Boolean(isDirty)}
            className="text-red-600 hover:text-red-700 dark:text-red-300 dark:hover:text-red-200"
          >
            <Trash2 className="h-4 w-4" />
            {text.delete}
          </Button>
          <div className="flex items-center gap-3">
            <Button variant="secondary" onClick={onClose} disabled={busy}>
              {text.close}
            </Button>
            <Button onClick={() => void handleSave()} disabled={busy || Boolean(isDirty) || !hasBindingChange || !selectedConversationId}>
              {busy ? text.saving : text.save}
            </Button>
          </div>
        </ModalFooter>
      </div>
    </Modal>
  )
}

function ConnectorCard({
  entry,
  locale,
  config,
  snapshot,
  quests,
  saving,
  isDirty,
  deletingProfileKey,
  bindingProfileKey,
  onUpdateField,
  onUpdateConnector,
  onSave,
  onRefresh,
  onDeleteProfile,
  onManageProfileBinding,
  onJumpToAnchor,
}: {
  entry: ConnectorCatalogEntry
  locale: Locale
  config: Record<string, unknown>
  snapshot?: ConnectorSnapshot
  quests: QuestSummary[]
  saving: boolean
  isDirty: boolean
  deletingProfileKey?: string
  bindingProfileKey?: string
  onUpdateField: (connectorName: ConnectorName, key: string, value: unknown) => void
  onUpdateConnector: (connectorName: ConnectorName, patch: Record<string, unknown>) => void
  onSave: (draftOverride?: Record<string, unknown>) => Promise<boolean> | boolean
  onRefresh: () => Promise<void> | void
  onDeleteProfile: (connectorName: ConnectorName, profileId: string) => Promise<void> | void
  onManageProfileBinding: (payload: ConnectorProfileBindingAction) => Promise<void> | void
  onJumpToAnchor?: (anchorId: string) => void
}) {
  const t = normalizedCopy[locale]
  const { toast } = useToast()
  const Icon = entry.icon
  const enabled = connectorConfigAutoEnabled(entry.name, config)
  const guide = connectorGuideCatalog[entry.name]
  const [qqWizardOpen, setQqWizardOpen] = useState(false)
  const [qqWizardStep, setQqWizardStep] = useState<1 | 2 | 3>(1)
  const [qqWizardProfileId, setQqWizardProfileId] = useState<string | null>(null)
  const [qqWizardDraft, setQqWizardDraft] = useState<QqDraftProfile>(() => createQqDraftProfile())
  const [qqWizardPendingSaveProfileId, setQqWizardPendingSaveProfileId] = useState<string | null>(null)
  const [guidedWizardOpen, setGuidedWizardOpen] = useState(false)
  const [guidedWizardStep, setGuidedWizardStep] = useState(1)
  const [lingzhuWizardOpen, setLingzhuWizardOpen] = useState(false)
  const [weixinWizardOpen, setWeixinWizardOpen] = useState(false)
  const [weixinQrSessionKey, setWeixinQrSessionKey] = useState('')
  const [weixinQrContent, setWeixinQrContent] = useState('')
  const [weixinQrImageUrl, setWeixinQrImageUrl] = useState('')
  const [weixinQrLoading, setWeixinQrLoading] = useState(false)
  const [weixinQrSaving, setWeixinQrSaving] = useState(false)
  const [weixinQrError, setWeixinQrError] = useState('')
  const [weixinDeleteOpen, setWeixinDeleteOpen] = useState(false)
  const [weixinDeleting, setWeixinDeleting] = useState(false)
  const [copiedValueKey, setCopiedValueKey] = useState('')
  const [profileWizardOpen, setProfileWizardOpen] = useState(false)
  const [profileWizardStep, setProfileWizardStep] = useState<1 | 2 | 3>(1)
  const [profileWizardProfileId, setProfileWizardProfileId] = useState<string | null>(null)
  const [profileWizardDraft, setProfileWizardDraft] = useState<Record<string, unknown>>({})
  const [deleteProfileTarget, setDeleteProfileTarget] = useState<{ profileId: string; label: string } | null>(null)
  const [manageProfileTarget, setManageProfileTarget] = useState<{
    profileId: string
    label: string
    preferredConversationId?: string | null
    profileSnapshot?: ConnectorProfileSnapshot | null
    targets: ConnectorTargetSnapshot[]
  } | null>(null)
  const cardAnchorId = connectorAnchorId(entry.name)
  const useCompactGuidedLayout = entry.name !== 'qq'
  const connectorModalClassName = 'w-[min(92vw,1100px)] max-w-[calc(100vw-1.5rem)] overflow-y-auto lg:w-[50vw]'

  const closeWeixinWizard = () => {
    setWeixinWizardOpen(false)
    setWeixinQrSessionKey('')
    setWeixinQrContent('')
    setWeixinQrImageUrl('')
    setWeixinQrLoading(false)
    setWeixinQrSaving(false)
    setWeixinQrError('')
  }

  useEffect(() => {
    if (entry.name !== 'weixin' || !weixinWizardOpen || weixinQrSessionKey) {
      return
    }
    let cancelled = false

    const startLogin = async () => {
      setWeixinQrLoading(true)
      setWeixinQrError('')
      try {
        const payload = await client.startWeixinQrLogin({ force: true })
        if (cancelled) {
          return
        }
        const nextSessionKey = String(payload.session_key || '').trim()
        const nextQrContent = resolveWeixinQrContent(payload)
        const nextQrImageUrl = resolveWeixinQrImageUrl(payload)
        if (!nextSessionKey || !nextQrContent) {
          throw new Error(String(payload.message || 'Failed to create WeChat QR code.'))
        }
        setWeixinQrSessionKey(nextSessionKey)
        setWeixinQrContent(nextQrContent)
        setWeixinQrImageUrl(nextQrImageUrl)
      } catch (error) {
        if (!cancelled) {
          setWeixinQrError(error instanceof Error ? error.message : String(error || 'Failed to create WeChat QR code.'))
        }
      } finally {
        if (!cancelled) {
          setWeixinQrLoading(false)
        }
      }
    }

    void startLogin()
    return () => {
      cancelled = true
    }
  }, [entry.name, weixinQrSessionKey, weixinWizardOpen])

  useEffect(() => {
    if (entry.name !== 'weixin') {
      setWeixinQrImageUrl('')
      return
    }
    if (!weixinQrContent) {
      setWeixinQrImageUrl('')
      return
    }
    if (weixinQrImageUrl) {
      return
    }
    let cancelled = false

    const renderQrPng = async () => {
      try {
        const qrModule = (await import('qrcode')) as {
          toDataURL?: (content: string, options?: Record<string, unknown>) => Promise<string>
          default?: {
            toDataURL?: (content: string, options?: Record<string, unknown>) => Promise<string>
          }
        }
        const toDataURL = qrModule.toDataURL || qrModule.default?.toDataURL
        if (typeof toDataURL !== 'function') {
          throw new Error('QR renderer is unavailable.')
        }
        const nextImageUrl = await toDataURL(weixinQrContent, {
          errorCorrectionLevel: 'M',
          margin: 2,
          type: 'image/png',
          width: 360,
        })
        if (!cancelled) {
          setWeixinQrImageUrl(nextImageUrl)
        }
      } catch (error) {
        if (!cancelled) {
          setWeixinQrError(error instanceof Error ? error.message : String(error || 'Failed to render WeChat QR code.'))
        }
      }
    }

    void renderQrPng()
    return () => {
      cancelled = true
    }
  }, [entry.name, weixinQrContent, weixinQrImageUrl])

  useEffect(() => {
    if (entry.name !== 'weixin' || !weixinWizardOpen || !weixinQrSessionKey || weixinQrLoading || weixinQrSaving) {
      return
    }
    let cancelled = false
    let timer: number | null = null

    const pollLogin = async () => {
      try {
        const payload = await client.waitWeixinQrLogin({
          session_key: weixinQrSessionKey,
          timeout_ms: 1500,
        })
        if (cancelled) {
          return
        }
        if (payload.ok === false && !payload.connected) {
          throw new Error(String(payload.message || 'Failed to poll WeChat login state.'))
        }
        const nextQrContent = resolveWeixinQrContent(payload)
        const nextQrImageUrl = resolveWeixinQrImageUrl(payload)
        if (nextQrContent) {
          if (!nextQrImageUrl) {
            setWeixinQrImageUrl((current) => (current ? '' : current))
          }
          setWeixinQrContent((current) => (current === nextQrContent ? current : nextQrContent))
        }
        if (nextQrImageUrl) {
          setWeixinQrImageUrl((current) => (current === nextQrImageUrl ? current : nextQrImageUrl))
        }
        if (payload.connected) {
          setWeixinQrSaving(true)
          try {
            await Promise.resolve(onRefresh())
            toast({
              title: t.weixinBindingSuccessTitle,
              description: t.weixinBindingSuccessBody,
              variant: 'success',
            })
            closeWeixinWizard()
          } catch (error) {
            setWeixinQrError(error instanceof Error ? error.message : String(error || 'Failed to refresh WeChat settings.'))
          } finally {
            if (!cancelled) {
              setWeixinQrSaving(false)
            }
          }
          return
        }
        timer = window.setTimeout(() => {
          void pollLogin()
        }, 150)
      } catch (error) {
        if (cancelled) {
          return
        }
        const message = error instanceof Error ? error.message : String(error || 'Failed to poll WeChat login state.')
        setWeixinQrError(message)
        toast({
          title: t.weixinBindingFailedTitle,
          description: message,
          variant: 'destructive',
        })
      }
    }

    void pollLogin()
    return () => {
      cancelled = true
      if (timer != null) {
        window.clearTimeout(timer)
      }
    }
  }, [entry.name, onRefresh, t.weixinBindingFailedTitle, t.weixinBindingSuccessBody, t.weixinBindingSuccessTitle, toast, weixinQrLoading, weixinQrSaving, weixinQrSessionKey, weixinWizardOpen])

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
    const settingsReady = requiredReady
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

                {activeStepFields.length ? (
                  <div>
                    <div className="mb-3 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.stepFields}</div>
                    <div className="grid gap-4 md:grid-cols-2">
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
      ready: locale === 'zh' ? '已就绪' : 'Ready',
      bound: locale === 'zh' ? '已绑定' : 'Bound',
      profileId: locale === 'zh' ? 'Profile ID' : 'Profile ID',
      currentBot: locale === 'zh' ? '当前 Bot' : 'Current bot',
      savedTargets: locale === 'zh' ? '已保存的 QQ 目标' : 'Saved QQ targets',
      bindNotice:
        locale === 'zh'
          ? '当第一条私聊到达后，DeepScientist 会自动保存 OpenID，并且 QQ bot 会在该会话里回复绑定成功提示。'
          : 'After the first private message arrives, DeepScientist saves the OpenID automatically and the QQ bot replies with a binding-success notice in that same chat.',
      deleteBot: locale === 'zh' ? '删除 QQ Bot' : 'Delete QQ bot',
      deleteBotConfirm:
        locale === 'zh'
          ? '删除后会移除该 QQ bot 的配置，并清理它当前的绑定关系。'
          : 'Deleting removes this QQ bot profile and clears its current bindings.',
      saveFirstToDelete:
        locale === 'zh'
          ? '请先保存当前未保存的修改，再删除已有 QQ bot。'
          : 'Save the current unsaved changes before deleting an existing QQ bot.',
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
                const selectedTarget = selectQqProfileTarget(profileTargets, mainChatId)
                const profileTitle = qqProfileDisplayLabel(profile, profileSnapshot)
                const profileState = qqProfileStatus(profileSnapshot, profileTargets, mainChatId)
                const manageKey = `${entry.name}:${profile.profile_id}`
                return (
                  <div
                    key={profile.profile_id}
                    className="group rounded-[20px] border border-black/[0.06] bg-white/[0.62] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.04]"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <TruncatedLine value={profileTitle} className="text-sm font-medium text-foreground" />
                        <TruncatedLine value={profile.app_id || '—'} mono className="mt-1 text-xs text-muted-foreground" />
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          title={locale === 'zh' ? '管理 Connector' : 'Manage connector'}
                          onClick={() =>
                            setManageProfileTarget({
                              profileId: profile.profile_id,
                              label: profileTitle,
                              preferredConversationId:
                                profileTargets.find((item) => item.bound_quest_id)?.conversation_id ||
                                selectedTarget?.conversation_id ||
                                profileSnapshot?.default_conversation_id ||
                                null,
                              profileSnapshot: profileSnapshot || null,
                              targets: profileTargets,
                            })
                          }
                          disabled={saving || Boolean(deletingProfileKey)}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-black/[0.08] bg-white/[0.72] text-muted-foreground transition hover:border-black/[0.14] hover:bg-black/[0.04] hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 dark:border-white/[0.12] dark:bg-white/[0.06]"
                        >
                          <Settings2 className="h-4 w-4" />
                        </button>
                        <Badge variant={profileState === 'waiting' ? 'secondary' : 'default'}>
                          {bindingProfileKey === manageKey
                            ? locale === 'zh'
                              ? '更新中'
                              : 'Updating'
                            : profileState === 'bound'
                              ? qqCopy.bound
                              : profileState === 'ready'
                                ? qqCopy.ready
                                : qqCopy.waiting}
                        </Badge>
                      </div>
                    </div>
                    <div className="mt-3 grid gap-2 text-xs text-muted-foreground md:grid-cols-2">
                      <div>
                        <span className="text-foreground">{qqCopy.profileId}:</span> {profile.profile_id}
                      </div>
                      <div>
                        <span className="text-foreground">{t.boundQuestLabel}:</span>{' '}
                        {selectedTarget?.bound_quest_id || t.notBoundYet}
                      </div>
                    </div>
                    {selectedTarget ? (
                      <div className="mt-3 rounded-[14px] border border-black/[0.06] bg-black/[0.02] px-3 py-2 text-xs text-muted-foreground dark:border-white/[0.08] dark:bg-white/[0.03]">
                        <TruncatedLine
                          value={connectorTargetLabel(selectedTarget)}
                          className="font-medium text-foreground"
                        />
                        <TruncatedLine
                          value={selectedTarget.conversation_id}
                          mono
                          className="mt-1"
                        />
                      </div>
                    ) : null}
                  </div>
                )
              })
            )}
          </div>
        </section>

        <ConnectorProfileSettingsModal
          open={Boolean(manageProfileTarget)}
          locale={locale}
          connectorName={entry.name}
          profileId={manageProfileTarget?.profileId || ''}
          profileLabel={manageProfileTarget?.label || 'QQ'}
          preferredConversationId={manageProfileTarget?.preferredConversationId || null}
          profileSnapshot={manageProfileTarget?.profileSnapshot || null}
          targets={manageProfileTarget?.targets || []}
          quests={quests}
          busy={Boolean(manageProfileTarget && bindingProfileKey === `${entry.name}:${manageProfileTarget.profileId}`)}
          isDirty={isDirty}
          onClose={() => setManageProfileTarget(null)}
          onSaveBinding={(payload) => onManageProfileBinding(payload)}
          onRequestDelete={() => {
            if (!manageProfileTarget) return
            setManageProfileTarget(null)
            setDeleteProfileTarget({
              profileId: manageProfileTarget.profileId,
              label: manageProfileTarget.label,
            })
          }}
        />

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
              ? 'Step 1 先打开 QQ 平台并填写 App ID / App Secret；Step 2 等待第一条 QQ 私聊；Step 3 确认连接状态并展示最终绑定结果。'
              : 'Step 1 opens the QQ platform first and fills App ID / App Secret. Step 2 waits for the first QQ private message. Step 3 confirms the connection state and shows the final binding state.'
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
                      <TruncatedLine value={qqPlatformLink.href} className="mt-2 text-sm text-muted-foreground" />
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
                  <div className="mt-3 text-xs leading-5">{t.qqPlatformHint}</div>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
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
                  <div className="mt-3 grid gap-3 text-sm text-muted-foreground md:grid-cols-2">
                    <div>
                      <span className="text-foreground">{t.transportLabel}:</span> gateway_direct
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
                            <TruncatedLine
                              value={connectorTargetLabel(target)}
                              className="font-medium text-foreground"
                            />
                            <TruncatedLine
                              value={target.conversation_id}
                              mono
                              className="text-xs text-muted-foreground"
                            />
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
        <ConfirmModal
          open={Boolean(deleteProfileTarget)}
          onClose={() => {
            if (deletingProfileKey) return
            setDeleteProfileTarget(null)
          }}
          onConfirm={() => {
            if (!deleteProfileTarget) return
            void Promise.resolve()
              .then(() => onDeleteProfile(entry.name, deleteProfileTarget.profileId))
              .finally(() => {
                setDeleteProfileTarget(null)
              })
          }}
          loading={Boolean(deletingProfileKey)}
          title={qqCopy.deleteBot}
          description={
            isDirty
              ? qqCopy.saveFirstToDelete
              : deleteProfileTarget
                ? `${deleteProfileTarget.label}\n\n${qqCopy.deleteBotConfirm}`
                : qqCopy.deleteBotConfirm
          }
          confirmText={qqCopy.deleteBot}
          cancelText={qqCopy.close}
          variant="destructive"
        />
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
            deleteProfile: '删除 Connector',
            deleteProfileConfirm: '删除后会移除这个 connector 实例，并清理它当前的绑定关系。',
            saveFirstToDelete: '请先保存当前未保存的修改，再删除已有 connector。',
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
            deleteProfile: 'Delete connector',
            deleteProfileConfirm: 'Deleting removes this connector profile and clears its current bindings.',
            saveFirstToDelete: 'Save the current unsaved changes before deleting an existing connector.',
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
      const nextStructuredDraft = {
        ...value,
        [entry.name]: {
          ...config,
          enabled: true,
          profiles: [...profiles, nextProfile],
        },
      }
      onUpdateConnector(entry.name, {
        enabled: true,
        profiles: [...profiles, nextProfile],
      })
      setProfileWizardDraft(nextProfile)
      setProfileWizardProfileId(profileId)
      onSave(nextStructuredDraft)
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
                const manageKey = `${entry.name}:${profileId}`
                return (
                  <div
                    key={profileId}
                    className="group rounded-[20px] border border-black/[0.06] bg-white/[0.62] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.04]"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <TruncatedLine
                          value={profileSnapshot?.label || genericProfileLabel(connectorName, profile)}
                          className="text-sm font-medium text-foreground"
                        />
                        <TruncatedLine value={identifier || profileId} mono className="mt-1 text-xs text-muted-foreground" />
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          title={locale === 'zh' ? '管理 Connector' : 'Manage connector'}
                          onClick={() =>
                            setManageProfileTarget({
                              profileId,
                              label: (profileSnapshot?.label || genericProfileLabel(connectorName, profile) || profileId) as string,
                              preferredConversationId: profileTargets.find((item) => item.bound_quest_id)?.conversation_id || profileSnapshot?.last_conversation_id || null,
                              profileSnapshot: profileSnapshot || null,
                              targets: profileTargets,
                            })
                          }
                          disabled={saving || Boolean(deletingProfileKey)}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-black/[0.08] bg-white/[0.72] text-muted-foreground transition hover:border-black/[0.14] hover:bg-black/[0.04] hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 dark:border-white/[0.12] dark:bg-white/[0.06]"
                        >
                          <Settings2 className="h-4 w-4" />
                        </button>
                        <Badge variant={ready ? 'default' : 'secondary'}>
                          {bindingProfileKey === manageKey ? (locale === 'zh' ? '更新中' : 'Updating') : ready ? labels.ready : labels.waiting}
                        </Badge>
                      </div>
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

        <ConnectorProfileSettingsModal
          open={Boolean(manageProfileTarget)}
          locale={locale}
          connectorName={entry.name}
          profileId={manageProfileTarget?.profileId || ''}
          profileLabel={manageProfileTarget?.label || translateSettingsCatalogText(locale, entry.label)}
          preferredConversationId={manageProfileTarget?.preferredConversationId || null}
          profileSnapshot={manageProfileTarget?.profileSnapshot || null}
          targets={manageProfileTarget?.targets || []}
          quests={quests}
          busy={Boolean(manageProfileTarget && bindingProfileKey === `${entry.name}:${manageProfileTarget.profileId}`)}
          isDirty={isDirty}
          onClose={() => setManageProfileTarget(null)}
          onSaveBinding={(payload) => onManageProfileBinding(payload)}
          onRequestDelete={() => {
            if (!manageProfileTarget) return
            setManageProfileTarget(null)
            setDeleteProfileTarget({
              profileId: manageProfileTarget.profileId,
              label: manageProfileTarget.label,
            })
          }}
        />

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
                  <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 text-sm text-muted-foreground dark:border-white/[0.12] dark:bg-white/[0.04] md:col-span-2">
                    {localizedGuideText(locale, settingsStep?.description)}
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
                  <StepBlockerNotice
                    locale={locale}
                    description={locale === 'zh' ? '请先补齐缺少的凭据字段。' : 'Fill the missing credential fields first.'}
                    fields={missingRequiredFields}
                  />
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
        <ConfirmModal
          open={Boolean(deleteProfileTarget)}
          onClose={() => {
            if (deletingProfileKey) return
            setDeleteProfileTarget(null)
          }}
          onConfirm={() => {
            if (!deleteProfileTarget) return
            void Promise.resolve()
              .then(() => onDeleteProfile(entry.name, deleteProfileTarget.profileId))
              .finally(() => {
                setDeleteProfileTarget(null)
              })
          }}
          loading={Boolean(deletingProfileKey)}
          title={labels.deleteProfile}
          description={
            isDirty
              ? labels.saveFirstToDelete
              : deleteProfileTarget
                ? `${deleteProfileTarget.label}\n\n${labels.deleteProfileConfirm}`
                : labels.deleteProfileConfirm
          }
          confirmText={labels.deleteProfile}
          cancelText={t.wizardClose}
          variant="destructive"
        />
      </div>
    )
  }

  const renderLingzhuSetup = () => {
    const copyGeneratedValue = async (key: string, value: string) => {
      const success = await copyToClipboard(value)
      if (!success) {
        return
      }
      setCopiedValueKey(key)
      window.setTimeout(() => {
        setCopiedValueKey((current) => (current === key ? '' : current))
      }, 1600)
    }
    const lingzhuGuide = connectorGuideCatalog.lingzhu
    const platformGuideStep = lingzhuGuide.steps.find((step) => step.id === 'platform') || null
    const publicBaseUrl = lingzhuResolvedPublicBaseUrl(config)
    const publicSseUrl = lingzhuPublicSseUrl(config)
    const authAk = resolveLingzhuAuthAk(lingzhuConfigString(config, 'auth_ak'))
    const hasPublicBaseUrl = Boolean(publicBaseUrl && publicSseUrl)
    const rokidPlatformUrl = 'https://agent-develop.rokid.com/space'
    const logoUrl = lingzhuLogoUrl()
    const rokidBindingFields = [
      {
        key: 'custom-agent-id',
        label: t.lingzhuCustomAgentId,
        value: LINGZHU_PUBLIC_AGENT_ID,
      },
      {
        key: 'custom-agent-url',
        label: t.lingzhuCustomAgentUrl,
        value: publicSseUrl,
        hint: hasPublicBaseUrl ? t.lingzhuPublicHint : t.lingzhuNeedPublicIp,
      },
      {
        key: 'custom-agent-ak',
        label: t.lingzhuCustomAgentAk,
        value: authAk,
        hint: t.lingzhuAkPersistenceHint,
      },
      {
        key: 'agent-name',
        label: t.lingzhuAgentName,
        value: lingzhuDefaultAgentName(locale),
      },
      {
        key: 'category',
        label: t.lingzhuCategory,
        value: t.lingzhuCategoryWork,
      },
      {
        key: 'capability-summary',
        label: t.lingzhuCapabilitySummary,
        value: lingzhuDefaultCapabilitySummary(locale),
        multiline: true,
      },
      {
        key: 'opening-message',
        label: t.lingzhuOpeningMessage,
        value: lingzhuDefaultOpeningMessage(locale),
        multiline: true,
      },
      {
        key: 'input-type',
        label: t.lingzhuInputType,
        value: t.lingzhuInputTypeText,
      },
    ]
    const bindingGuideItems = [
      t.lingzhuBindingGuide1,
      t.lingzhuBindingGuide2,
      t.lingzhuBindingGuide3,
      t.lingzhuBindingGuide4,
      t.lingzhuBindingGuide6,
      t.lingzhuBindingGuide7,
    ]
    const openLingzhuWizard = () => {
      const patch: Record<string, unknown> = {}
      if (publicBaseUrl && lingzhuPublicBaseUrl(config) !== publicBaseUrl) patch.public_base_url = publicBaseUrl
      if (lingzhuConfigString(config, 'agent_id') !== LINGZHU_PUBLIC_AGENT_ID) patch.agent_id = LINGZHU_PUBLIC_AGENT_ID
      if (lingzhuAuthAkNeedsRotation(lingzhuConfigString(config, 'auth_ak')) || !authAk) {
        patch.auth_ak = createLingzhuAk()
      }
      if (Object.keys(patch).length) {
        onUpdateConnector(entry.name, patch)
      }
      setLingzhuWizardOpen(true)
    }

    return (
      <div className="space-y-5">
        <section className="rounded-[24px] border border-black/[0.08] bg-white/[0.48] p-5 dark:border-white/[0.12] dark:bg-white/[0.03]">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.bindConnectorTitle}</div>
              <h4 className="mt-2 text-lg font-semibold tracking-tight">{localizedGuideText(locale, lingzhuGuide.summary)}</h4>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">
                {hasPublicBaseUrl ? t.lingzhuRokidBindHint : t.lingzhuNeedPublicIp}
              </p>
            </div>
            <Button size="lg" className="rounded-full px-6" onClick={openLingzhuWizard}>
              <RadioTower className="h-4 w-4" />
              {t.lingzhuAddConnector}
            </Button>
          </div>

          {!hasPublicBaseUrl ? <StepBlockerNotice locale={locale} description={t.lingzhuNeedPublicIp} /> : null}
          {hasPublicBaseUrl || authAk ? (
            <div className="mt-4 rounded-[20px] border border-black/[0.06] bg-black/[0.02] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.03]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                {t.lingzhuCurrentBindingValues}
              </div>
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                {hasPublicBaseUrl ? (
                  <CopyableValueCard
                    label={t.lingzhuCustomAgentUrl}
                    value={publicSseUrl}
                    hint={t.lingzhuPublicHint}
                    copyLabel={t.lingzhuCopyValue}
                    copiedLabel={t.lingzhuCopiedValue}
                    copied={copiedValueKey === 'current-custom-agent-url'}
                    onCopy={() => void copyGeneratedValue('current-custom-agent-url', publicSseUrl)}
                  />
                ) : null}
                {authAk ? (
                  <CopyableValueCard
                    label={t.lingzhuCustomAgentAk}
                    value={authAk}
                    hint={t.lingzhuAkPersistenceHint}
                    copyLabel={t.lingzhuCopyValue}
                    copiedLabel={t.lingzhuCopiedValue}
                    copied={copiedValueKey === 'current-custom-agent-ak'}
                    onCopy={() => void copyGeneratedValue('current-custom-agent-ak', authAk)}
                  />
                ) : null}
              </div>
            </div>
          ) : null}
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
            {!hasPublicBaseUrl ? <StepBlockerNotice locale={locale} description={t.lingzhuNeedPublicIp} /> : null}

            {platformGuideStep?.image ? <ConnectorGuideImageCard image={platformGuideStep.image} locale={locale} /> : null}

            <div className="rounded-[24px] border border-black/[0.08] bg-white/[0.48] p-5 dark:border-white/[0.12] dark:bg-white/[0.03]">
              <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.lingzhuPlatformUrl}</div>
                  <h4 className="mt-2 text-lg font-semibold tracking-tight">{t.lingzhuGeneratedForRokid}</h4>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">{t.lingzhuRokidBindHint}</p>
                </div>
                <a
                  href={rokidPlatformUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-2 rounded-full border border-black/[0.08] bg-white/[0.52] px-3 py-2 text-sm transition hover:border-black/[0.14] hover:text-foreground dark:border-white/[0.12] dark:bg-white/[0.04]"
                >
                  <ArrowUpRight className="h-4 w-4" />
                  {t.lingzhuOpenPlatform}
                </a>
              </div>

              <div className="mt-5 grid gap-4 md:grid-cols-2">
                {rokidBindingFields.map((field) => (
                  <CopyableValueCard
                    key={field.key}
                    label={field.label}
                    value={field.value}
                    hint={field.hint}
                    multiline={field.multiline}
                    copyLabel={t.lingzhuCopyValue}
                    copiedLabel={t.lingzhuCopiedValue}
                    copied={copiedValueKey === field.key}
                    onCopy={() => {
                      if (field.value) {
                        void copyGeneratedValue(field.key, field.value)
                      }
                    }}
                  />
                ))}
                <div className="rounded-[22px] border border-black/[0.08] bg-white/[0.52] p-4 dark:border-white/[0.12] dark:bg-white/[0.04]">
                  <div className="flex items-start justify-between gap-3">
                    <div className="text-sm font-medium">{t.lingzhuIcon}</div>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => void copyGeneratedValue('logo-url', logoUrl)}
                      className="shrink-0"
                    >
                      {copiedValueKey === 'logo-url' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                      {copiedValueKey === 'logo-url' ? t.lingzhuCopiedValue : t.lingzhuCopyLogoUrl}
                    </Button>
                  </div>
                  <div className="mt-3 flex items-center gap-4 rounded-[18px] border border-black/[0.06] bg-white/[0.44] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.03]">
                    <img src={logoUrl} alt="DeepScientist logo" className="h-14 w-14 rounded-[14px] border border-black/[0.08] bg-white p-2 dark:border-white/[0.12]" />
                    <div className="min-w-0">
                      <div className="text-sm font-medium">{lingzhuDefaultAgentName(locale)}</div>
                      <TruncatedLine value={logoUrl} className="mt-1 text-xs text-muted-foreground" />
                    </div>
                  </div>
                  <div className="mt-3 text-xs leading-5 text-muted-foreground">{t.lingzhuIconHint}</div>
                </div>
              </div>
            </div>

            <div className="rounded-[24px] border border-black/[0.08] bg-white/[0.48] p-5 dark:border-white/[0.12] dark:bg-white/[0.03]">
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.lingzhuBindingGuideTitle}</div>
              <ol className="mt-3 space-y-2 text-sm leading-6 text-muted-foreground">
                {bindingGuideItems.map((item, index) => (
                  <li key={`lingzhu-binding-guide:${index}`}>{index + 1}. {item}</li>
                ))}
              </ol>
            </div>

            <ModalFooter className="-mx-6 -mb-4 mt-2">
              <Button variant="secondary" onClick={() => setLingzhuWizardOpen(false)}>
                {t.wizardClose}
              </Button>
              <Button
                onClick={() => {
                  void (async () => {
                    if (isDirty) {
                      const saved = await Promise.resolve(onSave())
                      if (!saved) {
                        return
                      }
                    }
                    setLingzhuWizardOpen(false)
                  })()
                }}
                disabled={saving || !hasPublicBaseUrl || !authAk}
              >
                {saving ? t.saving : t.save}
              </Button>
            </ModalFooter>
          </div>
        </Modal>
      </div>
    )
  }

  const renderWeixinSetup = () => {
    const accountId = String(config.account_id || '').trim()
    const loginUserId = String(config.login_user_id || '').trim()
    const hasBinding = Boolean(accountId)
    const introGuideImage =
      guide.steps.find((step) => step.id === 'platform')?.image ||
      guide.steps.find((step) => step.id === 'scan')?.image ||
      guide.steps[0]?.image ||
      null

    const openWeixinWizard = () => {
      setWeixinQrSessionKey('')
      setWeixinQrContent('')
      setWeixinQrImageUrl('')
      setWeixinQrLoading(false)
      setWeixinQrSaving(false)
      setWeixinQrError('')
      setWeixinWizardOpen(true)
    }

    const deleteWeixinBinding = async () => {
      setWeixinDeleting(true)
      try {
        flushSync(() => {
          onUpdateConnector(entry.name, {
            enabled: false,
            bot_token: null,
            bot_token_env: null,
            account_id: null,
            login_user_id: null,
          })
        })
        const saved = await Promise.resolve(onSave())
        if (!saved) {
          throw new Error(locale === 'zh' ? '微信删除保存失败。' : 'Failed to save WeChat deletion.')
        }
        toast({
          title: t.weixinDeleteSuccessTitle,
          description: t.weixinDeleteSuccessBody,
          variant: 'success',
        })
        setWeixinDeleteOpen(false)
      } catch (error) {
        toast({
          title: t.weixinBindingFailedTitle,
          description: error instanceof Error ? error.message : String(error || 'Failed to delete WeChat binding.'),
          variant: 'destructive',
        })
      } finally {
        setWeixinDeleting(false)
      }
    }

    return (
      <div className="space-y-5">
        <section className="rounded-[24px] border border-black/[0.08] bg-white/[0.48] p-5 dark:border-white/[0.12] dark:bg-white/[0.03]">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.bindConnectorTitle}</div>
              <h4 className="mt-2 text-lg font-semibold tracking-tight">{localizedGuideText(locale, guide.summary)}</h4>
              <p className="mt-1 text-sm leading-6 text-muted-foreground">{t.weixinBindHint}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {guide.links.map((link, index) => (
                  <ConnectorGuideLinkButton
                    key={`weixin-guide-link:${index}:${link.kind === 'external' ? link.href : link.docSlug}`}
                    link={link}
                    locale={locale}
                  />
                ))}
              </div>
            </div>
            <Button size="lg" className="rounded-full px-6" onClick={openWeixinWizard}>
              <RadioTower className="h-4 w-4" />
              {hasBinding ? t.weixinRebindConnector : t.weixinAddConnector}
            </Button>
          </div>

          {introGuideImage ? (
            <div className="mt-4">
              <ConnectorGuideImageCard image={introGuideImage} locale={locale} />
            </div>
          ) : null}

          <div className="mt-4 rounded-[20px] border border-black/[0.06] bg-black/[0.02] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.03]">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{t.weixinCurrentBinding}</div>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div className="rounded-[18px] border border-black/[0.06] bg-white/[0.44] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.03]">
                <div className="text-sm font-medium">{t.weixinAccountId}</div>
                <TruncatedLine value={accountId || t.weixinNotBoundYet} className="mt-2 text-sm text-muted-foreground" />
              </div>
              <div className="rounded-[18px] border border-black/[0.06] bg-white/[0.44] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.03]">
                <div className="text-sm font-medium">{t.weixinLoginUserId}</div>
                <TruncatedLine value={loginUserId || t.weixinNotBoundYet} className="mt-2 text-sm text-muted-foreground" />
              </div>
            </div>
            {hasBinding ? (
              <div className="mt-4 flex justify-end">
                <Button
                  variant="secondary"
                  onClick={() => setWeixinDeleteOpen(true)}
                  className="text-red-600 hover:text-red-700 dark:text-red-300 dark:hover:text-red-200"
                >
                  <Trash2 className="h-4 w-4" />
                  {t.weixinDeleteAction}
                </Button>
              </div>
            ) : null}
          </div>
        </section>

        <Modal
          open={weixinWizardOpen}
          onClose={closeWeixinWizard}
          title={t.weixinQrModalTitle}
          size="xl"
          className="w-[min(96vw,980px)] max-w-[calc(100vw-1rem)]"
        >
          <div className="max-h-[calc(100dvh-8rem)] overflow-auto py-4 pr-1">
            <div className="grid min-w-[720px] grid-cols-[360px_minmax(320px,1fr)] gap-4">
              <div className="flex min-h-[420px] items-center justify-center rounded-[20px] border border-black/[0.06] bg-black/[0.02] px-4 py-4 dark:border-white/[0.08] dark:bg-white/[0.03]">
                {weixinQrError ? (
                  <div className="text-sm text-red-600 dark:text-red-300">{weixinQrError}</div>
                ) : weixinQrLoading || weixinQrSaving || (weixinQrContent && !weixinQrImageUrl) ? (
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                ) : weixinQrImageUrl ? (
                  <img
                    src={weixinQrImageUrl}
                    alt="Weixin QR code"
                    className="h-[320px] w-[320px] rounded-[24px] border border-black/[0.08] bg-white p-4 shadow-sm dark:border-white/[0.12]"
                  />
                ) : (
                  <div className="text-sm text-red-600 dark:text-red-300">{weixinQrError || t.weixinQrLoading}</div>
                )}
              </div>
              <div className="space-y-4">
                {introGuideImage ? (
                  <div className="overflow-hidden rounded-[20px] border border-black/[0.06] bg-white/[0.44] dark:border-white/[0.08] dark:bg-white/[0.03]">
                    <img
                      src={getDocAssetUrl(introGuideImage.assetPath)}
                      alt={localizedGuideText(locale, introGuideImage.alt)}
                      className="block w-full bg-white object-cover"
                      loading="lazy"
                    />
                  </div>
                ) : null}
                <div className="rounded-[20px] border border-black/[0.06] bg-black/[0.02] px-4 py-4 text-sm leading-6 text-muted-foreground dark:border-white/[0.08] dark:bg-white/[0.03]">
                  <p>{t.weixinQrHint1}</p>
                  <p>{t.weixinQrHint2}</p>
                  {t.weixinQrHint3 ? <p>{t.weixinQrHint3}</p> : null}
                </div>
              </div>
            </div>
          </div>
        </Modal>

        <ConfirmModal
          open={weixinDeleteOpen}
          onClose={() => {
            if (!weixinDeleting) {
              setWeixinDeleteOpen(false)
            }
          }}
          onConfirm={() => {
            void deleteWeixinBinding()
          }}
          title={t.weixinDeleteTitle}
          description={t.weixinDeleteConfirm}
          confirmText={t.weixinDeleteAction}
          cancelText={t.wizardClose}
          variant="danger"
          loading={weixinDeleting}
        />
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
          <span className="inline-flex items-center rounded-full border border-black/[0.08] bg-white/[0.52] px-3 py-2 text-sm text-muted-foreground dark:border-white/[0.12] dark:bg-white/[0.04]">
            {enabled ? t.enabled : t.disabled}
          </span>
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
          {entry.name === 'weixin'
            ? renderWeixinSetup()
            : entry.name === 'lingzhu'
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
                    <div className="flex min-w-0 gap-1">
                      <span className="shrink-0 text-foreground">{t.defaultTarget}:</span>
                      <span className="min-w-0 flex-1 truncate" title={connectorTargetLabel(snapshot.default_target)}>
                        {connectorTargetLabel(snapshot.default_target)}
                      </span>
                    </div>
                  ) : null}
                  {snapshot.main_chat_id && entry.name !== 'qq' ? (
                    <div className="flex min-w-0 gap-1">
                      <span className="shrink-0 text-foreground">{t.boundTarget}:</span>
                      <span className="min-w-0 flex-1 truncate" title={snapshot.main_chat_id}>
                        {snapshot.main_chat_id}
                      </span>
                    </div>
                  ) : null}
                  {snapshot.last_conversation_id ? (
                    <div className="flex min-w-0 gap-1">
                      <span className="shrink-0 text-foreground">{t.lastSeen}:</span>
                      <span className="min-w-0 flex-1 truncate" title={snapshot.last_conversation_id}>
                        {snapshot.last_conversation_id}
                      </span>
                    </div>
                  ) : null}
                  {entry.name === 'lingzhu' && snapshot.details ? (
                    <>
                      {typeof snapshot.details.health_url === 'string' ? (
                        <div className="flex min-w-0 gap-1">
                          <span className="shrink-0 text-foreground">{t.lingzhuLocalHealthUrl}:</span>
                          <span className="min-w-0 flex-1 truncate" title={String(snapshot.details.health_url)}>
                            {String(snapshot.details.health_url)}
                          </span>
                        </div>
                      ) : null}
                      {typeof snapshot.details.public_endpoint_url === 'string' && snapshot.details.public_endpoint_url ? (
                        <div className="flex min-w-0 gap-1">
                          <span className="shrink-0 text-foreground">{t.lingzhuPublicSseUrl}:</span>
                          <span className="min-w-0 flex-1 truncate" title={String(snapshot.details.public_endpoint_url)}>
                            {String(snapshot.details.public_endpoint_url)}
                          </span>
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
  quests,
  saving,
  isDirty,
  deletingProfileKey,
  bindingProfileKey,
  visibleConnectorNames,
  selectedConnectorName,
  onChange,
  onSave,
  onRefresh,
  onDeleteProfile,
  onManageProfileBinding,
  onSelectConnector,
  onBackToConnectorCatalog,
  onJumpToAnchor,
}: {
  locale: Locale
  value: ConnectorConfigMap
  connectors: ConnectorSnapshot[]
  quests: QuestSummary[]
  saving: boolean
  isDirty: boolean
  deletingProfileKey?: string
  bindingProfileKey?: string
  visibleConnectorNames: ConnectorName[]
  selectedConnectorName?: ConnectorName | null
  onChange: (next: ConnectorConfigMap) => void
  onSave: (draftOverride?: Record<string, unknown>) => Promise<boolean> | boolean
  onRefresh: () => Promise<void> | void
  onDeleteProfile: (connectorName: ConnectorName, profileId: string) => Promise<void> | void
  onManageProfileBinding: (payload: ConnectorProfileBindingAction) => Promise<void> | void
  onSelectConnector: (connectorName: ConnectorName) => void
  onBackToConnectorCatalog: () => void
  onJumpToAnchor?: (anchorId: string) => void
}) {
  const t = normalizedCopy[locale]
  const snapshots = useMemo(() => snapshotByName(connectors), [connectors])
  const routing = useMemo(() => routingConfig(value), [value])
  const visibleEntries = useMemo(
    () => connectorCatalog.filter((entry) => visibleConnectorNames.includes(entry.name)),
    [visibleConnectorNames]
  )
  const enabledEntries = useMemo(
    () =>
      visibleEntries.filter((entry) =>
        connectorConfigAutoEnabled(entry.name, (value[entry.name] as Record<string, unknown> | undefined) || {})
      ),
    [value, visibleEntries]
  )
  const preferredConnector = typeof routing.primary_connector === 'string' ? routing.primary_connector : ''
  const deliveryPolicy =
    typeof routing.artifact_delivery_policy === 'string' ? routing.artifact_delivery_policy : 'fanout_all'
  const selectedEntry =
    selectedConnectorName ? visibleEntries.find((entry) => entry.name === selectedConnectorName) || null : null

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
              quests={quests}
              saving={saving}
              isDirty={isDirty}
              deletingProfileKey={deletingProfileKey}
              bindingProfileKey={bindingProfileKey}
              onUpdateField={updateConnectorField}
              onUpdateConnector={updateConnectorFields}
              onSave={onSave}
              onRefresh={onRefresh}
              onDeleteProfile={onDeleteProfile}
              onManageProfileBinding={onManageProfileBinding}
              onJumpToAnchor={onJumpToAnchor}
            />
          ) : (
            <>
              {renderRoutingSection()}
              <div className="grid gap-5 xl:grid-cols-2">
                {visibleEntries.map((entry) => (
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
