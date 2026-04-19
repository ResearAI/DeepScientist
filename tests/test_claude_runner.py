from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from deepscientist.runners import ClaudeRunner, OpenCodeRunner, RunRequest
from deepscientist.runners.runtime_overrides import apply_claude_runtime_overrides


def _runner(cls, *, binary: str):
    return cls(
        home=Path('/tmp'),
        repo_root=Path('/tmp'),
        binary=binary,
        logger=SimpleNamespace(),
        prompt_builder=SimpleNamespace(),
        artifact_service=SimpleNamespace(),
    )


def test_claude_runner_preserves_mcp_identity_on_tool_results() -> None:
    runner = _runner(ClaudeRunner, binary='claude')
    state: dict[str, object] = {}

    tool_call_events, _ = runner._translate_event(
        {
            'type': 'assistant',
            'message': {
                'id': 'msg-1',
                'content': [
                    {
                        'type': 'tool_use',
                        'id': 'tool-1',
                        'name': 'mcp__artifact__get_quest_state',
                        'input': {'detail': 'summary'},
                    }
                ],
            },
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:00Z',
        translation_state=state,
    )
    tool_result_events, _ = runner._translate_event(
        {
            'type': 'user',
            'message': {
                'content': [
                    {
                        'type': 'tool_result',
                        'tool_use_id': 'tool-1',
                        'content': [{'type': 'text', 'text': '{"ok": true}'}],
                    }
                ],
            },
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:01Z',
        translation_state=state,
    )

    assert tool_call_events[0]['mcp_server'] == 'artifact'
    assert tool_call_events[0]['mcp_tool'] == 'get_quest_state'
    assert tool_result_events[0]['tool_name'] == 'mcp__artifact__get_quest_state'
    assert tool_result_events[0]['mcp_server'] == 'artifact'
    assert tool_result_events[0]['mcp_tool'] == 'get_quest_state'


def test_claude_runner_emits_reasoning_for_thinking_blocks() -> None:
    runner = _runner(ClaudeRunner, binary='claude')
    events, texts = runner._translate_event(
        {
            'type': 'assistant',
            'message': {
                'id': 'msg-thinking',
                'content': [
                    {'type': 'thinking', 'thinking': 'Let me reason this through.'},
                    {'type': 'text', 'text': 'Final answer.'},
                ],
            },
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:00Z',
        translation_state={},
    )

    assert [event['type'] for event in events] == ['runner.reasoning', 'runner.agent_message']
    assert events[0]['kind'] == 'thinking'
    assert 'reason this through' in events[0]['text']
    assert texts == ['Final answer.']


def test_claude_runner_compacts_extreme_tool_results() -> None:
    runner = _runner(ClaudeRunner, binary='claude')
    huge_text = 'x' * (3 * 1024 * 1024)
    state: dict[str, object] = {
        'known_tools': {
            'tool-big': {
                'tool_name': 'mcp__artifact__get_quest_state',
                'mcp_server': 'artifact',
                'mcp_tool': 'get_quest_state',
            }
        }
    }
    events, _ = runner._translate_event(
        {
            'type': 'user',
            'message': {
                'content': [
                    {
                        'type': 'tool_result',
                        'tool_use_id': 'tool-big',
                        'content': huge_text,
                    }
                ],
            },
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:01Z',
        translation_state=state,
    )

    assert events[0]['type'] == 'runner.tool_result'
    assert events[0]['output_truncated'] is True
    assert events[0]['output_bytes'] > 2_000_000
    assert len(str(events[0]['output'])) < 20_000


def test_claude_runner_command_uses_configured_permission_mode(temp_home: Path) -> None:
    runner = ClaudeRunner(
        home=temp_home,
        repo_root=temp_home,
        binary='claude',
        logger=SimpleNamespace(),
        prompt_builder=SimpleNamespace(),
        artifact_service=SimpleNamespace(),
    )
    request = RunRequest(
        quest_id='q-001',
        quest_root=temp_home,
        worktree_root=temp_home,
        run_id='run-001',
        skill_id='decision',
        message='hello',
        model='inherit',
        approval_policy='never',
        sandbox_mode='danger-full-access',
    )

    command = runner._build_command(request, 'prompt', runner_config={'permission_mode': 'bypassPermissions'})

    assert command[0].endswith('claude')
    assert '--permission-mode' in command
    assert command[command.index('--permission-mode') + 1] == 'bypassPermissions'
    assert '--model' not in command


def test_apply_claude_runtime_overrides_maps_yolo_and_model(monkeypatch) -> None:
    monkeypatch.setenv('DEEPSCIENTIST_CLAUDE_MODEL', 'claude-sonnet-4-5')
    monkeypatch.setenv('DEEPSCIENTIST_CLAUDE_YOLO', 'true')
    monkeypatch.setenv('DEEPSCIENTIST_CLAUDE_MAX_TURNS', '88')

    rendered = apply_claude_runtime_overrides({'permission_mode': 'default'})

    assert rendered['model'] == 'claude-sonnet-4-5'
    assert rendered['permission_mode'] == 'bypassPermissions'
    assert rendered['max_turns'] == '88'


def test_opencode_runner_preserves_mcp_identity_on_tool_results() -> None:
    runner = _runner(OpenCodeRunner, binary='opencode')
    state: dict[str, object] = {}

    tool_call_events, _ = runner._translate_event(
        {
            'type': 'tool_call',
            'id': 'tool-2',
            'tool': 'mcp__bash_exec__bash_exec',
            'input': {'command': 'pwd'},
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='experiment',
        created_at='2026-04-14T00:00:00Z',
        translation_state=state,
    )
    tool_result_events, _ = runner._translate_event(
        {
            'type': 'tool_result',
            'toolCallID': 'tool-2',
            'output': {'status': 'completed', 'cwd': '/tmp/quest'},
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='experiment',
        created_at='2026-04-14T00:00:01Z',
        translation_state=state,
    )

    assert tool_call_events[0]['mcp_server'] == 'bash_exec'
    assert tool_call_events[0]['mcp_tool'] == 'bash_exec'
    assert tool_result_events[0]['tool_name'] == 'mcp__bash_exec__bash_exec'
    assert tool_result_events[0]['mcp_server'] == 'bash_exec'
    assert tool_result_events[0]['mcp_tool'] == 'bash_exec'


def test_opencode_runner_translates_real_tool_use_payload_into_call_and_result() -> None:
    runner = _runner(OpenCodeRunner, binary='opencode')
    state: dict[str, object] = {}

    events, _ = runner._translate_event(
        {
            'type': 'tool_use',
            'sessionID': 'ses-1',
            'part': {
                'type': 'tool',
                'tool': 'artifact_get_quest_state',
                'callID': 'call-1',
                'messageID': 'msg-1',
                'state': {
                    'status': 'completed',
                    'input': {'detail': 'summary'},
                    'output': '{"quest_id":"q-001"}',
                },
            },
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:00Z',
        translation_state=state,
    )
    message_events, texts = runner._translate_event(
        {
            'type': 'text',
            'sessionID': 'ses-1',
            'part': {
                'type': 'text',
                'messageID': 'msg-2',
                'text': 'DONE: hello',
            },
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:01Z',
        translation_state=state,
    )

    assert [event['type'] for event in events] == ['runner.tool_call', 'runner.tool_result']
    assert events[0]['tool_name'] == 'mcp__artifact__get_quest_state'
    assert events[0]['mcp_server'] == 'artifact'
    assert events[0]['mcp_tool'] == 'get_quest_state'
    assert events[1]['tool_name'] == 'mcp__artifact__get_quest_state'
    assert events[1]['mcp_server'] == 'artifact'
    assert events[1]['mcp_tool'] == 'get_quest_state'
    assert events[1]['output'] == '{"quest_id":"q-001"}'
    assert message_events[0]['type'] == 'runner.agent_message'
    assert message_events[0]['text'] == 'DONE: hello'
    assert texts == ['DONE: hello']


def test_opencode_runner_does_not_emit_result_for_running_tool_use() -> None:
    runner = _runner(OpenCodeRunner, binary='opencode')
    state: dict[str, object] = {}

    events, _ = runner._translate_event(
        {
            'type': 'tool_use',
            'sessionID': 'ses-1',
            'part': {
                'type': 'tool',
                'tool': 'artifact_get_quest_state',
                'callID': 'call-running',
                'messageID': 'msg-1',
                'state': {
                    'status': 'running',
                    'input': {'detail': 'summary'},
                },
            },
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:00Z',
        translation_state=state,
    )

    assert [event['type'] for event in events] == ['runner.tool_call']


def test_opencode_runner_dedups_separate_tool_result_after_inline_terminal() -> None:
    runner = _runner(OpenCodeRunner, binary='opencode')
    state: dict[str, object] = {}

    inline_events, _ = runner._translate_event(
        {
            'type': 'tool_use',
            'sessionID': 'ses-1',
            'part': {
                'type': 'tool',
                'tool': 'artifact_get_quest_state',
                'callID': 'call-dup',
                'state': {'status': 'completed', 'output': 'inline-result'},
            },
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:00Z',
        translation_state=state,
    )
    separate_events, _ = runner._translate_event(
        {
            'type': 'tool_result',
            'toolCallID': 'call-dup',
            'output': 'separate-result',
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:01Z',
        translation_state=state,
    )

    assert [event['type'] for event in inline_events] == ['runner.tool_call', 'runner.tool_result']
    assert inline_events[1]['output'] == 'inline-result'
    assert separate_events == []


def test_opencode_runner_tool_result_empty_output_does_not_leak_record() -> None:
    runner = _runner(OpenCodeRunner, binary='opencode')
    state: dict[str, object] = {}

    _, _ = runner._translate_event(
        {'type': 'tool_call', 'id': 'call-empty', 'tool': 'artifact_x', 'input': {'k': 'v'}},
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:00Z',
        translation_state=state,
    )
    result_events, _ = runner._translate_event(
        {'type': 'tool_result', 'toolCallID': 'call-empty', 'output': None, 'sensitive_input': 'secret'},
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:01Z',
        translation_state=state,
    )

    assert len(result_events) == 1
    assert result_events[0]['output'] == ''
    assert 'secret' not in result_events[0]['output']


def test_opencode_runner_inline_terminal_empty_output_does_not_leak_state() -> None:
    runner = _runner(OpenCodeRunner, binary='opencode')
    state: dict[str, object] = {}

    events, _ = runner._translate_event(
        {
            'type': 'tool_use',
            'part': {
                'type': 'tool',
                'tool': 'artifact_x',
                'callID': 'call-inline-empty',
                'state': {
                    'status': 'completed',
                    'input': {'very_long_secret_input': 'hunter2' * 100},
                },
            },
        },
        raw_line='',
        quest_id='q-001',
        run_id='run-001',
        skill_id='decision',
        created_at='2026-04-14T00:00:00Z',
        translation_state=state,
    )

    assert [event['type'] for event in events] == ['runner.tool_call', 'runner.tool_result']
    assert events[1]['output'] == ''


def test_opencode_runner_prepare_runtime_uses_allow_permission_mode_by_default(temp_home: Path) -> None:
    quest_root = temp_home / 'quest'
    quest_root.mkdir(parents=True, exist_ok=True)
    runner = OpenCodeRunner(
        home=temp_home,
        repo_root=temp_home,
        binary='opencode',
        logger=SimpleNamespace(),
        prompt_builder=SimpleNamespace(),
        artifact_service=SimpleNamespace(),
    )

    env, meta = runner._prepare_runtime(
        workspace_root=quest_root,
        quest_root=quest_root,
        quest_id='q-001',
        run_id='run-001',
        runner_config={'config_dir': str(temp_home / 'missing-opencode-home')},
    )

    config_path = Path(str(meta['opencode_config']))
    payload = json.loads(config_path.read_text(encoding='utf-8'))
    assert env['XDG_CONFIG_HOME'].endswith('.config')
    assert payload['permission'] == 'allow'
    assert payload['mcp']['artifact']['enabled'] is True
