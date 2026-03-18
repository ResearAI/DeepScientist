import type { Locale } from '@/types'

import type { ConnectorName } from './connectorCatalog'

export type LocalizedText = {
  en: string
  zh: string
}

export type ConnectorGuideLink =
  | {
      kind: 'external'
      label: LocalizedText
      href: string
    }
  | {
      kind: 'internal'
      label: LocalizedText
      docSlug: string
    }

export type ConnectorGuideImage = {
  assetPath: string
  alt: LocalizedText
  caption?: LocalizedText
}

export type ConnectorGuideStep = {
  id: string
  title: LocalizedText
  description: LocalizedText
  checklist?: LocalizedText[]
  fieldKeys?: string[]
  links?: ConnectorGuideLink[]
  image?: ConnectorGuideImage
  includeEnabledToggle?: boolean
}

export type ConnectorGuideEntry = {
  summary: LocalizedText
  requiredFieldKeys: string[]
  overviewChecks: LocalizedText[]
  links: ConnectorGuideLink[]
  steps: ConnectorGuideStep[]
}

export function localizedGuideText(locale: Locale, value?: LocalizedText | null) {
  if (!value) return ''
  return value[locale]
}

export function connectorGuideDocHref(locale: Locale, link: ConnectorGuideLink) {
  if (link.kind === 'external') {
    return link.href
  }
  return `/docs/${locale}/${link.docSlug}`
}

export const connectorGuideCatalog: Record<ConnectorName, ConnectorGuideEntry> = {
  telegram: {
    summary: {
      en: 'Create the bot in BotFather, keep polling enabled, then send one direct message and verify from DeepScientist.',
      zh: '先在 BotFather 创建机器人，保持 polling，然后先发一条私聊消息，再回到 DeepScientist 校验。',
    },
    requiredFieldKeys: ['bot_token'],
    overviewChecks: [
      {
        en: 'Default transport is `polling`, so no public webhook is required.',
        zh: '默认使用 `polling`，不需要公网 webhook。',
      },
      {
        en: 'The key credential is `bot_token` from BotFather.',
        zh: '关键凭据是从 BotFather 获取的 `bot_token`。',
      },
      {
        en: 'After saving, DM the bot with `/start` or `/help`, then run a probe.',
        zh: '保存后先给机器人发送 `/start` 或 `/help`，再执行联通测试。',
      },
    ],
    links: [
      {
        kind: 'external',
        label: { en: 'BotFather Tutorial', zh: 'BotFather 教程' },
        href: 'https://core.telegram.org/bots/tutorial',
      },
      {
        kind: 'external',
        label: { en: 'Telegram Bot Docs', zh: 'Telegram Bot 文档' },
        href: 'https://core.telegram.org/bots',
      },
      {
        kind: 'internal',
        label: { en: 'DeepScientist Settings Reference', zh: 'DeepScientist 设置参考' },
        docSlug: '01_SETTINGS_REFERENCE',
      },
    ],
    steps: [
      {
        id: 'platform',
        title: { en: 'Step 1. Create bot in BotFather', zh: 'Step 1. 在 BotFather 创建机器人' },
        description: {
          en: 'Open BotFather, create a bot with `/newbot`, and keep the generated token.',
          zh: '打开 BotFather，执行 `/newbot` 创建机器人，并保存生成的 token。',
        },
        image: {
          assetPath: 'images/connectors/telegram-setup-overview.svg',
          alt: { en: 'Telegram setup overview', zh: 'Telegram 配置步骤示意' },
          caption: {
            en: 'Start in BotFather, copy the token, then come back to DeepScientist with polling enabled.',
            zh: '先在 BotFather 创建机器人并复制 token，再回到 DeepScientist，保持 polling 即可。',
          },
        },
        checklist: [
          {
            en: 'Choose a bot display name and username.',
            zh: '确定机器人的显示名和用户名。',
          },
          {
            en: 'Copy the `bot_token` exactly once you receive it.',
            zh: '拿到 `bot_token` 后立刻完整保存。',
          },
          {
            en: 'If you plan to use groups, decide whether mention-only mode should stay enabled.',
            zh: '如果计划用于群组，先决定是否保留“仅被提及时响应”。',
          },
        ],
      },
      {
        id: 'settings',
        title: { en: 'Step 2. Fill Telegram settings', zh: 'Step 2. 填写 Telegram 设置' },
        description: {
          en: 'Enable the connector, keep `polling`, and paste the token into Settings.',
          zh: '启用连接器，保持 `polling`，然后把 token 填入 Settings。',
        },
        fieldKeys: ['transport', 'bot_name', 'bot_token', 'command_prefix', 'require_mention_in_groups'],
        includeEnabledToggle: true,
      },
      {
        id: 'verify',
        title: { en: 'Step 3. Save, DM, and verify', zh: 'Step 3. 保存、私聊并验证' },
        description: {
          en: 'Save first, send one private Telegram message to the bot, then choose the discovered target and run a probe.',
          zh: '先保存，再从 Telegram 给机器人发送一条私聊消息，然后选择自动发现的目标并发送测试消息。',
        },
        checklist: [
          {
            en: 'Use `/start`, `/help`, or any short private message.',
            zh: '发送 `/start`、`/help` 或任意一条简短私聊消息。',
          },
          {
            en: 'Return here and confirm that runtime targets are no longer empty.',
            zh: '回到这里确认运行时目标列表不再为空。',
          },
          {
            en: 'Run Check and Probe after the bot becomes reachable.',
            zh: '确认机器人可达后，再执行“校验”和“发送测试消息”。',
          },
        ],
        fieldKeys: ['dm_policy', 'allow_from', 'group_policy', 'group_allow_from', 'groups', 'auto_bind_dm_to_active_quest'],
      },
    ],
  },
  discord: {
    summary: {
      en: 'Use the Discord Developer Portal to create the app, keep Gateway mode, then invite the bot and test from a DM or server mention.',
      zh: '在 Discord Developer Portal 创建应用，保持 Gateway 模式，邀请机器人进入服务器后再从私聊或 @ 提及完成测试。',
    },
    requiredFieldKeys: ['bot_token', 'application_id'],
    overviewChecks: [
      {
        en: 'Default transport is `gateway`, not a public interactions callback.',
        zh: '默认使用 `gateway`，不是公网 interactions 回调。',
      },
      {
        en: 'Copy both `bot_token` and `application_id` from the Developer Portal.',
        zh: '需要从 Developer Portal 复制 `bot_token` 和 `application_id`。',
      },
      {
        en: 'After saving, invite the bot and generate one real message event before probing.',
        zh: '保存后先邀请机器人并制造一条真实消息事件，再执行探测。',
      },
    ],
    links: [
      {
        kind: 'external',
        label: { en: 'Discord Developer Portal', zh: 'Discord 开发者后台' },
        href: 'https://discord.com/developers/applications',
      },
      {
        kind: 'external',
        label: { en: 'Gateway Docs', zh: 'Gateway 文档' },
        href: 'https://docs.discord.com/developers/events/gateway',
      },
      {
        kind: 'internal',
        label: { en: 'DeepScientist Settings Reference', zh: 'DeepScientist 设置参考' },
        docSlug: '01_SETTINGS_REFERENCE',
      },
    ],
    steps: [
      {
        id: 'platform',
        title: { en: 'Step 1. Create the Discord app', zh: 'Step 1. 创建 Discord 应用' },
        description: {
          en: 'Create an application, open the Bot tab, and keep both the Bot Token and Application ID.',
          zh: '创建应用后打开 Bot 页面，保存 Bot Token 与 Application ID。',
        },
        image: {
          assetPath: 'images/connectors/discord-setup-overview.svg',
          alt: { en: 'Discord setup overview', zh: 'Discord 配置步骤示意' },
          caption: {
            en: 'The main path is Developer Portal -> Bot token + Application ID -> invite bot -> one real message.',
            zh: '主路径是 Developer Portal -> Bot token + Application ID -> 邀请机器人 -> 触发一条真实消息。',
          },
        },
        checklist: [
          {
            en: 'Create the app and enable the bot user.',
            zh: '创建应用并启用 bot 用户。',
          },
          {
            en: 'Copy `bot_token` from the Bot tab.',
            zh: '从 Bot 页面复制 `bot_token`。',
          },
          {
            en: 'Copy `application_id` from General Information.',
            zh: '从 General Information 复制 `application_id`。',
          },
        ],
      },
      {
        id: 'settings',
        title: { en: 'Step 2. Fill Discord settings', zh: 'Step 2. 填写 Discord 设置' },
        description: {
          en: 'Enable the connector, keep `gateway`, and paste the token and application id.',
          zh: '启用连接器，保持 `gateway`，填入 token 与 application id。',
        },
        fieldKeys: ['transport', 'bot_name', 'bot_token', 'application_id', 'guild_allowlist', 'require_mention_in_groups'],
        includeEnabledToggle: true,
      },
      {
        id: 'verify',
        title: { en: 'Step 3. Invite, mention, and verify', zh: 'Step 3. 邀请、提及并验证' },
        description: {
          en: 'Invite the bot to a server or DM it directly, trigger one real event, then run validation and a probe.',
          zh: '把机器人拉进服务器或直接私聊，触发一条真实事件后，再执行校验与探测。',
        },
        checklist: [
          {
            en: 'Send one DM or mention the bot in an allowed server channel.',
            zh: '在允许的服务器频道里 @ 机器人，或直接发一条私聊。',
          },
          {
            en: 'Check that discovered targets appear in the runtime panel.',
            zh: '确认运行时面板里已经出现 discovered targets。',
          },
          {
            en: 'Use the discovered target for the probe instead of typing ids blindly.',
            zh: '优先直接使用自动发现的目标，不要盲填 id。',
          },
        ],
        fieldKeys: ['dm_policy', 'allow_from', 'group_policy', 'group_allow_from', 'groups', 'auto_bind_dm_to_active_quest'],
      },
    ],
  },
  slack: {
    summary: {
      en: 'Create a Slack app, enable Socket Mode, generate the app-level token, then install the app and verify from DeepScientist.',
      zh: '创建 Slack App，开启 Socket Mode，生成 app-level token，然后安装应用并在 DeepScientist 中验证。',
    },
    requiredFieldKeys: ['bot_token', 'app_token'],
    overviewChecks: [
      {
        en: 'Default transport is `socket_mode`, so no public callback URL is required.',
        zh: '默认使用 `socket_mode`，不需要公网回调地址。',
      },
      {
        en: 'Slack requires both `bot_token` and `app_token`.',
        zh: 'Slack 需要同时填写 `bot_token` 和 `app_token`。',
      },
      {
        en: 'After installing the app, mention it once in Slack and then run a probe.',
        zh: '安装应用后，先在 Slack 里 @ 一次机器人，再执行探测。',
      },
    ],
    links: [
      {
        kind: 'external',
        label: { en: 'Slack App Dashboard', zh: 'Slack App 后台' },
        href: 'https://api.slack.com/apps',
      },
      {
        kind: 'external',
        label: { en: 'Using Socket Mode', zh: 'Socket Mode 文档' },
        href: 'https://docs.slack.dev/apis/events-api/using-socket-mode/',
      },
      {
        kind: 'internal',
        label: { en: 'DeepScientist Settings Reference', zh: 'DeepScientist 设置参考' },
        docSlug: '01_SETTINGS_REFERENCE',
      },
    ],
    steps: [
      {
        id: 'platform',
        title: { en: 'Step 1. Prepare the Slack app', zh: 'Step 1. 准备 Slack App' },
        description: {
          en: 'Create the app, turn on Socket Mode, and generate an app-level token in Basic Information.',
          zh: '创建应用，开启 Socket Mode，并在 Basic Information 中生成 app-level token。',
        },
        image: {
          assetPath: 'images/connectors/slack-setup-overview.svg',
          alt: { en: 'Slack setup overview', zh: 'Slack 配置步骤示意' },
          caption: {
            en: 'Slack needs both the bot token and the app-level token before the connector can receive events.',
            zh: 'Slack 需要先拿到 bot token 和 app-level token，connector 才能收事件。',
          },
        },
        checklist: [
          {
            en: 'Copy the Bot User OAuth Token (`xoxb-...`).',
            zh: '复制 Bot User OAuth Token（`xoxb-...`）。',
          },
          {
            en: 'Generate the App-Level Token (`xapp-...`).',
            zh: '生成 App-Level Token（`xapp-...`）。',
          },
          {
            en: 'Install the app into the target workspace.',
            zh: '把应用安装到目标工作区。',
          },
        ],
      },
      {
        id: 'settings',
        title: { en: 'Step 2. Fill Slack settings', zh: 'Step 2. 填写 Slack 设置' },
        description: {
          en: 'Enable the connector, keep `socket_mode`, and paste both tokens.',
          zh: '启用连接器，保持 `socket_mode`，并填入两个 token。',
        },
        fieldKeys: ['transport', 'bot_name', 'bot_token', 'app_token', 'bot_user_id', 'command_prefix', 'require_mention_in_groups'],
        includeEnabledToggle: true,
      },
      {
        id: 'verify',
        title: { en: 'Step 3. Mention the app and verify', zh: 'Step 3. 提及应用并验证' },
        description: {
          en: 'After saving, mention the app or DM it once so DeepScientist can learn a target, then run Check and Probe.',
          zh: '保存后先 @ 一次应用或发一条私聊，让 DeepScientist 学到目标，再执行校验与探测。',
        },
        checklist: [
          {
            en: 'Confirm `auth.test` style readiness succeeds first.',
            zh: '先确认 `auth.test` 风格的就绪检查成功。',
          },
          {
            en: 'Use a discovered target whenever possible.',
            zh: '能直接用自动发现目标时，不要手填会话 id。',
          },
          {
            en: 'Keep mention-only mode on in busy channels.',
            zh: '在活跃频道里建议保持“仅在被提及时响应”。',
          },
        ],
        fieldKeys: ['dm_policy', 'allow_from', 'group_policy', 'group_allow_from', 'groups', 'auto_bind_dm_to_active_quest'],
      },
    ],
  },
  feishu: {
    summary: {
      en: 'Create the app in Feishu Open Platform, keep long connection mode, then install the app and verify from a direct or group chat.',
      zh: '先在飞书开放平台创建应用，保持 long connection，然后安装应用并从私聊或群聊完成验证。',
    },
    requiredFieldKeys: ['app_id', 'app_secret'],
    overviewChecks: [
      {
        en: 'Default transport is `long_connection`, which avoids a public callback URL.',
        zh: '默认使用 `long_connection`，避免公网 callback URL。',
      },
      {
        en: 'The key credentials are `app_id` and `app_secret`.',
        zh: '关键凭据是 `app_id` 和 `app_secret`。',
      },
      {
        en: 'Only `app_id` and `app_secret` are required for the native Feishu setup.',
        zh: '原生飞书接入只需要 `app_id` 和 `app_secret`。',
      },
    ],
    links: [
      {
        kind: 'external',
        label: { en: 'Feishu Open Platform', zh: '飞书开放平台' },
        href: 'https://open.feishu.cn/app',
      },
      {
        kind: 'internal',
        label: { en: 'DeepScientist Settings Reference', zh: 'DeepScientist 设置参考' },
        docSlug: '01_SETTINGS_REFERENCE',
      },
    ],
    steps: [
      {
        id: 'platform',
        title: { en: 'Step 1. Create the Feishu app', zh: 'Step 1. 创建飞书应用' },
        description: {
          en: 'Open the Feishu developer console, create the app, and keep the App ID and App Secret.',
          zh: '打开飞书开发者后台，创建应用并保存 App ID 与 App Secret。',
        },
        image: {
          assetPath: 'images/connectors/feishu-setup-overview.svg',
          alt: { en: 'Feishu setup overview', zh: '飞书配置步骤示意' },
          caption: {
            en: 'In Feishu, the shortest path is Credentials -> App ID/App Secret -> long connection -> one real chat.',
            zh: '飞书里最短的路径是 Credentials -> App ID/App Secret -> long connection -> 一条真实聊天消息。',
          },
        },
        checklist: [
          {
            en: 'Create or open the target app in the Feishu console.',
            zh: '在飞书控制台里创建或打开目标应用。',
          },
          {
            en: 'Copy `app_id` and `app_secret` from the credentials page.',
            zh: '从凭据页面复制 `app_id` 和 `app_secret`。',
          },
          {
            en: 'Install or publish the app to the tenant that will chat with DeepScientist.',
            zh: '把应用安装或发布到将要和 DeepScientist 对话的租户。',
          },
        ],
      },
      {
        id: 'settings',
        title: { en: 'Step 2. Fill Feishu settings', zh: 'Step 2. 填写飞书设置' },
        description: {
          en: 'Enable the connector, keep `long_connection`, and paste the app credentials.',
          zh: '启用连接器，保持 `long_connection`，填入应用凭据。',
        },
        fieldKeys: ['transport', 'bot_name', 'app_id', 'app_secret', 'api_base_url', 'require_mention_in_groups'],
        includeEnabledToggle: true,
      },
      {
        id: 'verify',
        title: { en: 'Step 3. Start one real chat and verify', zh: 'Step 3. 触发一次真实聊天并验证' },
        description: {
          en: 'Save first, then send a message to the app in Feishu so runtime targets can be discovered before the probe.',
          zh: '先保存，再在飞书里给应用发消息，让运行时先发现目标，然后再做探测。',
        },
        checklist: [
          {
            en: 'If you use groups, mention the bot once in the target group.',
            zh: '如果要用群聊，先在目标群里 @ 一次机器人。',
          },
          {
            en: 'Check that tenant token exchange succeeds in Check.',
            zh: '先确认租户 token 交换在“校验”里成功。',
          },
          {
            en: 'After the first real chat lands, use the discovered target instead of typing ids manually.',
            zh: '第一条真实聊天到达后，优先使用自动发现目标，不要手填 id。',
          },
        ],
        fieldKeys: ['dm_policy', 'allow_from', 'group_policy', 'group_allow_from', 'groups', 'auto_bind_dm_to_active_quest'],
      },
    ],
  },
  whatsapp: {
    summary: {
      en: 'DeepScientist prefers local session mode. Save the local session settings, complete QR or pairing login, then send one real message and verify.',
      zh: 'DeepScientist 默认推荐本地会话模式。先保存本地会话设置，完成二维码或配对码登录，再发一条真实消息并验证。',
    },
    requiredFieldKeys: ['auth_method', 'session_dir'],
    overviewChecks: [
      {
        en: 'Required transport is `local_session`; this page no longer walks through Meta Cloud callbacks.',
        zh: '必选传输方式是 `local_session`；本页不再引导 Meta Cloud 回调方案。',
      },
      {
        en: 'For local session, the main choices are auth method and session directory.',
        zh: '对于本地会话，主要需要决定认证方式与 session 目录。',
      },
      {
        en: 'Complete QR or pairing login first, then wait for the first real message to discover the target id.',
        zh: '先完成二维码或配对码登录，再等待第一条真实消息来发现目标 id。',
      },
    ],
    links: [
      {
        kind: 'external',
        label: { en: 'WhatsApp Cloud API Docs', zh: 'WhatsApp Cloud API 文档' },
        href: 'https://developers.facebook.com/docs/whatsapp/cloud-api/get-started/',
      },
      {
        kind: 'internal',
        label: { en: 'DeepScientist Settings Reference', zh: 'DeepScientist 设置参考' },
        docSlug: '01_SETTINGS_REFERENCE',
      },
    ],
    steps: [
      {
        id: 'platform',
        title: { en: 'Step 1. Choose the local session path', zh: 'Step 1. 选择本地会话路径' },
        description: {
          en: 'Start with `local_session`, choose the login method, and decide where the local auth state should be stored.',
          zh: '先走 `local_session`，选择登录方式，并决定本地认证状态保存在哪个目录。',
        },
        image: {
          assetPath: 'images/connectors/whatsapp-setup-overview.svg',
          alt: { en: 'WhatsApp setup overview', zh: 'WhatsApp 配置步骤示意' },
          caption: {
            en: 'DeepScientist prefers local session mode: choose QR or pairing code, persist the session, then verify with one real message.',
            zh: 'DeepScientist 默认推荐本地会话模式：先选二维码或配对码，保存 session，再用一条真实消息完成验证。',
          },
        },
        checklist: [
          {
            en: 'Decide whether the machine can use QR login or needs pairing code mode.',
            zh: '先判断当前机器适合二维码登录还是配对码模式。',
          },
          {
            en: 'Keep the default session directory unless you need an isolated profile.',
            zh: '除非你需要独立 profile，否则保持默认 session 目录。',
          },
          {
            en: 'Make sure the machine can keep the session directory on disk between restarts.',
            zh: '确保这台机器重启后仍能保留 session 目录里的本地状态。',
          },
        ],
      },
      {
        id: 'settings',
        title: { en: 'Step 2. Fill WhatsApp settings', zh: 'Step 2. 填写 WhatsApp 设置' },
        description: {
          en: 'Enable the connector, keep `local_session`, and choose the auth method.',
          zh: '启用连接器，保持 `local_session`，并选择认证方式。',
        },
        fieldKeys: ['transport', 'bot_name', 'auth_method', 'session_dir', 'command_prefix'],
        includeEnabledToggle: true,
      },
      {
        id: 'verify',
        title: { en: 'Step 3. Complete login and verify', zh: 'Step 3. 完成登录并验证' },
        description: {
          en: 'After saving, complete the WhatsApp session login, send one real message, then run validation and a probe.',
          zh: '保存后完成 WhatsApp 会话登录，发送一条真实消息，再执行校验与探测。',
        },
        checklist: [
          {
            en: 'If the runtime shows a QR or pairing code, finish that flow first.',
            zh: '如果运行时显示二维码或配对码，先完成该登录流程。',
          },
          {
            en: 'Use a discovered target after the first inbound message lands.',
            zh: '第一条入站消息到达后，优先直接使用自动发现目标。',
          },
          {
            en: 'If login has not completed yet, finish QR or pairing first before expecting a discovered id.',
            zh: '如果登录还没完成，就先完成二维码或配对流程，再等待自动发现的 id。',
          },
        ],
        fieldKeys: ['dm_policy', 'allow_from', 'group_policy', 'group_allow_from', 'groups', 'auto_bind_dm_to_active_quest'],
      },
    ],
  },
  qq: {
    summary: {
      en: 'Use the official QQ bot platform, save App ID and App Secret, send one private message, then let DeepScientist auto-detect the OpenID.',
      zh: '使用 QQ 官方机器人平台，保存 App ID 与 App Secret，发送第一条私聊消息，然后让 DeepScientist 自动检测 OpenID。',
    },
    requiredFieldKeys: ['app_id', 'app_secret'],
    overviewChecks: [
      {
        en: 'QQ uses the built-in `gateway_direct` path and does not need a public callback URL.',
        zh: 'QQ 使用内置 `gateway_direct` 路径，不需要公网 callback URL。',
      },
      {
        en: 'The core credentials are `app_id` and `app_secret`.',
        zh: '核心凭据就是 `app_id` 和 `app_secret`。',
      },
      {
        en: 'The first real private QQ message teaches DeepScientist the correct OpenID automatically.',
        zh: '第一条真实 QQ 私聊会让 DeepScientist 自动学到正确的 OpenID。',
      },
    ],
    links: [
      {
        kind: 'external',
        label: { en: 'QQ Bot Platform', zh: 'QQ 机器人平台' },
        href: 'https://bot.q.qq.com/',
      },
      {
        kind: 'internal',
        label: { en: 'QQ Connector Guide', zh: 'QQ 接入指南' },
        docSlug: '03_QQ_CONNECTOR_GUIDE',
      },
      {
        kind: 'internal',
        label: { en: 'DeepScientist Settings Reference', zh: 'DeepScientist 设置参考' },
        docSlug: '01_SETTINGS_REFERENCE',
      },
    ],
    steps: [
      {
        id: 'platform',
        title: { en: 'Step 1. Register the QQ bot', zh: 'Step 1. 注册 QQ 机器人' },
        description: {
          en: 'Open the QQ bot platform, create the bot, and keep both App ID and App Secret.',
          zh: '打开 QQ 机器人平台，创建机器人，并保存 App ID 与 App Secret。',
        },
        image: {
          assetPath: 'images/qq/tencent-cloud-qq-register.png',
          alt: { en: 'QQ bot registration entry', zh: 'QQ 机器人注册入口' },
          caption: {
            en: 'Use this screenshot as a visual reference when locating the registration and console entry.',
            zh: '这个截图可以帮助你快速识别注册入口和控制台位置。',
          },
        },
      },
      {
        id: 'settings',
        title: { en: 'Step 2. Fill QQ settings', zh: 'Step 2. 填写 QQ 设置' },
        description: {
          en: 'Enable QQ, keep the built-in direct gateway path, and save the credentials.',
          zh: '启用 QQ，保持内置直连网关路径，然后保存凭据。',
        },
        fieldKeys: ['transport', 'bot_name', 'app_id', 'app_secret'],
        includeEnabledToggle: true,
      },
      {
        id: 'bind',
        title: { en: 'Step 3. Send the first private QQ message', zh: 'Step 3. 发送第一条 QQ 私聊消息' },
        description: {
          en: 'Send one private message from your QQ account to the bot so DeepScientist can detect the OpenID.',
          zh: '从你的 QQ 账号给机器人发送一条私聊消息，让 DeepScientist 自动检测 OpenID。',
        },
        image: {
          assetPath: 'images/qq/tencent-cloud-qq-chat.png',
          alt: { en: 'QQ private chat with the bot', zh: 'QQ 私聊机器人示意' },
          caption: {
            en: 'Use a private chat first. It is the shortest path to learning the correct OpenID.',
            zh: '第一次建议先走私聊，这是学到正确 OpenID 的最短路径。',
          },
        },
      },
    ],
  },
  lingzhu: {
    summary: {
      en: 'Fill the OpenClaw companion endpoint, generate the public values, then probe locally before binding a real Lingzhu device.',
      zh: '先填写 OpenClaw companion 端点，生成公网配置值，再在绑定真实灵珠设备前完成本地探测。',
    },
    requiredFieldKeys: ['public_base_url', 'auth_ak', 'agent_id'],
    overviewChecks: [
      {
        en: 'Lingzhu needs a real public IP or domain before a device can connect.',
        zh: '绑定真实灵珠设备前，必须先有可访问的公网 IP 或域名。',
      },
      {
        en: 'The three key values are public base URL, auth AK, and agent id.',
        zh: '三个关键值是公网地址、auth AK 和 agent id。',
      },
      {
        en: 'The probe is still local-first; it does not prove your public exposure is already correct.',
        zh: '探测仍然是本地优先的；它不能替代公网暴露是否正确的最终验证。',
      },
    ],
    links: [
      {
        kind: 'external',
        label: { en: 'Rokid Developer Forum', zh: 'Rokid 开发者论坛' },
        href: 'https://forum.rokid.com/post/detail/2831',
      },
      {
        kind: 'internal',
        label: { en: 'DeepScientist Settings Reference', zh: 'DeepScientist 设置参考' },
        docSlug: '01_SETTINGS_REFERENCE',
      },
    ],
    steps: [
      {
        id: 'endpoint',
        title: { en: 'Step 1. Point to the OpenClaw gateway', zh: 'Step 1. 指向 OpenClaw 网关' },
        description: {
          en: 'Keep the fixed transport, fill the gateway host and port, and provide the public base URL the glasses can really reach.',
          zh: '保持固定 transport，填写网关主机和端口，并提供眼镜端真正可访问的公网地址。',
        },
        image: {
          assetPath: 'images/lingzhu/lingzhu-settings-overview.svg',
          alt: { en: 'Lingzhu settings overview', zh: 'Lingzhu 设置总览示意' },
        },
      },
      {
        id: 'platform',
        title: { en: 'Step 2. Generate platform values', zh: 'Step 2. 生成平台填写值' },
        description: {
          en: 'Generate the AK and copy the generated public SSE endpoint back into the Lingzhu platform.',
          zh: '生成 AK，并把自动生成的公网 SSE 地址回填到灵珠平台。',
        },
        image: {
          assetPath: 'images/lingzhu/lingzhu-platform-values.svg',
          alt: { en: 'Lingzhu platform values', zh: 'Lingzhu 平台填写值示意' },
        },
      },
      {
        id: 'probe',
        title: { en: 'Step 3. Probe before binding a device', zh: 'Step 3. 绑定设备前先探测' },
        description: {
          en: 'Run the local probe only after the endpoint and AK are saved.',
          zh: '只有在端点和 AK 都已保存后，才执行本地探测。',
        },
        image: {
          assetPath: 'images/lingzhu/lingzhu-openclaw-config.svg',
          alt: { en: 'Lingzhu OpenClaw config preview', zh: 'Lingzhu OpenClaw 配置预览' },
        },
      },
    ],
  },
}
