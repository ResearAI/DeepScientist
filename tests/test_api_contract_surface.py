from __future__ import annotations

from pathlib import Path

from deepscientist.daemon.api.router import match_route


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_backend_routes_cover_shared_web_and_tui_surface() -> None:
    expected_routes = [
        ("GET", "/api/system/update", "system_update"),
        ("POST", "/api/system/update", "system_update_action"),
        ("POST", "/api/system/shutdown", "system_shutdown"),
        ("GET", "/api/system/doctor", "system_doctor"),
        ("GET", "/api/system/tasks", "system_tasks"),
        ("POST", "/api/system/tasks/doctor", "system_task_doctor_start"),
        ("POST", "/api/system/tasks/system-update-check", "system_task_system_update_check_start"),
        ("POST", "/api/system/tasks/system-update-action", "system_task_system_update_action_start"),
        ("GET", "/api/system/tasks/systemtask-001", "system_task_detail"),
        ("GET", "/api/system/tasks/systemtask-001/stream", "system_task_stream"),
        ("GET", "/api/system/overview", "system_overview"),
        ("GET", "/api/system/quests", "system_quests"),
        ("GET", "/api/system/quests/q-001/summary", "system_quest_summary"),
        ("GET", "/api/system/runtime/sessions", "system_runtime_sessions"),
        ("GET", "/api/system/logs/sources", "system_log_sources"),
        ("GET", "/api/system/logs/tail", "system_log_tail"),
        ("GET", "/api/system/failures", "system_failures"),
        ("GET", "/api/system/errors", "system_errors"),
        ("GET", "/api/system/runtime-tools", "system_runtime_tools"),
        ("GET", "/api/system/hardware", "system_hardware"),
        ("POST", "/api/system/hardware", "system_hardware_update"),
        ("GET", "/api/system/charts/catalog", "system_chart_catalog"),
        ("POST", "/api/system/charts/query", "system_chart_query"),
        ("GET", "/api/system/audit", "system_audit"),
        ("GET", "/api/system/stats/summary", "system_stats_summary"),
        ("GET", "/api/system/search", "system_search"),
        ("POST", "/api/system/issues/draft", "system_issue_draft"),
        ("GET", "/api/system/controllers", "system_controllers"),
        ("POST", "/api/system/controllers/stale_running_quest_guard/run", "system_controller_run"),
        ("POST", "/api/system/controllers/stale_running_quest_guard/toggle", "system_controller_toggle"),
        ("GET", "/api/system/repairs", "system_repairs"),
        ("POST", "/api/system/repairs", "system_repair_create"),
        ("GET", "/api/system/repairs/repair-001", "system_repair_detail"),
        ("POST", "/api/system/repairs/repair-001/close", "system_repair_close"),
        ("GET", "/api/admin/doctor", "admin_doctor"),
        ("POST", "/api/admin/shutdown", "admin_shutdown"),
        ("GET", "/api/admin/tasks", "admin_tasks"),
        ("POST", "/api/admin/tasks/doctor", "admin_task_doctor_start"),
        ("POST", "/api/admin/tasks/system-update-check", "admin_task_system_update_check_start"),
        ("POST", "/api/admin/tasks/system-update-action", "admin_task_system_update_action_start"),
        ("GET", "/api/admin/tasks/admintask-001", "admin_task_detail"),
        ("GET", "/api/admin/tasks/admintask-001/stream", "admin_task_stream"),
        ("GET", "/api/admin/errors", "admin_errors"),
        ("GET", "/api/admin/system/hardware", "admin_system_hardware"),
        ("POST", "/api/admin/system/hardware", "admin_system_hardware_update"),
        ("GET", "/api/admin/charts/catalog", "admin_chart_catalog"),
        ("POST", "/api/admin/charts/query", "admin_chart_query"),
        ("POST", "/api/admin/issues/draft", "admin_issue_draft"),
        ("GET", "/api/admin/controllers", "admin_controllers"),
        ("POST", "/api/admin/controllers/stale_running_quest_guard/run", "admin_controller_run"),
        ("POST", "/api/admin/controllers/stale_running_quest_guard/toggle", "admin_controller_toggle"),
        ("GET", "/api/admin/repairs", "admin_repairs"),
        ("POST", "/api/admin/repairs", "admin_repair_create"),
        ("GET", "/api/admin/repairs/repair-001", "admin_repair_detail"),
        ("POST", "/api/admin/repairs/repair-001/close", "admin_repair_close"),
        ("GET", "/api/baselines", "baselines"),
        ("DELETE", "/api/baselines/demo-baseline", "baseline_delete"),
        ("GET", "/api/benchstore/entries", "benchstore_entries"),
        ("GET", "/api/benchstore/entries/aisb.t3.tdc_admet", "benchstore_entry"),
        ("GET", "/api/benchstore/entries/aisb.t3.tdc_admet/image", "benchstore_entry_image"),
        ("GET", "/api/benchstore/entries/aisb.t3.tdc_admet/setup-packet", "benchstore_entry_setup_packet"),
        ("POST", "/api/benchstore/entries/aisb.t3.tdc_admet/install", "benchstore_entry_install"),
        ("POST", "/api/benchstore/entries/aisb.t3.tdc_admet/launch", "benchstore_entry_launch"),
        ("GET", "/api/quests", "quests"),
        ("GET", "/api/quest-id/next", "quest_next_id"),
        ("POST", "/api/quests", "quest_create"),
        ("GET", "/api/connectors", "connectors"),
        ("GET", "/api/connectors/availability", "connectors_availability"),
        ("POST", "/api/connectors/weixin/login/qr/start", "weixin_login_qr_start"),
        ("POST", "/api/connectors/weixin/login/qr/wait", "weixin_login_qr_wait"),
        ("DELETE", "/api/connectors/qq/profiles/qq-alpha", "connector_profile_delete"),
        ("POST", "/api/quests/q-001/baseline-binding", "quest_baseline_binding"),
        ("DELETE", "/api/quests/q-001/baseline-binding", "quest_baseline_unbind"),
        ("PATCH", "/api/quests/q-001/settings", "quest_settings"),
        ("POST", "/api/quests/q-001/bindings", "quest_bindings"),
        ("PUT", "/api/quests/q-001/bindings", "quest_bindings"),
        ("DELETE", "/api/quests/q-001", "quest_delete"),
        ("GET", "/api/quests/q-001/session", "quest_session"),
        ("GET", "/api/quests/q-001/events", "quest_events"),
        ("GET", "/api/quests/q-001/artifacts", "quest_artifacts"),
        ("GET", "/api/quests/q-001/workflow", "workflow"),
        ("GET", "/api/quests/q-001/bash/sessions", "bash_sessions"),
        ("GET", "/api/quests/q-001/bash/sessions/stream", "bash_sessions_stream"),
        ("GET", "/api/quests/q-001/bash/sessions/bash-001", "bash_session"),
        ("GET", "/api/quests/q-001/bash/sessions/bash-001/logs", "bash_logs"),
        ("GET", "/api/quests/q-001/bash/sessions/bash-001/stream", "bash_log_stream"),
        ("POST", "/api/quests/q-001/bash/sessions/bash-001/stop", "bash_stop"),
        ("POST", "/api/quests/q-001/terminal/sessions/terminal-main/attach", "terminal_attach"),
        ("GET", "/api/quests/q-001/node-traces", "node_traces"),
        ("GET", "/api/quests/q-001/node-traces/stage%3Amain%3Aidea", "node_trace"),
        ("POST", "/api/quests/q-001/stage-view", "stage_view"),
        ("GET", "/api/quests/q-001/layout", "quest_layout"),
        ("POST", "/api/quests/q-001/layout", "quest_layout_update"),
        ("GET", "/api/quests/q-001/graph", "graph"),
        ("GET", "/api/quests/q-001/graph/svg", "graph_asset"),
        ("GET", "/api/quests/q-001/git/branches", "git_branches"),
        ("GET", "/api/quests/q-001/git/canvas", "git_canvas"),
        ("GET", "/api/quests/q-001/git/log", "git_log"),
        ("GET", "/api/quests/q-001/git/compare", "git_compare"),
        ("GET", "/api/quests/q-001/git/commit", "git_commit"),
        ("GET", "/api/quests/q-001/git/diff-file", "git_diff_file"),
        ("GET", "/api/quests/q-001/git/commit-file", "git_commit_file"),
        ("GET", "/api/quests/q-001/operations/file-change-diff", "file_change_diff"),
        ("GET", "/api/quests/q-001/memory", "quest_memory"),
        ("GET", "/api/quests/q-001/documents", "documents"),
        ("GET", "/api/quests/q-001/explorer", "explorer"),
        ("POST", "/api/quests/q-001/files/folder", "quest_file_create_folder"),
        ("POST", "/api/quests/q-001/files/upload", "quest_file_upload"),
        ("POST", "/api/quests/q-001/files/rename", "quest_file_rename"),
        ("POST", "/api/quests/q-001/files/move", "quest_file_move"),
        ("POST", "/api/quests/q-001/files/delete", "quest_file_delete"),
        ("GET", "/api/quests/q-001/documents/asset", "document_asset"),
        ("POST", "/api/quests/q-001/documents/open", "document_open"),
        ("POST", "/api/quests/q-001/documents/assets", "document_asset_upload"),
        ("PUT", "/api/quests/q-001/documents/plan.md", "document_save"),
        ("PUT", "/api/quests/q-001/documents/path::literature/notes.md", "document_save"),
        ("POST", "/api/quests/q-001/chat/uploads", "chat_upload_create"),
        ("DELETE", "/api/quests/q-001/chat/uploads/draft-001", "chat_upload_delete"),
        ("POST", "/api/quests/q-001/chat", "chat"),
        ("POST", "/api/quests/q-001/commands", "command"),
        ("POST", "/api/quests/q-001/control", "quest_control"),
        ("POST", "/api/quests/q-001/runs", "run_create"),
        ("GET", "/api/v1/arxiv/list", "arxiv_list"),
        ("POST", "/api/v1/arxiv/import", "arxiv_import"),
        ("GET", "/api/v1/annotations/file/quest-file::q-001::path%3A%3Adocs%2Fpaper.pdf::docs%2Fpaper.pdf", "annotations_file"),
        ("GET", "/api/v1/annotations/project/q-001", "annotations_project"),
        ("POST", "/api/v1/annotations/", "annotation_create"),
        ("GET", "/api/v1/annotations/ann-001", "annotation_detail"),
        ("PATCH", "/api/v1/annotations/ann-001", "annotation_update"),
        ("DELETE", "/api/v1/annotations/ann-001", "annotation_delete"),
        ("POST", "/api/v1/projects/q-001/latex/init", "latex_init"),
        ("POST", "/api/v1/projects/q-001/latex/quest-dir::q-001::paper%2Flatex/compile", "latex_compile"),
        ("GET", "/api/v1/projects/q-001/latex/quest-dir::q-001::paper%2Flatex/builds", "latex_builds"),
        ("GET", "/api/v1/projects/q-001/latex/quest-dir::q-001::paper%2Flatex/builds/latex-001", "latex_build"),
        ("GET", "/api/v1/projects/q-001/latex/quest-dir::q-001::paper%2Flatex/builds/latex-001/pdf", "latex_build_pdf"),
        ("GET", "/api/v1/projects/q-001/latex/quest-dir::q-001::paper%2Flatex/builds/latex-001/log", "latex_build_log"),
        ("GET", "/api/v1/projects/q-001/latex/quest-dir::q-001::paper%2Flatex/archive", "latex_archive"),
        ("GET", "/api/config/files", "config_files"),
        ("GET", "/api/config/core", "config_show"),
        ("PUT", "/api/config/core", "config_save"),
    ]

    for method, path, expected in expected_routes:
        route_name, _params = match_route(method, path)
        assert route_name == expected, f"{method} {path} should resolve to {expected}, got {route_name!r}"


def test_web_client_uses_acp_and_git_surface_expected_by_backend() -> None:
    source = _read("src/ui/src/lib/api.ts")
    benchstore_source = _read("src/ui/src/lib/api/benchstore.ts")
    bash_source = _read("src/ui/src/lib/api/bash.ts")
    arxiv_source = _read("src/ui/src/lib/api/arxiv.ts")
    lab_source = _read("src/ui/src/lib/api/lab.ts")
    latex_source = _read("src/ui/src/lib/api/latex.ts")
    terminal_source = _read("src/ui/src/lib/api/terminal.ts")
    annotations_source = _read("src/ui/src/lib/plugins/pdf-viewer/api/annotations.ts")

    expected_fragments = [
        "/api/baselines",
        "/api/baselines/${encodeURIComponent(baselineId)}",
        "/api/system/update",
        "/api/quests/${questId}/session",
        "/api/quest-id/next",
        "/api/connectors/availability",
        "/api/connectors/weixin/login/qr/start",
        "/api/connectors/weixin/login/qr/wait",
        "/api/connectors/${encodeURIComponent(connectorName)}/profiles/${encodeURIComponent(profileId)}",
        "/api/quests/${questId}/settings",
        "/api/quests/${questId}/bindings",
        "/api/quests/${questId}`",
        "format=acp",
        "session_id=quest:${questId}",
        "stream=1",
        "/api/quests/${questId}/workflow",
        "/api/quests/${questId}/layout",
        "/api/quests/${questId}/artifacts",
        "/api/quests/${questId}/node-traces",
        "/api/quests/${questId}/stage-view",
        "/api/quests/${questId}/explorer",
        "/api/quests/${questId}/files/folder",
        "/api/quests/${questId}/files/upload",
        "/api/quests/${questId}/files/rename",
        "/api/quests/${questId}/files/move",
        "/api/quests/${questId}/files/delete",
        "/api/quests/${questId}/memory",
        "/api/quests/${questId}/documents",
        "/api/quests/${questId}/graph",
        "/api/quests/${questId}/git/branches",
        "/api/quests/${questId}/git/log",
        "/api/quests/${questId}/git/compare",
        "/api/quests/${questId}/git/commit",
        "/api/quests/${questId}/git/diff-file",
        "/api/quests/${questId}/git/commit-file",
        "/api/quests/${questId}/operations/file-change-diff",
        "/api/quests/${questId}/documents/open",
        "/api/quests/${questId}/documents/assets",
        "/api/quests/${questId}/chat",
        "/api/quests/${questId}/commands",
        "/api/quests/${questId}/runs",
        "/api/config/files",
        "/api/config/${name}",
    ]

    for fragment in expected_fragments:
        assert fragment in source, f"Web API client is missing contract fragment: {fragment}"

    benchstore_fragments = [
        "/api/benchstore/entries",
        "/api/benchstore/entries/${encodeURIComponent(entryId)}",
        "/api/benchstore/entries/${encodeURIComponent(entryId)}/image",
        "/api/benchstore/entries/${encodeURIComponent(entryId)}/setup-packet",
        "/api/benchstore/entries/${encodeURIComponent(entryId)}/install",
        "/api/benchstore/entries/${encodeURIComponent(entryId)}/launch",
    ]

    for fragment in benchstore_fragments:
        assert fragment in benchstore_source, f"BenchStore API client is missing contract fragment: {fragment}"

    bash_fragments = [
        "/api/quests/${projectId}/bash/sessions",
        "/api/quests/${projectId}/bash/sessions/${bashId}",
        "/api/quests/${projectId}/bash/sessions/${bashId}/logs",
        "/api/quests/${projectId}/bash/sessions/${bashId}/stop",
    ]

    for fragment in bash_fragments:
        assert fragment in bash_source, f"Bash API client is missing contract fragment: {fragment}"

    assert "/api/quests/${projectId}/bash/transcript" not in bash_source

    assert 'const ARXIV_BASE = "/api/v1/arxiv"' in arxiv_source
    assert "`${ARXIV_BASE}/list`" in arxiv_source
    assert "`${ARXIV_BASE}/import`" in arxiv_source

    annotation_fragments = [
        "/api/v1/annotations/file/${fileId}",
        "/api/v1/annotations/",
        "/api/v1/annotations/${id}",
        "/api/v1/annotations/project/${projectId}",
    ]

    for fragment in annotation_fragments:
        assert fragment in annotations_source, f"Annotation API client is missing contract fragment: {fragment}"

    lab_fragments = [
        "/baseline-binding",
        "questClient.baselines()",
    ]

    for fragment in lab_fragments:
        assert fragment in lab_source, f"Lab API client is missing contract fragment: {fragment}"

    latex_fragments = [
        "/api/v1/projects/${projectId}/latex/init",
        "/api/v1/projects/${projectId}/latex/${folderId}/compile",
        "/api/v1/projects/${projectId}/latex/${folderId}/builds",
        "/api/v1/projects/${projectId}/latex/${folderId}/builds/${buildId}",
        "/api/v1/projects/${projectId}/latex/${folderId}/builds/${buildId}/pdf",
        "/api/v1/projects/${projectId}/latex/${folderId}/builds/${buildId}/log",
        "/api/v1/projects/${projectId}/latex/${folderId}/archive",
    ]

    for fragment in latex_fragments:
        assert fragment in latex_source, f"LaTeX API client is missing contract fragment: {fragment}"

    terminal_fragments = [
        "/api/quests/${projectId}/terminal/session/ensure",
        "/api/quests/${projectId}/terminal/history",
        "/api/quests/${projectId}/terminal/sessions/${sessionId}/attach",
        "/api/quests/${projectId}/terminal/sessions/${sessionId}/input",
        "/api/quests/${projectId}/terminal/sessions/${sessionId}/restore",
    ]

    for fragment in terminal_fragments:
        assert fragment in terminal_source, f"Terminal API client is missing contract fragment: {fragment}"


def test_settings_control_center_client_prefers_system_alias_surface() -> None:
    settings_api_source = _read("src/ui/src/lib/api/admin.ts")
    task_stream_source = _read("src/ui/src/lib/hooks/useAdminTaskStream.ts")

    expected_fragments = [
        "const SYSTEM_BASE = '/api/system'",
        "${SYSTEM_BASE}/overview",
        "${SYSTEM_BASE}/quests",
        "${SYSTEM_BASE}/runtime/sessions",
        "${SYSTEM_BASE}/logs/sources",
        "${SYSTEM_BASE}/logs/tail",
        "${SYSTEM_BASE}/failures",
        "${SYSTEM_BASE}/errors",
        "${SYSTEM_BASE}/runtime-tools",
        "${SYSTEM_BASE}/hardware",
        "${SYSTEM_BASE}/audit",
        "${SYSTEM_BASE}/stats/summary",
        "${SYSTEM_BASE}/search",
        "${SYSTEM_BASE}/issues/draft",
        "${SYSTEM_BASE}/controllers",
        "${SYSTEM_BASE}/doctor",
        "${SYSTEM_BASE}/tasks",
        "${SYSTEM_BASE}/repairs",
    ]

    for fragment in expected_fragments:
        assert fragment in settings_api_source, f"Settings API client is missing system fragment: {fragment}"

    assert "/api/admin/" not in settings_api_source
    assert "/api/system/tasks/${encodeURIComponent(taskId)}/stream" in task_stream_source


def test_local_workspace_does_not_route_markdown_or_commands_through_dead_notebook_and_auth_paths() -> None:
    workspace_source = _read("src/ui/src/components/workspace/WorkspaceLayout.tsx")
    open_file_source = _read("src/ui/src/hooks/useOpenFile.ts")
    plugin_types_source = _read("src/ui/src/lib/types/plugin.ts")
    plugin_init_source = _read("src/ui/src/lib/plugin/init.ts")

    assert "getMyToken(" not in workspace_source
    assert "rotateMyToken(" not in workspace_source
    assert "TokenDialog" not in workspace_source
    assert "BUILTIN_PLUGINS.NOTEBOOK" in workspace_source
    assert "BUILTIN_PLUGINS.NOTEBOOK,\n    BUILTIN_PLUGINS.LATEX" not in workspace_source
    assert "updateTabPlugin(tab.id, BUILTIN_PLUGINS.NOTEBOOK" in workspace_source
    assert 'return BUILTIN_PLUGINS.NOTEBOOK;' in open_file_source
    assert '"text/markdown": BUILTIN_PLUGINS.NOTEBOOK' in plugin_types_source
    assert '".md": BUILTIN_PLUGINS.NOTEBOOK' in plugin_types_source
    assert 'extensions: [".md", ".markdown"],\n        mimeTypes: ["text/markdown", "text/x-markdown"],\n        priority: 95,' in plugin_init_source
    assert 'extensions: [".md", ".markdown"],\n        mimeTypes: ["text/markdown", "text/x-markdown"],\n        priority: 40,' not in plugin_init_source


def test_web_workspace_keeps_streaming_operational_views_and_tool_effect_surface() -> None:
    acp_source = _read("src/ui/src/lib/acp.ts")
    api_source = _read("src/ui/src/lib/api.ts")
    tool_ops_source = _read("src/ui/src/lib/toolOperations.ts")
    bash_tool_source = _read("src/ui/src/components/workspace/QuestBashExecOperation.tsx")
    workspace_surface_source = _read("src/ui/src/components/workspace/QuestWorkspaceSurface.tsx")
    workspace_layout_source = _read("src/ui/src/components/workspace/WorkspaceLayout.tsx")
    studio_timeline_source = _read("src/ui/src/components/workspace/QuestStudioDirectTimeline.tsx")
    studio_trace_source = _read("src/ui/src/components/workspace/QuestStudioTraceView.tsx")
    lab_canvas_source = _read("src/ui/src/lib/plugins/lab/components/LabQuestGraphCanvas.tsx")
    lab_api_source = _read("src/ui/src/lib/api/lab.ts")
    workspace_i18n_source = _read("src/ui/src/lib/i18n/messages/workspace.ts")

    assert "pendingFeed.some(" in acp_source
    assert "baselineCompare: (questId: string) =>" in api_source
    assert "window.setTimeout" in acp_source
    assert "client.workflow(targetQuestId)" in acp_source
    assert "ensureViewData" in acp_source
    assert "detailsEnabledRef.current = true" in acp_source
    assert "await flushDetailsRefresh(questId, options)" in acp_source
    assert "insertHistoryItemChronologically" in acp_source
    assert "previous_run_id" in acp_source
    assert "collectSealedAssistantRunIds(initialUpdates)" in acp_source
    assert "item.label === 'run_failed'" in acp_source
    assert "void ensureViewData('details')" in workspace_surface_source
    assert "onOpenStageSelection={onOpenStageSelection}" in workspace_surface_source
    assert "LabQuestGraphCanvas" in workspace_surface_source
    assert "QuestMemorySurface" in workspace_surface_source
    assert 'title="Baseline Compare"' in workspace_surface_source
    assert "updateView('memory')" in workspace_surface_source
    assert "BUILTIN_PLUGINS.GIT_COMMIT_VIEWER" in workspace_layout_source
    assert "onStageOpen(selection)" in lab_canvas_source
    assert "selectionType !== 'workflow_placeholder'" in lab_canvas_source
    assert "function resolveLocalBaselineAnchorNode" in lab_api_source
    assert "const rootNode = operationalNodes.find((node) => !String(node.parent_branch || '').trim())" in lab_api_source
    assert "const mainNode = operationalNodes.find((node) => node.branch_name === 'main')" in lab_api_source
    assert "const firstOperationalNode = resolveLocalBaselineAnchorNode(nodes, summary.branch || 'main')" in lab_api_source
    assert "quest_workspace_memory" in workspace_i18n_source
    assert "function StudioOperationBlock" in studio_timeline_source
    assert "item.type === 'operation'" in tool_ops_source
    assert "copilot_trace_empty_description" in studio_timeline_source
    assert "buildToolEffectPreviews" in tool_ops_source
    assert "<QuestStudioDirectTimeline" in studio_trace_source
    assert "McpBashExecView" in bash_tool_source


def test_tui_client_and_git_canvas_follow_same_protocol_contract() -> None:
    tui_source = _read("src/tui/src/lib/api.ts")
    tui_app_source = _read("src/tui/src/app/AppContainer.tsx")
    tui_history_source = _read("src/tui/src/components/HistoryItemDisplay.tsx")
    tui_bash_source = _read("src/tui/src/components/messages/BashExecOperationMessage.tsx")
    app_source = _read("src/ui/src/App.tsx")
    workspace_source = _read("src/ui/src/pages/ProjectWorkspacePage.tsx")
    canvas_source = _read("src/ui/src/components/git/GitResearchCanvas.tsx")

    tui_fragments = [
        "/api/quests/${questId}/events?after=${cursor}&format=acp&session_id=quest:${questId}",
        "text/event-stream",
        "stream=1",
        "/api/connectors",
        "/api/quests/${questId}/chat",
        "/api/quests/${questId}/commands",
        "/api/quests/${questId}/control",
        "/api/quests/${questId}/bash/sessions/${bashId}",
        "/api/quests/${questId}/bash/sessions/${bashId}/logs",
        "/api/quests/${questId}/bash/sessions/${bashId}/stream",
    ]
    canvas_fragments = [
        "/api/quests/${questId}/graph/svg",
        ".gitBranches(",
        ".gitCompare(",
        ".gitLog(",
        ".gitCommit(",
        ".gitDiffFile(",
        ".gitCommitFile(",
    ]

    for fragment in tui_fragments:
        assert fragment in tui_source, f"TUI API client is missing contract fragment: {fragment}"

    for fragment in canvas_fragments:
        assert fragment in canvas_source, f"Git canvas is missing contract fragment: {fragment}"

    assert "target.pathname = `/projects/${questId}`" in tui_app_source
    assert "client.configFiles(baseUrl)" in tui_app_source
    assert "stringifyStructured" in tui_app_source
    assert "openConfigBrowser" in tui_app_source
    assert "searchParams.set('quest'" not in tui_app_source
    assert "BashExecOperationMessage" in tui_history_source
    assert " | " in tui_bash_source
    assert "streamBashLogs" in tui_bash_source
    assert '/settings/:configName' in app_source
    assert "WorkspaceLayout" in workspace_source
    assert "projectId={projectId}" in workspace_source


def test_workspace_navbar_project_title_is_hard_limited() -> None:
    workspace_source = _read("src/ui/src/components/workspace/WorkspaceLayout.tsx")

    assert "const NAVBAR_PROJECT_TITLE_MAX_CHARS = 30" in workspace_source
    assert "truncateNavbarProjectTitle(projectDisplayName)" in workspace_source
    assert "'project-name-field max-w-[30ch]'" in workspace_source


def test_local_quest_workspace_uses_real_canvas_and_details_tabs() -> None:
    workspace_source = _read("src/ui/src/components/workspace/WorkspaceLayout.tsx")
    surface_source = _read("src/ui/src/components/workspace/QuestWorkspaceSurface.tsx")

    expected_workspace_fragments = [
        "const QUEST_WORKSPACE_PLUGIN_ID = '@ds/plugin-quest-workspace'",
        "buildQuestWorkspaceTabContext(projectId, view, stageSelection)",
        "openQuestWorkspaceTab('canvas')",
        "openQuestWorkspaceTab('details')",
        "openQuestWorkspaceTab('terminal')",
        "openQuestWorkspaceTab('settings')",
        "title: getQuestWorkspaceTitle(view, stageSelection)",
        "return getQuestWorkspaceTabView(resolvedTab)",
        "view={getQuestWorkspaceTabView(tab)}",
    ]
    for fragment in expected_workspace_fragments:
        assert fragment in workspace_source, f"Quest workspace tabs should include: {fragment}"

    expected_surface_fragments = [
        "view: controlledView",
        "onViewChange",
        "const view = controlledView ?? uncontrolledView",
        "workspaceLayerClass(view === 'canvas')",
        "view === 'terminal' ? (",
        "view === 'settings' ? (",
        "view === 'stage' ? (",
        "<QuestCanvasSurface",
        "<QuestTerminalSurface",
        "<QuestSettingsSurface",
        "<QuestStageSurface",
        "<QuestDetails",
    ]
    for fragment in expected_surface_fragments:
        assert fragment in surface_source, f"Quest surface should stay tab-controlled with: {fragment}"


def test_workspace_terminal_surface_uses_raw_pty_attach_flow() -> None:
    surface_source = _read("src/ui/src/components/workspace/QuestWorkspaceSurface.tsx")

    assert "attachTerminalSession(questId, bashId)" in surface_source
    assert "const socketUrl =" in surface_source
    assert "new WebSocket(socketUrl)" in surface_source
    assert "ws.binaryType = 'arraybuffer'" in surface_source
    assert "onBinary={handleTerminalBinaryInput}" in surface_source
    assert "convertEol={false}" in surface_source
    assert "sendLiveEnvelope({ type: 'resize', cols, rows })" in surface_source
    assert "replayRestoredEntry" in surface_source


def test_workspace_surfaces_hide_autofigure_entry_points() -> None:
    marketplace_source = _read("src/ui/src/lib/plugins/marketplace/MarketplacePlugin.tsx")
    workspace_source = _read("src/ui/src/components/workspace/WorkspaceLayout.tsx")
    builtin_loader_source = _read("src/ui/src/lib/plugin/builtin-loader.tsx")
    plugin_types_source = _read("src/ui/src/lib/types/plugin.ts")

    assert 'title: "AutoFigure"' not in marketplace_source
    assert "AUTOFIGURE" not in workspace_source
    assert "plugin-autofigure" not in builtin_loader_source
    assert "AUTOFIGURE" not in plugin_types_source


def test_workspace_studio_uses_direct_timeline_surface() -> None:
    studio_view_source = _read("src/ui/src/components/workspace/QuestStudioTraceView.tsx")
    studio_timeline_source = _read("src/ui/src/components/workspace/QuestStudioDirectTimeline.tsx")
    bash_tool_source = _read("src/ui/src/components/workspace/QuestBashExecOperation.tsx")
    studio_tool_cards_source = _read("src/ui/src/components/workspace/StudioToolCards.tsx")
    studio_turns_source = _read("src/ui/src/lib/studioTurns.ts")
    acp_bridge_source = _read("src/deepscientist/acp/bridge.py")
    mcp_identity_source = _read("src/ui/src/lib/mcpIdentity.ts")

    assert "QuestStudioDirectTimeline" in studio_view_source
    assert "<QuestStudioDirectTimeline" in studio_view_source
    assert "@DeepScientist" in studio_timeline_source
    assert "buildStudioTurns(feed)" in studio_timeline_source
    assert "findLatestRenderedOperationId" in studio_timeline_source
    assert "QuestBashExecOperation" in studio_timeline_source
    assert "if (isBashExecOperation(block)) {" in studio_timeline_source
    assert "StudioToolCard" in studio_timeline_source
    assert "preferBashTerminalRender" in bash_tool_source
    assert "buildArtifactModel" in studio_tool_cards_source
    assert "buildMemoryModel" in studio_tool_cards_source
    assert "buildBashModel" in studio_tool_cards_source
    assert "buildWebSearchModel" in studio_tool_cards_source
    assert "mergeFeedItemsForRender(items)" in studio_turns_source
    assert "runner.tool_call" in acp_bridge_source
    assert "runner.tool_result" in acp_bridge_source
    assert "artifact.recorded" in acp_bridge_source
    assert "deriveMcpIdentity" in mcp_identity_source


def test_artifact_tool_views_render_activate_branch_and_delivery_context() -> None:
    studio_tool_cards_source = _read("src/ui/src/components/workspace/StudioToolCards.tsx")
    artifact_tool_view_source = _read("src/ui/src/components/chat/toolViews/McpArtifactToolView.tsx")

    assert "activate_branch: active ? 'Activating branch' : 'Activated branch'" in studio_tool_cards_source
    assert "connector notified" in studio_tool_cards_source
    assert "latestMainRunId" in studio_tool_cards_source

    assert "function renderActivateBranch" in artifact_tool_view_source
    assert "function renderConnectorDelivery" in artifact_tool_view_source
    assert "activate_branch: active ? 'DeepScientist is activating branch...' : 'DeepScientist activated branch.'" in artifact_tool_view_source
    assert "Returning to a durable research branch should also sync the active workspace and connector context." in artifact_tool_view_source


def test_runner_settings_surface_exposes_reasoning_and_retry_controls() -> None:
    settings_catalog_source = _read("src/ui/src/components/settings/settingsFormCatalog.ts")
    settings_form_source = _read("src/ui/src/components/settings/RegistrySettingsForm.tsx")
    config_service_source = _read("src/deepscientist/config/service.py")
    doctor_source = _read("src/deepscientist/doctor.py")

    assert "{ label: 'Claude', value: 'claude' }" in settings_catalog_source
    assert "{ label: 'OpenCode', value: 'opencode' }" in settings_catalog_source
    assert "key: 'permission_mode'" in settings_catalog_source
    assert "key: 'default_agent'" in settings_catalog_source
    assert "key: 'variant'" in settings_catalog_source
    assert "key: 'model_reasoning_effort'" in settings_catalog_source
    assert "key: 'retry_on_failure'" in settings_catalog_source
    assert "key: 'retry_max_attempts'" in settings_catalog_source
    assert "key: 'retry_initial_backoff_sec'" in settings_catalog_source
    assert "key: 'retry_backoff_multiplier'" in settings_catalog_source
    assert "key: 'retry_max_backoff_sec'" in settings_catalog_source
    assert "retry_on_failure: true" in settings_form_source
    assert "retry_max_attempts: 7" in settings_form_source
    assert "retry_initial_backoff_sec: 10" in settings_form_source
    assert "retry_backoff_multiplier: 6" in settings_form_source
    assert "retry_max_backoff_sec: 1800" in settings_form_source
    assert "codex.retry_on_failure: true" in config_service_source
    assert "at most `7` total attempts" in config_service_source
    assert "10s / 6x / 1800s max" in config_service_source
    assert "Enable one of `codex`, `claude`, or `opencode`" in doctor_source


def test_ui_font_loading_uses_single_stylesheet_entrypoint() -> None:
    index_html_source = _read("src/ui/index.html")
    index_css_source = _read("src/ui/src/index.css")

    assert '%BASE_URL%assets/fonts/ds-fonts.css' in index_html_source
    assert "@import url('/assets/fonts/ds-fonts.css');" not in index_css_source


def test_local_quest_canvas_uses_single_lab_refresh_entrypoint() -> None:
    quest_surface_source = _read("src/ui/src/components/workspace/QuestWorkspaceSurface.tsx")
    lab_surface_source = _read("src/ui/src/lib/plugins/lab/components/LabSurface.tsx")
    lab_canvas_source = _read("src/ui/src/lib/plugins/lab/components/LabCanvasStudio.tsx")

    quest_canvas_block = quest_surface_source.split("function QuestCanvasSurface(", 1)[1].split(
        "\n\nfunction QuestTerminalLegacySurface(", 1
    )[0]

    assert "<WorkspaceRefreshButton onRefresh={handleRefresh} />" not in quest_canvas_block
    assert "onRefresh={handleRefresh}" in quest_canvas_block
    assert "onRefresh?: () => Promise<void> | void" in lab_surface_source
    assert "onRefresh={onRefresh}" in lab_surface_source
    assert "onRefresh?: () => Promise<void> | void" in lab_canvas_source
    assert "void Promise.resolve(onRefresh?.())" in lab_canvas_source


def test_update_reminders_show_manual_npm_command_in_web_surface() -> None:
    reminder_source = _read("src/ui/src/components/landing/UpdateReminderDialog.tsx")
    app_bar_source = _read("src/ui/src/components/projects/ProjectsAppBar.tsx")
    hero_nav_source = _read("src/ui/src/components/landing/HeroNav.tsx")
    update_button_source = _read("src/ui/src/components/system-update/SystemUpdateButton.tsx")
    dialog_source = _read("src/ui/src/components/system-update/SystemUpdateDialog.tsx")

    assert "manual_update_command" in dialog_source
    assert "systemUpdateAction('remind_later')" in reminder_source
    assert "SystemUpdateDialog" in reminder_source
    assert "prompt_recommended" in reminder_source
    assert "npm install -g @researai/deepscientist@latest" in dialog_source
    assert "Sparkles" in update_button_source
    assert "SystemUpdateButton" in app_bar_source
    assert "SystemUpdateButton" in hero_nav_source
    assert "install_latest" not in reminder_source
    assert "updateNow" not in reminder_source


def test_local_web_workspace_wraps_routes_with_auth_gate_and_shows_password_button() -> None:
    app_source = _read("src/ui/src/App.tsx")
    hero_nav_source = _read("src/ui/src/components/landing/HeroNav.tsx")
    auth_provider_source = _read("src/ui/src/components/auth/AuthProvider.tsx")

    assert "AuthProvider" in app_source
    assert "<AuthProvider>" in app_source
    assert "LocalAuthTokenButton" in hero_nav_source
    assert "api/auth/login" in auth_provider_source
    assert "fetchBrowserAuthToken" in auth_provider_source


def test_settings_control_center_exposes_summary_runtime_and_optional_ops_rail() -> None:
    app_source = _read("src/ui/src/App.tsx")
    settings_source = _read("src/ui/src/components/settings/SettingsPage.tsx")
    ops_rail_source = _read("src/ui/src/components/settings/SettingsOpsRail.tsx")

    assert 'path="/settings/runtime"' in app_source
    assert "SettingsSummarySection" in settings_source
    assert "SettingsRuntimeSection" in settings_source
    assert "SettingsOpsRail" in settings_source
    assert "SettingsOpsLauncher" in settings_source
    assert "dockOpen ? 'xl:grid-cols-[260px_minmax(0,1fr)_420px]'" in settings_source
    assert 'data-testid="settings-copilot-launcher"' in ops_rail_source
    assert 'data-testid="settings-copilot-rail"' in ops_rail_source
