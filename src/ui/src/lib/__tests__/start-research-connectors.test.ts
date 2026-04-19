import { describe, expect, it } from 'vitest'

import {
  compileStartResearchPrompt,
  defaultStartResearchTemplate,
  resolveStartResearchConnectorBindings,
  saveStartResearchTemplate,
  shouldRecommendStartResearchConnectorBinding,
} from '../startResearch'

describe('shouldRecommendStartResearchConnectorBinding', () => {
  it('does not recommend before the first connector fetch completes', () => {
    expect(
      shouldRecommendStartResearchConnectorBinding({
        open: true,
        availabilityResolved: false,
        availabilityLoading: false,
        availabilityError: null,
        connectorRecommendationHandled: false,
        availability: null,
      })
    ).toBe(false)
  })

  it('does not recommend when an enabled connector already has a delivery target', () => {
    expect(
      shouldRecommendStartResearchConnectorBinding({
        open: true,
        availabilityResolved: true,
        availabilityLoading: false,
        availabilityError: null,
        connectorRecommendationHandled: false,
        availability: {
          has_enabled_external_connector: true,
          has_bound_external_connector: true,
          should_recommend_binding: false,
          preferred_connector_name: 'qq',
          preferred_conversation_id: 'qq:direct:user-1',
          available_connectors: [
            {
              name: 'qq',
              enabled: true,
              connection_state: 'connected',
              binding_count: 1,
              target_count: 1,
              has_delivery_target: true,
            },
          ],
        },
      })
    ).toBe(false)
  })

  it('recommends only after the connector fetch completes and no enabled connector exists', () => {
    expect(
      shouldRecommendStartResearchConnectorBinding({
        open: true,
        availabilityResolved: true,
        availabilityLoading: false,
        availabilityError: null,
        connectorRecommendationHandled: false,
        availability: {
          has_enabled_external_connector: false,
          has_bound_external_connector: false,
          should_recommend_binding: true,
          preferred_connector_name: null,
          preferred_conversation_id: null,
          available_connectors: [],
        },
      })
    ).toBe(true)
  })
})

describe('resolveStartResearchConnectorBindings', () => {
  it('defaults to the first available connector target only', () => {
    expect(
      resolveStartResearchConnectorBindings([
        {
          name: 'qq',
          targets: [
            { conversationId: 'qq:direct:qq-a::user-a' },
            { conversationId: 'qq:direct:qq-b::user-b' },
          ],
        },
        {
          name: 'telegram',
          targets: [{ conversationId: 'telegram:direct:tg-1' }],
        },
      ])
    ).toEqual({
      qq: 'qq:direct:qq-a::user-a',
      telegram: null,
    })
  })

  it('preserves one valid existing selection and clears the rest', () => {
    expect(
      resolveStartResearchConnectorBindings(
        [
          {
            name: 'qq',
            targets: [
              { conversationId: 'qq:direct:qq-a::user-a' },
              { conversationId: 'qq:direct:qq-b::user-b' },
            ],
          },
          {
            name: 'telegram',
            targets: [{ conversationId: 'telegram:direct:tg-2' }],
          },
        ],
        {
          qq: 'qq:direct:qq-b::user-b',
          telegram: 'telegram:direct:tg-2',
        }
      )
    ).toEqual({
      qq: 'qq:direct:qq-b::user-b',
      telegram: null,
    })
  })

  it('falls back to the next available connector when the current one becomes invalid', () => {
    expect(
      resolveStartResearchConnectorBindings(
        [
          {
            name: 'qq',
            targets: [],
          },
          {
            name: 'telegram',
            targets: [{ conversationId: 'telegram:direct:tg-2' }],
          },
        ],
        {
          qq: 'qq:direct:qq-b::user-b',
        }
      )
    ).toEqual({
      qq: null,
      telegram: 'telegram:direct:tg-2',
    })
  })

  it('preserves an explicit local-only choice', () => {
    expect(
      resolveStartResearchConnectorBindings(
        [
          {
            name: 'qq',
            targets: [{ conversationId: 'qq:direct:qq-a::user-a' }],
          },
          {
            name: 'telegram',
            targets: [{ conversationId: 'telegram:direct:tg-2' }],
          },
        ],
        {
          qq: null,
          telegram: null,
        }
      )
    ).toEqual({
      qq: null,
      telegram: null,
    })
  })
})

describe('start research standard profiles', () => {
  it('defaults standard mode to the canonical research graph', () => {
    expect(defaultStartResearchTemplate('en').standard_profile).toBe('canonical_research_graph')
  })

  it('persists and recompiles the optimization task profile', () => {
    const saved = saveStartResearchTemplate({
      ...defaultStartResearchTemplate('en'),
      launch_mode: 'standard',
      standard_profile: 'optimization_task',
      need_research_paper: false,
      goal: 'Optimize the system rather than writing a paper.',
    })

    expect(saved.standard_profile).toBe('optimization_task')
    expect(saved.compiled_prompt).toContain('Optimization task:')
    expect(saved.compiled_prompt).toContain('Do not schedule analysis-campaign work by default')
  })

  it('describes the optimization task as non-paper in the compiled prompt', () => {
    const prompt = compileStartResearchPrompt({
      ...defaultStartResearchTemplate('en'),
      launch_mode: 'standard',
      standard_profile: 'optimization_task',
      need_research_paper: false,
      goal: 'Search for the strongest result only.',
    })

    expect(prompt).toContain('Standard profile: optimization task.')
    expect(prompt).toContain('do not plan around paper writing')
    expect(prompt).toContain('do not drift into paper writing or default analysis-campaign work')
  })

  it('can compile a local-existing baseline route with plan-first execution', () => {
    const prompt = compileStartResearchPrompt({
      ...defaultStartResearchTemplate('en'),
      goal: 'Use the already running local system as the baseline comparator first.',
      baseline_source_mode: 'verify_local_existing',
      execution_start_mode: 'plan_then_execute',
      baseline_acceptance_target: 'comparison_ready',
    })

    expect(prompt).toContain('Baseline Source Preference')
    expect(prompt).toContain('Verify local existing')
    expect(prompt).toContain('Execution Start Mode')
    expect(prompt).toContain('Plan first')
    expect(prompt).toContain('Baseline Acceptance Target')
    expect(prompt).toContain('Comparison ready')
  })
})
