// @vitest-environment jsdom

import '@testing-library/jest-dom/vitest'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { StartSetupAssessmentCard } from '@/components/projects/CreateProjectDialog'

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('@/lib/plugins/markdown-viewer/components/MarkdownRenderer', () => ({
  default: ({ content, className }: { content: string; className?: string }) => (
    <article data-testid="markdown-plan" className={className}>{content}</article>
  ),
}))

describe('StartSetupAssessmentCard', () => {
  it('renders durable markdown launch plans from SetupAgent', () => {
    render(
      <StartSetupAssessmentCard
        locale="zh"
        session={{
          suggestedForm: null,
          fitAssessment: {
            verdict: 'provisional_autonomous',
            reason: '这个任务可以在机器内闭环推进，但需要确认 GPU 范围。',
          },
          recommendedWorkspaceMode: 'provisional_autonomous',
          launchReadiness: 'needs_confirmation',
          missingConfirmations: ['可用 GPU 是几张？'],
          previewPlan: {
            markdown: '## 启动预览计划\n\n### 1. 模式建议\n- 推荐：暂可全自动但需确认',
            phases: [
              {
                title: 'Baseline / 起点可信化',
                goal: '先确认可复现实验入口。',
                deliverable: '可信 baseline 记录',
                switch_condition: '如果数据缺失则回到协作模式。',
              },
            ],
          },
          copilotHandoff: null,
          scienceTask: null,
          scienceTaskBrief: null,
          sciencePackageCards: [],
        }}
      />
    )

    expect(screen.getByText('Recommended mode · 需确认')).toBeInTheDocument()
    expect(screen.getByText('启动规划')).toBeInTheDocument()
    expect(screen.getByTestId('markdown-plan')).toHaveTextContent('## 启动预览计划')
    expect(screen.getByText('Baseline / 起点可信化')).toBeInTheDocument()
  })

  it('renders science task metadata and copilot recommendation from SetupAgent', () => {
    render(
      <StartSetupAssessmentCard
        locale="zh"
        session={{
          suggestedForm: null,
          fitAssessment: {
            verdict: 'copilot',
            reason: '这是一次有边界的科学软件检查，适合协作模式。',
          },
          recommendedWorkspaceMode: 'copilot',
          launchReadiness: 'ready',
          missingConfirmations: [],
          previewPlan: null,
          copilotHandoff: {
            title: 'PySCF 协作检查',
            startup_message: '先检查 PySCF import/version/smoke test。',
            workspace_mode: 'copilot',
            create_and_send: true,
          },
          scienceTask: {
            is_science_task: true,
            domain: 'quantum_chemistry',
            task_family: 'computational_run',
            required_packages: ['pyscf'],
            expected_node_types: ['science.package_check', 'science.computational_run', 'science.validation_result'],
            package_check_required: true,
            solver_installation_unknown: true,
          },
          scienceTaskBrief: {
            brief_type: 'science_task_brief',
            markdown: '## Objective\nCheck PySCF before running.',
            uses_fermilink_goal_structure: true,
            materialize_as_file: false,
          },
          sciencePackageCards: ['science/references/packages/pyscf.md'],
        }}
      />
    )

    expect(screen.getByText('Recommended mode · 协作模式')).toBeInTheDocument()
    expect(screen.getByText('Science Evidence Graph')).toBeInTheDocument()
    expect(screen.getByText('quantum_chemistry · computational_run')).toBeInTheDocument()
    expect(screen.getByText('Packages: pyscf')).toBeInTheDocument()
    expect(screen.getByText(/science\/references\/packages\/pyscf.md/)).toBeInTheDocument()
    expect(screen.getByText(/package check/)).toBeInTheDocument()
    expect(screen.getByText(/solver 未验证/)).toBeInTheDocument()
  })
})
