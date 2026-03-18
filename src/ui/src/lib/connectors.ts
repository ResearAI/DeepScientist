import type { ConnectorBindingSnapshot, ConnectorRecentConversation, ConnectorSnapshot, ConnectorTargetSnapshot } from '@/types'

const CONNECTOR_PROFILE_CHAT_ID_SEPARATOR = '::'

function defaultConversationLabel(chatType?: string | null, chatId?: string | null) {
  return `${String(chatType || '').trim()} · ${String(chatId || '').trim()}`.trim()
}

function stripRepeatedProfilePrefix(profileLabel?: string | null, label?: string | null) {
  const normalizedProfileLabel = String(profileLabel || '').trim()
  let normalizedLabel = String(label || '').trim()
  if (!normalizedProfileLabel || !normalizedLabel) {
    return normalizedLabel
  }
  const prefixed = `${normalizedProfileLabel} · `
  while (normalizedLabel === normalizedProfileLabel || normalizedLabel.startsWith(prefixed)) {
    if (normalizedLabel === normalizedProfileLabel) {
      return normalizedProfileLabel
    }
    normalizedLabel = normalizedLabel.slice(prefixed.length).trim()
  }
  return normalizedLabel
}

function baseTargetLabel(target?: Pick<ConnectorTargetSnapshot, 'label' | 'chat_type' | 'chat_id' | 'conversation_id' | 'profile_label'> | null) {
  if (!target) return ''
  const fallback =
    defaultConversationLabel(target.chat_type, target.chat_id) || String(target.conversation_id || '').trim()
  return stripRepeatedProfilePrefix(target.profile_label, target.label) || fallback
}

function baseRecentConversationLabel(
  item?: Pick<ConnectorRecentConversation, 'label' | 'chat_type' | 'chat_id' | 'profile_label'> | null
) {
  if (!item) return ''
  return stripRepeatedProfilePrefix(item.profile_label, item.label) || defaultConversationLabel(item.chat_type, item.chat_id)
}

function withProfileLabel(profileLabel?: string | null, label?: string | null) {
  const normalizedProfileLabel = String(profileLabel || '').trim()
  const normalizedLabel = stripRepeatedProfilePrefix(profileLabel, label)
  if (!normalizedProfileLabel) return normalizedLabel
  if (!normalizedLabel) return normalizedProfileLabel
  if (normalizedLabel === normalizedProfileLabel) return normalizedProfileLabel
  return `${normalizedProfileLabel} · ${normalizedLabel}`
}

export function parseConversationId(value?: string | null) {
  const raw = String(value || '').trim()
  const parts = raw.split(':', 3)
  if (parts.length !== 3) return null
  const [connector, chatType, chatId] = parts
  if (!connector || !chatType || !chatId) return null
  const separatorIndex = chatId.indexOf(CONNECTOR_PROFILE_CHAT_ID_SEPARATOR)
  const profileId = separatorIndex >= 0 ? chatId.slice(0, separatorIndex).trim() : ''
  const resolvedChatId = separatorIndex >= 0 ? chatId.slice(separatorIndex + CONNECTOR_PROFILE_CHAT_ID_SEPARATOR.length).trim() : chatId
  return {
    conversation_id: raw,
    connector: connector.toLowerCase(),
    chat_type: chatType.toLowerCase(),
    chat_id: resolvedChatId,
    chat_id_raw: chatId,
    profile_id: profileId,
  }
}

export function conversationIdentityKey(value?: string | null) {
  const parsed = parseConversationId(value)
  if (!parsed) return String(value || '').trim().toLowerCase()
  return [parsed.connector, parsed.profile_id || '', parsed.chat_type, parsed.chat_id.toLowerCase()].filter(Boolean).join(':')
}

export function connectorTargetLabel(target?: ConnectorTargetSnapshot | null) {
  if (!target) return ''
  return withProfileLabel(target.profile_label, baseTargetLabel(target))
}

export function recentConversationLabel(item?: ConnectorRecentConversation | null) {
  if (!item) return ''
  return withProfileLabel(item.profile_label, baseRecentConversationLabel(item))
}

function sortTargets(left: ConnectorTargetSnapshot, right: ConnectorTargetSnapshot) {
  const leftDefault = left.is_default ? 0 : 1
  const rightDefault = right.is_default ? 0 : 1
  if (leftDefault !== rightDefault) return leftDefault - rightDefault
  const leftDirect = String(left.chat_type || '') === 'direct' ? 0 : 1
  const rightDirect = String(right.chat_type || '') === 'direct' ? 0 : 1
  if (leftDirect !== rightDirect) return leftDirect - rightDirect
  const updatedCompare = String(right.updated_at || '').localeCompare(String(left.updated_at || ''))
  if (updatedCompare !== 0) return updatedCompare
  return String(left.conversation_id || '').localeCompare(String(right.conversation_id || ''))
}

function mergeTargetEntry(
  merged: Map<string, ConnectorTargetSnapshot>,
  target: ConnectorTargetSnapshot | null | undefined,
  options: {
    defaultConversationId: string | null
  }
) {
  if (!target?.conversation_id) return
  const { defaultConversationId } = options
  const normalizedTarget: ConnectorTargetSnapshot = {
    ...target,
    label: baseTargetLabel(target),
    selectable: target.selectable ?? true,
    is_default: target.is_default || conversationIdentityKey(target.conversation_id) === conversationIdentityKey(defaultConversationId),
  }
  const key = conversationIdentityKey(normalizedTarget.conversation_id)
  const existing = merged.get(key)
  if (!existing) {
    merged.set(key, normalizedTarget)
    return
  }
  const nextSources = Array.from(
    new Set([...(existing.sources || []), ...(normalizedTarget.sources || []), existing.source, normalizedTarget.source].filter(Boolean))
  )
  merged.set(key, {
    ...existing,
    ...normalizedTarget,
    label:
      baseTargetLabel(existing) === defaultConversationLabel(existing.chat_type, existing.chat_id) && baseTargetLabel(normalizedTarget)
        ? baseTargetLabel(normalizedTarget)
        : baseTargetLabel(existing) || baseTargetLabel(normalizedTarget),
    sources: nextSources.length ? nextSources : undefined,
    is_default: Boolean(existing.is_default || normalizedTarget.is_default),
    selectable: existing.selectable ?? normalizedTarget.selectable ?? true,
    bound_quest_id: normalizedTarget.bound_quest_id || existing.bound_quest_id || null,
    bound_quest_title: normalizedTarget.bound_quest_title || existing.bound_quest_title || null,
    warning: normalizedTarget.warning || existing.warning || null,
    updated_at:
      String(normalizedTarget.updated_at || '') >= String(existing.updated_at || '')
        ? normalizedTarget.updated_at || existing.updated_at
        : existing.updated_at || normalizedTarget.updated_at,
  })
}

function targetFromConversationId(
  conversationId: string | null | undefined,
  patch: Partial<ConnectorTargetSnapshot> = {}
): ConnectorTargetSnapshot | null {
  const parsed = parseConversationId(conversationId)
  if (!parsed) return null
  return {
    ...parsed,
    ...patch,
    conversation_id: parsed.conversation_id,
    connector: parsed.connector,
    chat_type: parsed.chat_type,
    chat_id: parsed.chat_id,
    chat_id_raw: parsed.chat_id_raw,
    profile_id: parsed.profile_id || null,
    label: patch.label || `${parsed.chat_type} · ${parsed.chat_id}`,
  }
}

function normalizeBindingTarget(binding: ConnectorBindingSnapshot): ConnectorTargetSnapshot | null {
  return targetFromConversationId(binding.conversation_id, {
    source: 'quest_binding',
    sources: ['quest_binding'],
    profile_id: binding.profile_id || null,
    profile_label: binding.profile_label || null,
    bound_quest_id: binding.quest_id || null,
    bound_quest_title: binding.quest_title || null,
    is_bound: Boolean(binding.quest_id),
    warning: binding.quest_id ? `Currently bound to ${binding.quest_id}` : null,
    updated_at: binding.updated_at || null,
  })
}

function normalizeRecentConversationTarget(item: ConnectorRecentConversation): ConnectorTargetSnapshot | null {
  return targetFromConversationId(item.conversation_id, {
    source: item.source || 'recent_activity',
    sources: [String(item.source || 'recent_activity')],
    profile_id: item.profile_id || null,
    profile_label: item.profile_label || null,
    label: baseRecentConversationLabel(item),
    updated_at: item.updated_at || null,
    bound_quest_id: item.quest_id || null,
    is_bound: Boolean(item.quest_id),
  })
}

function normalizeKnownTarget(target: ConnectorTargetSnapshot): ConnectorTargetSnapshot {
  const source = String(target.source || '').trim() || 'known_target'
  const sources = Array.from(new Set([...(target.sources || []), source].map((item) => String(item || '').trim()).filter(Boolean)))
  return {
    ...target,
    source,
    sources,
  }
}

export function normalizeConnectorTargets(snapshot: ConnectorSnapshot): ConnectorTargetSnapshot[] {
  const merged = new Map<string, ConnectorTargetSnapshot>()
  const defaultConversationId =
    String(snapshot.default_target?.conversation_id || '').trim() ||
    (snapshot.name === 'qq' && String(snapshot.main_chat_id || '').trim() ? `qq:direct:${String(snapshot.main_chat_id || '').trim()}` : '') ||
    ''

  for (const target of snapshot.known_targets || []) {
    mergeTargetEntry(merged, normalizeKnownTarget(target), { defaultConversationId })
  }
  for (const target of snapshot.discovered_targets || []) {
    mergeTargetEntry(merged, target, { defaultConversationId })
  }
  mergeTargetEntry(merged, snapshot.default_target || null, { defaultConversationId })
  for (const binding of snapshot.bindings || []) {
    mergeTargetEntry(merged, normalizeBindingTarget(binding), { defaultConversationId })
  }
  for (const item of snapshot.recent_conversations || []) {
    mergeTargetEntry(merged, normalizeRecentConversationTarget(item), { defaultConversationId })
  }
  if (snapshot.last_conversation_id) {
    mergeTargetEntry(
      merged,
      targetFromConversationId(snapshot.last_conversation_id, {
        source: 'last_conversation',
        sources: ['last_conversation'],
      }),
      { defaultConversationId }
    )
  }
  if (snapshot.name === 'qq' && snapshot.main_chat_id) {
    mergeTargetEntry(
      merged,
      targetFromConversationId(`qq:direct:${snapshot.main_chat_id}`, {
        source: 'saved_main_chat',
        sources: ['saved_main_chat'],
        is_default: true,
      }),
      { defaultConversationId }
    )
  }
  return Array.from(merged.values()).sort(sortTargets)
}
