// @vitest-environment jsdom

import * as React from 'react'
import '@testing-library/jest-dom/vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import LabQuestGraphCanvas from '@/lib/plugins/lab/components/LabQuestGraphCanvas'

const reactFlowMocks = vi.hoisted(() => ({
  setCenter: vi.fn(),
  fitView: vi.fn(),
  getNodes: vi.fn(() => []),
  getInternalNode: vi.fn(() => undefined),
}))

vi.mock('@/lib/api/lab', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api/lab')>('@/lib/api/lab')
  return {
    ...actual,
    listLabAgents: vi.fn().mockResolvedValue({ items: [] }),
    listLabMemory: vi.fn().mockResolvedValue({ items: [] }),
    listLabPapers: vi.fn().mockResolvedValue({ items: [] }),
    updateLabQuestLayout: vi.fn().mockResolvedValue({ layout_json: {}, updated_at: '2026-03-21T00:00:00Z' }),
  }
})

vi.mock('@xyflow/react', async () => {
  const ReactRuntime = await vi.importActual<typeof React>('react')
  return {
    MarkerType: { ArrowClosed: 'arrowclosed' },
    Position: { Left: 'left', Right: 'right' },
    Handle: () => null,
    ReactFlow: ({
      children,
      nodes,
      nodeTypes,
    }: {
      children?: React.ReactNode
      nodes?: Array<{ id: string; type?: string; data?: unknown }>
      nodeTypes?: Record<string, React.ComponentType<any>>
    }) => (
      <div data-testid="reactflow">
        {(nodes ?? []).map((node) => {
          const NodeComponent = node.type ? nodeTypes?.[node.type] : null
          return NodeComponent ? <NodeComponent key={node.id} data={node.data} /> : null
        })}
        {children}
      </div>
    ),
    ReactFlowProvider: ({ children }: { children?: React.ReactNode }) => (
      <div data-testid="reactflow-provider">{children}</div>
    ),
    Background: () => null,
    Controls: () => null,
    MiniMap: () => null,
    useNodesInitialized: () => true,
    useReactFlow: () => ({
      setCenter: reactFlowMocks.setCenter,
      fitView: reactFlowMocks.fitView,
      getNodes: reactFlowMocks.getNodes,
      getInternalNode: reactFlowMocks.getInternalNode,
    }),
    useNodesState: (initial: unknown) => {
      const [nodes, setNodes] = ReactRuntime.useState(initial)
      return [nodes, setNodes, vi.fn()]
    },
    useEdgesState: (initial: unknown) => {
      const [edges, setEdges] = ReactRuntime.useState(initial)
      return [edges, setEdges, vi.fn()]
    },
  }
})

vi.mock('@xyflow/react/dist/style.css', () => ({}))
vi.mock('@/lib/plugins/lab/lab.css', () => ({}))
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  }
})

describe('LabQuestGraphCanvas', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
    vi.useRealTimers()
  })

  it('does not loop state updates when queries are disabled (empty projectId/questId)', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <LabQuestGraphCanvas projectId="" questId="" />
      </QueryClientProvider>
    )

    expect(screen.getByTestId('reactflow')).toBeInTheDocument()
    expect(screen.getByLabelText('Show Branches')).toBeInTheDocument()
    expect(screen.getByLabelText('Show Recent events')).toBeInTheDocument()
    expect(screen.getByLabelText('Show Papers')).toBeInTheDocument()
    expect(screen.queryByText('No graph nodes yet.')).toBeNull()
  })

  it('does not loop state updates when graph queries resolve with data', async () => {
    const fetchGraph = vi.fn().mockResolvedValue({
      view: 'branch',
      nodes: [
        {
          node_id: 'branch-1',
          branch_name: 'main',
          created_at: '2025-01-01T00:00:00Z',
        },
      ],
      edges: [],
      head_branch: 'main',
      layout_json: {},
    })
    const fetchEvents = vi.fn().mockResolvedValue({ items: [], next_cursor: null })

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <LabQuestGraphCanvas
          projectId="project-1"
          questId="quest-1"
          fetchGraph={fetchGraph}
          fetchEvents={fetchEvents}
        />
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(fetchGraph).toHaveBeenCalled()
    })

    expect(screen.getByTestId('reactflow')).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Show Branches'))
    expect(screen.getByText(/Current view/i)).toBeInTheDocument()
  })

  it('skips hidden panel queries when floating panels are disabled', async () => {
    const labApi = await import('@/lib/api/lab')
    vi.mocked(labApi.listLabAgents).mockClear()
    vi.mocked(labApi.listLabMemory).mockClear()
    vi.mocked(labApi.listLabPapers).mockClear()

    const fetchGraph = vi.fn().mockResolvedValue({
      view: 'branch',
      nodes: [
        {
          node_id: 'branch-1',
          branch_name: 'main',
          created_at: '2025-01-01T00:00:00Z',
        },
      ],
      edges: [],
      head_branch: 'main',
      layout_json: {},
    })
    const fetchEvents = vi.fn().mockResolvedValue({ items: [], next_cursor: null })

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <LabQuestGraphCanvas
          projectId="project-1"
          questId="quest-1"
          preferredViewMode="branch"
          showFloatingPanels={false}
          fetchGraph={fetchGraph}
          fetchEvents={fetchEvents}
        />
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(fetchGraph).toHaveBeenCalledTimes(1)
    })

    expect(fetchEvents).not.toHaveBeenCalled()
    expect(labApi.listLabAgents).not.toHaveBeenCalled()
    expect(labApi.listLabMemory).not.toHaveBeenCalled()
    expect(labApi.listLabPapers).not.toHaveBeenCalled()
  })

  it('renders replay-aware memory hints on branch nodes', async () => {
    const labApi = await import('@/lib/api/lab')
    vi.mocked(labApi.listLabMemory).mockResolvedValue({
      items: [
        {
          entry_id: 'MEM-1',
          kind: 'knowledge',
          branch_name: 'main',
          title: 'Warmup lesson',
          summary: 'Longer warmup stabilizes the branch.',
          updated_at: '2026-02-07T00:00:00Z',
        },
      ],
    })

    const fetchGraph = vi.fn().mockResolvedValue({
      view: 'branch',
      nodes: [
        {
          node_id: 'branch-1',
          branch_name: 'main',
          created_at: '2025-01-01T00:00:00Z',
          metrics_json: {
            primary: {
              label: 'Accuracy',
              delta: '+1.2%',
            },
          },
        },
      ],
      edges: [],
      head_branch: 'main',
      layout_json: {},
    })
    const fetchEvents = vi.fn().mockResolvedValue({ items: [], next_cursor: null })

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <LabQuestGraphCanvas
          projectId="project-1"
          questId="quest-1"
          atEventId="evt-1"
          fetchGraph={fetchGraph}
          fetchEvents={fetchEvents}
        />
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(labApi.listLabMemory).toHaveBeenCalledWith(
        'project-1',
        expect.objectContaining({ questId: 'quest-1', atEventId: 'evt-1' })
      )
    })

    expect(await screen.findByText('1 memory note')).toBeInTheDocument()
    expect(screen.getByText('Longer warmup stabilizes the branch.')).toBeInTheDocument()
  })

  it('switches branch nodes into metric mode and keeps baseline metrics visible', async () => {
    const fetchGraph = vi.fn().mockResolvedValue({
      view: 'branch',
      nodes: [
        {
          node_id: 'baseline-root',
          branch_name: 'baseline',
          node_kind: 'baseline_root',
          target_label: 'Accepted Baseline',
          status: 'confirmed',
          created_at: '2025-01-01T00:00:00Z',
          metrics_json: { acc: 0.8 },
          node_summary: {
            last_reply: 'Baseline locked.',
            latest_metrics: { acc: 0.8 },
          },
        },
        {
          node_id: 'branch-1',
          branch_name: 'main',
          branch_no: '001',
          idea_title: 'Branch Alpha',
          created_at: '2025-01-02T00:00:00Z',
          metrics_json: { acc: 0.86 },
          node_summary: {
            last_reply: 'Main branch beats baseline.',
            metrics_delta: { acc: 0.06 },
          },
        },
      ],
      edges: [],
      head_branch: 'main',
      layout_json: {},
      metric_catalog: [{ key: 'acc', label: 'Accuracy', direction: 'higher', importance: 1 }],
    })
    const fetchEvents = vi.fn().mockResolvedValue({ items: [], next_cursor: null })

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <LabQuestGraphCanvas
          projectId="project-1"
          questId="quest-1"
          fetchGraph={fetchGraph}
          fetchEvents={fetchEvents}
        />
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(fetchGraph).toHaveBeenCalled()
    })

    fireEvent.click(screen.getByRole('button', { name: 'Metric' }))

    expect(screen.getByText('0.8000')).toBeInTheDocument()
    expect(screen.getByText('0.8600')).toBeInTheDocument()
    expect(screen.getByText('Baseline reference')).toBeInTheDocument()
    expect(screen.getAllByText('Δ +0.0600 vs baseline').length).toBeGreaterThan(0)
  })

  it('renders science evidence graph cards in stage view', async () => {
    const fetchGraph = vi.fn().mockResolvedValue({
      view: 'stage',
      nodes: [
        {
          node_id: 'stage:main:science',
          branch_name: 'main',
          status: 'success',
          stage_key: 'science',
          stage_title: 'Science',
          artifact_kind: 'science.computational_run',
          node_kind: 'branch',
          idea_json: {
            kind: 'science.computational_run',
            node_id: 'run_water_hf_sto3g',
            title: 'Water HF/STO-3G energy',
            status: 'success',
            package_id: 'pyscf',
            task_type: 'scf_energy',
            key_results: [{ label: 'Total energy', value: -74.96, unit: 'Hartree' }],
            input_paths: ['simulations/inputs/water.py'],
            log_paths: ['simulations/logs/water.out'],
            output_paths: ['simulations/outputs/water/energy.json'],
          },
          event_count: 1,
          created_at: '2025-01-02T00:00:00Z',
        },
      ],
      edges: [],
      head_branch: 'main',
      layout_json: {},
    })
    const fetchEvents = vi.fn().mockResolvedValue({ items: [], next_cursor: null })
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <LabQuestGraphCanvas
          projectId="project-1"
          questId="quest-1"
          preferredViewMode="stage"
          fetchGraph={fetchGraph}
          fetchEvents={fetchEvents}
        />
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(fetchGraph).toHaveBeenCalled()
    })

    expect(await screen.findByText('Computational Run')).toBeInTheDocument()
    expect(screen.getByText('Water HF/STO-3G energy')).toBeInTheDocument()
    expect(screen.getByText(/Total energy/)).toBeInTheDocument()
    expect(screen.getByText(/Evidence:/)).toBeInTheDocument()
  })

  it('focuses and opens science nodes from science focus effects', async () => {
    const fetchGraph = vi.fn().mockResolvedValue({
      view: 'stage',
      nodes: [
        {
          node_id: 'stage:main:science',
          branch_name: 'main',
          status: 'success',
          stage_key: 'science',
          stage_title: 'Science',
          artifact_kind: 'science.computational_run',
          node_kind: 'branch',
          idea_json: {
            kind: 'science.computational_run',
            artifact_id: 'run-water-record',
            node_id: 'run_water_hf_sto3g',
            title: 'Water HF/STO-3G energy',
            summary: 'Computed water molecule total energy.',
            status: 'success',
            package_id: 'pyscf',
            output_paths: ['simulations/outputs/water/energy.json'],
          },
          event_count: 1,
          created_at: '2025-01-02T00:00:00Z',
        },
      ],
      edges: [],
      head_branch: 'main',
      layout_json: {},
    })
    const fetchEvents = vi.fn().mockResolvedValue({ items: [], next_cursor: null })
    const onSelectionChange = vi.fn()
    const onStageOpen = vi.fn()
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <LabQuestGraphCanvas
          projectId="project-1"
          questId="quest-1"
          preferredViewMode="stage"
          fetchGraph={fetchGraph}
          fetchEvents={fetchEvents}
          onSelectionChange={onSelectionChange}
          onStageOpen={onStageOpen}
        />
      </QueryClientProvider>
    )

    expect(await screen.findByText('Water HF/STO-3G energy')).toBeInTheDocument()

    window.dispatchEvent(
      new CustomEvent('ds:science:focus', {
        detail: {
          node_id: 'run_water_hf_sto3g',
          focus: true,
          open_detail: true,
        },
      })
    )

    await waitFor(() => {
      expect(onSelectionChange).toHaveBeenCalledWith(
        expect.objectContaining({
          selection_type: 'stage_node',
          selection_ref: 'stage:main:science',
          stage_key: 'science',
          label: 'Water HF/STO-3G energy',
        })
      )
      expect(onStageOpen).toHaveBeenCalledWith(
        expect.objectContaining({
          selection_ref: 'stage:main:science',
        })
      )
      expect(reactFlowMocks.setCenter).toHaveBeenCalled()
    })
  })

  it('keeps branch list clicks as selection-only without opening the stage page', async () => {
    const fetchGraph = vi.fn().mockResolvedValue({
      view: 'branch',
      nodes: [
        {
          node_id: 'branch-1',
          branch_name: 'main',
          branch_no: '001',
          idea_title: 'Branch Alpha',
          next_target: 'Run ablation',
          created_at: '2025-01-01T00:00:00Z',
        },
      ],
      edges: [],
      head_branch: 'main',
      layout_json: {},
    })
    const fetchEvents = vi.fn().mockResolvedValue({ items: [], next_cursor: null })
    const onBranchSelect = vi.fn()
    const onStageOpen = vi.fn()
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <LabQuestGraphCanvas
          projectId="project-1"
          questId="quest-1"
          fetchGraph={fetchGraph}
          fetchEvents={fetchEvents}
          onBranchSelect={onBranchSelect}
          onStageOpen={onStageOpen}
        />
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(fetchGraph).toHaveBeenCalled()
    })

    fireEvent.click(screen.getByLabelText('Show Branches'))

    const branchButton = await waitFor(() => {
      const button = container.querySelector('.lab-quest-branch-item') as HTMLButtonElement | null
      expect(button).not.toBeNull()
      return button as HTMLButtonElement
    })
    expect(branchButton).not.toBeNull()
    fireEvent.click(branchButton)

    expect(onBranchSelect).toHaveBeenCalledWith('main')
    expect(onStageOpen).not.toHaveBeenCalled()
  })

  it('restores current-path filtering from persisted layout and saves filter changes', async () => {
    const labApi = await import('@/lib/api/lab')
    vi.mocked(labApi.updateLabQuestLayout).mockClear()
    const fetchGraph = vi.fn().mockResolvedValue({
      view: 'branch',
      nodes: [
        {
          node_id: 'baseline-root',
          branch_name: 'baseline',
          node_kind: 'baseline_root',
          target_label: 'Baseline',
          created_at: '2025-01-01T00:00:00Z',
        },
        {
          node_id: 'main',
          branch_name: 'main',
          idea_title: 'Main Route',
          created_at: '2025-01-01T00:00:00Z',
        },
        {
          node_id: 'run/current',
          branch_name: 'run/current',
          parent_branch: 'main',
          idea_title: 'Current Route',
          created_at: '2025-01-02T00:00:00Z',
          workflow_state: {
            analysis_state: 'active',
            writing_state: 'blocked_by_analysis',
            status_reason: 'Analysis 1/2 done · next: slice-b',
          },
        },
        {
          node_id: 'run/other',
          branch_name: 'run/other',
          parent_branch: 'main',
          idea_title: 'Sibling Route',
          created_at: '2025-01-03T00:00:00Z',
          workflow_state: {
            analysis_state: 'none',
            writing_state: 'ready',
            status_reason: 'Main experiment recorded. Ready for writing.',
          },
        },
      ],
      edges: [
        { source: 'main', target: 'run/current' },
        { source: 'main', target: 'run/other' },
      ],
      head_branch: 'run/current',
      layout_json: {
        preferences: {
          pathFilterMode: 'current',
          showAnalysis: true,
        },
      },
    })
    const fetchEvents = vi.fn().mockResolvedValue({ items: [], next_cursor: null })
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    const { container } = render(
      <QueryClientProvider client={queryClient}>
        <LabQuestGraphCanvas
          projectId="project-1"
          questId="quest-1"
          fetchGraph={fetchGraph}
          fetchEvents={fetchEvents}
        />
      </QueryClientProvider>
    )

    await waitFor(() => {
      expect(fetchGraph).toHaveBeenCalled()
    })

    fireEvent.click(screen.getByLabelText('Show Branches'))
    const branchTitles = () =>
      Array.from(container.querySelectorAll('.lab-quest-branch-item__title')).map((element) => element.textContent)
    expect(branchTitles()).toContain('Current Route')
    expect(branchTitles()).not.toContain('Sibling Route')

    fireEvent.click(screen.getByRole('button', { name: 'All' }))

    await waitFor(() => {
      expect(branchTitles()).toContain('Sibling Route')
    })

    await waitFor(() => {
      expect(labApi.updateLabQuestLayout).toHaveBeenCalledWith(
        'project-1',
        'quest-1',
        expect.objectContaining({
          preferences: expect.objectContaining({
            pathFilterMode: 'all',
          }),
        })
      )
    }, { timeout: 3000 })
  })
})
