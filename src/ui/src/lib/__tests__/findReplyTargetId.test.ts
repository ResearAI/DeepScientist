import { describe, expect, it } from 'vitest'

import { findReplyTargetId } from '@/lib/acp'
import type { FeedItem } from '@/types'

type ArtifactItem = Extract<FeedItem, { type: 'artifact' }>

function artifact(overrides: Partial<ArtifactItem>): ArtifactItem {
  return {
    id: 'art-default',
    type: 'artifact',
    kind: 'progress',
    content: '',
    ...overrides,
  }
}

describe('findReplyTargetId', () => {
  it('prefers an unresolved blocking decision over more recent threaded heartbeats', () => {
    // Reproduces quest 014: a blocking quest_completion_approval is followed
    // by several `__noop__` progress heartbeats. Without the two-pass scan the
    // most recent threaded heartbeat would steal the reply target and "同意"
    // would never reach the actual approval request.
    const feed: FeedItem[] = [
      artifact({
        id: 'decision-b5351a4f',
        kind: 'decision',
        interactionId: 'decision-b5351a4f',
        replyMode: 'blocking',
        expectsReply: true,
      }),
      artifact({ id: 'progress-1', interactionId: 'progress-1', replyMode: 'threaded' }),
      artifact({ id: 'progress-2', interactionId: 'progress-2', replyMode: 'threaded' }),
      artifact({ id: 'progress-3', interactionId: 'progress-3', replyMode: 'threaded' }),
    ]
    expect(findReplyTargetId(feed)).toBe('decision-b5351a4f')
  })

  it('falls back to the latest threaded interaction when no blocking one is open', () => {
    const feed: FeedItem[] = [
      artifact({ id: 'progress-old', interactionId: 'progress-old', replyMode: 'threaded' }),
      artifact({ id: 'progress-new', interactionId: 'progress-new', replyMode: 'threaded' }),
    ]
    expect(findReplyTargetId(feed)).toBe('progress-new')
  })

  it('matches expectsReply even without an explicit blocking replyMode', () => {
    const feed: FeedItem[] = [
      artifact({
        id: 'question',
        interactionId: 'question',
        expectsReply: true,
      }),
      artifact({ id: 'progress-after', interactionId: 'progress-after', replyMode: 'threaded' }),
    ]
    expect(findReplyTargetId(feed)).toBe('question')
  })

  it('returns the interaction id when present, otherwise falls back to the item id', () => {
    const feed: FeedItem[] = [
      artifact({ id: 'art-id', interactionId: undefined, replyMode: 'blocking', expectsReply: true }),
    ]
    expect(findReplyTargetId(feed)).toBe('art-id')
  })

  it('returns null when no artifacts are present', () => {
    const feed: FeedItem[] = [
      { id: 'm', type: 'message', role: 'user', content: 'hi' },
    ]
    expect(findReplyTargetId(feed)).toBeNull()
  })
})
