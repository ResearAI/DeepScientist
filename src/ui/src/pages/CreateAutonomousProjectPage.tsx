import * as React from 'react'
import { useNavigate } from 'react-router-dom'

import { CreateProjectDialog } from '@/components/projects/CreateProjectDialog'
import { client } from '@/lib/api'

export function CreateAutonomousProjectPage() {
  const navigate = useNavigate()
  const [creating, setCreating] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const handleCreate = React.useCallback(
    async (payload: {
      title: string
      goal: string
      quest_id?: string
      requested_connector_bindings?: Array<{ connector: string; conversation_id?: string | null }>
      requested_baseline_ref?: { baseline_id: string; variant_id?: string | null } | null
      startup_contract?: Record<string, unknown> | null
    }) => {
      if (!payload.goal.trim()) return
      setCreating(true)
      setError(null)
      try {
        const result = await client.createQuestWithOptions({
          goal: payload.goal.trim(),
          title: payload.title.trim() || undefined,
          quest_id: payload.quest_id?.trim() || undefined,
          source: 'web-react',
          auto_start: true,
          initial_message: payload.goal.trim(),
          auto_bind_latest_connectors: false,
          requested_connector_bindings: payload.requested_connector_bindings,
          requested_baseline_ref: payload.requested_baseline_ref ?? undefined,
          startup_contract: payload.startup_contract ?? undefined,
        })
        navigate(`/projects/${result.snapshot.quest_id}`)
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : 'Failed to create quest.')
      } finally {
        setCreating(false)
      }
    },
    [navigate]
  )

  return (
    <div
      className="min-h-screen bg-[#F5F2EC] font-project"
      style={{
        backgroundImage:
          'radial-gradient(880px circle at 12% 12%, rgba(181, 194, 204, 0.2), transparent 58%), radial-gradient(740px circle at 88% 0%, rgba(214, 200, 180, 0.22), transparent 52%), linear-gradient(180deg, #F6F1EA 0%, #EFE7DD 100%)',
      }}
    >
      <CreateProjectDialog
        open
        loading={creating}
        error={error}
        onBack={() => navigate('/')}
        onClose={() => navigate('/')}
        onCreate={handleCreate}
      />
    </div>
  )
}

export default CreateAutonomousProjectPage
