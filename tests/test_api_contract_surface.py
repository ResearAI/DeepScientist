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
        ("GET", "/api/baselines", "baselines"),
        ("GET", "/api/quests", "quests"),
        ("GET", "/api/quest-id/next", "quest_next_id"),
        ("POST", "/api/quests", "quest_create"),
        ("GET", "/api/connectors", "connectors"),
        ("GET", "/api/connectors/availability", "connectors_availability"),
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
        ("GET", "/api/quests/q-001/graph", "graph"),
        ("GET", "/api/quests/q-001/graph/svg", "graph_asset"),
        ("GET", "/api/quests/q-001/git/branches", "git_branches"),
        ("GET", "/api/quests/q-001/git/log", "git_log"),
        ("GET", "/api/quests/q-001/git/compare", "git_compare"),
        ("GET", "/api/quests/q-001/git/commit", "git_commit"),
        ("GET", "/api/quests/q-001/git/diff-file", "git_diff_file"),
        ("GET", "/api/quests/q-001/git/commit-file", "git_commit_file"),
        ("GET", "/api/quests/q-001/memory", "quest_memory"),
        ("GET", "/api/quests/q-001/documents", "documents"),
        ("GET", "/api/quests/q-001/explorer", "explorer"),
        ("GET", "/api/quests/q-001/documents/asset", "document_asset"),
        ("POST", "/api/quests/q-001/documents/open", "document_open"),
        ("POST", "/api/quests/q-001/documents/assets", "document_asset_upload"),
        ("PUT", "/api/quests/q-001/documents/plan.md", "document_save"),
        ("PUT", "/api/quests/q-001/documents/path::literature/notes.md", "document_save"),
        ("POST", "/api/quests/q-001/chat", "chat"),
        ("POST", "/api/quests/q-001/commands", "command"),
        ("POST", "/api/quests/q-001/control", "quest_control"),
        ("POST", "/api/quests/q-001/runs", "run_create"),
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
    bash_source = _read("src/ui/src/lib/api/bash.ts")
    lab_source = _read("src/ui/src/lib/api/lab.ts")
    latex_source = _read("src/ui/src/lib/api/latex.ts")
    terminal_source = _read("src/ui/src/lib/api/terminal.ts")

    expected_fragments = [
        "/api/baselines",
        "/api/system/update",
        "/api/quests/${questId}/session",
        "/api/quest-id/next",
        "/api/connectors/availability",
        "/api/quests/${questId}/settings",
        "/api/quests/${questId}/bindings",
        "/api/quests/${questId}`",
        "format=acp",
        "session_id=quest:${questId}",
        "stream=1",
        "/api/quests/${questId}/workflow",
        "/api/quests/${questId}/artifacts",
        "/api/quests/${questId}/node-traces",
        "/api/quests/${questId}/stage-view",
        "/api/quests/${questId}/explorer",
        "/api/quests/${questId}/memory",
        "/api/quests/${questId}/documents",
        "/api/quests/${questId}/graph",
        "/api/quests/${questId}/git/branches",
        "/api/quests/${questId}/git/log",
        "/api/quests/${questId}/git/compare",
        "/api/quests/${questId}/git/commit",
        "/api/quests/${questId}/git/diff-file",
        "/api/quests/${questId}/git/commit-file",
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

    bash_fragments = [
        "/api/quests/${projectId}/bash/sessions",
        "/api/quests/${projectId}/bash/sessions/${bashId}",
        "/api/quests/${projectId}/bash/sessions/${bashId}/logs",
        "/api/quests/${projectId}/bash/sessions/${bashId}/stop",
    ]

    for fragment in bash_fragments:
        assert fragment in bash_source, f"Bash API client is missing contract fragment: {fragment}"

    assert "/api/quests/${projectId}/bash/transcript" not in bash_source

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
    feed_source = _read("src/ui/src/components/EventFeed.tsx")
    tool_ops_source = _read("src/ui/src/lib/toolOperations.ts")
    workspace_source = _read("src/ui/src/components/WorkflowStudio.tsx")
    bash_tool_source = _read("src/ui/src/components/workspace/QuestBashExecOperation.tsx")
    workspace_surface_source = _read("src/ui/src/components/workspace/QuestWorkspaceSurface.tsx")
    lab_canvas_source = _read("src/ui/src/lib/plugins/lab/components/LabQuestGraphCanvas.tsx")
    lab_api_source = _read("src/ui/src/lib/api/lab.ts")
    workspace_i18n_source = _read("src/ui/src/lib/i18n/messages/workspace.ts")

    assert "pendingFeed.some(" in acp_source
    assert "window.setTimeout" in acp_source
    assert "client.workflow(targetQuestId)" in acp_source
    assert "ensureViewData" in acp_source
    assert "view === 'details' || view === 'memory'" in acp_source
    assert "void ensureViewData(view)" in workspace_surface_source
    assert "onOpenStageSelection={onOpenStageSelection}" in workspace_surface_source
    assert "QuestMemorySurface" in workspace_surface_source
    assert "updateView('memory')" in workspace_surface_source
    assert "onStageOpen(selection)" in lab_canvas_source
    assert "selectionType !== 'workflow_placeholder'" in lab_canvas_source
    assert "function resolveLocalBaselineAnchorNode" in lab_api_source
    assert "const rootNode = operationalNodes.find((node) => !String(node.parent_branch || '').trim())" in lab_api_source
    assert "const mainNode = operationalNodes.find((node) => node.branch_name === 'main')" in lab_api_source
    assert "const firstOperationalNode = resolveLocalBaselineAnchorNode(nodes, summary.branch || 'main')" in lab_api_source
    assert "quest_workspace_memory" in workspace_i18n_source
    assert "function OperationBlock" in feed_source
    assert "item.type === 'operation'" in feed_source
    assert "ACP-compatible copilot events will appear here." in feed_source
    assert "buildToolEffectPreviews" in tool_ops_source
    assert "<EventFeed questId={questId} items={feed} />" in workspace_source
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
        "view={resolvedQuestWorkspaceView}",
    ]
    for fragment in expected_workspace_fragments:
        assert fragment in workspace_source, f"Quest workspace tabs should include: {fragment}"

    expected_surface_fragments = [
        "view: controlledView",
        "onViewChange",
        "const view = controlledView ?? uncontrolledView",
        "view === 'canvas' ? (",
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

    assert 'title: "AutoFigure"' not in marketplace_source
    assert "tab.pluginId === BUILTIN_PLUGINS.AUTOFIGURE" in workspace_source


def test_workspace_studio_uses_direct_timeline_surface() -> None:
    studio_view_source = _read("src/ui/src/components/workspace/QuestStudioTraceView.tsx")
    studio_timeline_source = _read("src/ui/src/components/workspace/QuestStudioDirectTimeline.tsx")
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
    assert "StudioToolCard" in studio_timeline_source
    assert "buildArtifactModel" in studio_tool_cards_source
    assert "buildMemoryModel" in studio_tool_cards_source
    assert "buildBashModel" in studio_tool_cards_source
    assert "buildWebSearchModel" in studio_tool_cards_source
    assert "mergeFeedItemsForRender(items)" in studio_turns_source
    assert "runner.tool_call" in acp_bridge_source
    assert "runner.tool_result" in acp_bridge_source
    assert "artifact.recorded" in acp_bridge_source
    assert "deriveMcpIdentity" in mcp_identity_source


def test_runner_settings_surface_exposes_reasoning_and_retry_controls() -> None:
    settings_catalog_source = _read("src/ui/src/components/settings/settingsFormCatalog.ts")
    settings_form_source = _read("src/ui/src/components/settings/RegistrySettingsForm.tsx")
    config_service_source = _read("src/deepscientist/config/service.py")

    assert "{ label: 'Claude', value: 'claude' }" not in settings_catalog_source
    assert "not runnable yet" in settings_catalog_source
    assert "key: 'model_reasoning_effort'" in settings_catalog_source
    assert "key: 'retry_on_failure'" in settings_catalog_source
    assert "key: 'retry_max_attempts'" in settings_catalog_source
    assert "key: 'retry_initial_backoff_sec'" in settings_catalog_source
    assert "key: 'retry_backoff_multiplier'" in settings_catalog_source
    assert "key: 'retry_max_backoff_sec'" in settings_catalog_source
    assert "retry_on_failure: true" in settings_form_source
    assert "retry_max_attempts: 5" in settings_form_source
    assert "codex.retry_on_failure: true" in config_service_source
    assert "at most `5` total attempts" in config_service_source
    assert "not runnable yet" in config_service_source


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
