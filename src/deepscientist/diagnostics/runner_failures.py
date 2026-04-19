from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FailureDiagnosis:
    code: str
    problem: str
    why: str
    guidance: tuple[str, ...]
    retriable: bool
    matched_text: str | None = None


_MODEL_UNAVAILABLE_MARKERS = (
    "unknown model",
    "invalid model",
    "model not found",
    "unsupported model",
    "model is not available",
    "not authorized to use model",
    "you do not have access",
    "access to model",
    "model access",
    "unrecognized model",
)


def _build_haystack(*values: object) -> str:
    return "\n".join(str(value or "") for value in values if str(value or "").strip())


def _contains(text: str, marker: str) -> bool:
    return marker in text.lower()


def diagnose_runner_failure(
    *,
    runner_name: str,
    summary: str = "",
    stderr_text: str = "",
    output_text: str = "",
) -> FailureDiagnosis | None:
    haystack = _build_haystack(summary, stderr_text, output_text)
    lower = haystack.lower()
    normalized_runner = str(runner_name or "").strip().lower()

    if (
        "tool call result does not follow tool call (2013)" in lower
        or "tool result's tool id" in lower
    ):
        return FailureDiagnosis(
            code="minimax_tool_result_sequence_error",
            problem="MiniMax rejected the tool result sequence.",
            why=(
                "The tool result did not immediately follow the corresponding tool call, "
                "or the tool result referenced a tool call id that was no longer valid."
            ),
            guidance=(
                "Keep each tool result immediately after its matching tool call.",
                "Do not insert an extra assistant message between a tool call and its tool result.",
                "For MiniMax chat-wire sessions, serialize tool use one call at a time.",
            ),
            retriable=False,
            matched_text="2013",
        )

    if (
        "invalid function arguments json string" in lower
        or "failed to parse tool call arguments" in lower
        or "trailing characters at line 1 column" in lower
    ):
        return FailureDiagnosis(
            code="chat_wire_tool_argument_parse_error",
            problem="The runner emitted malformed tool-call arguments.",
            why=(
                "The tool-call arguments were not a single valid JSON object. "
                "This usually happens when multiple tool calls are batched into one response "
                "or when the arguments string contains trailing characters."
            ),
            guidance=(
                "Serialize tool calls one at a time instead of batching multiple MCP calls together.",
                "Make sure each tool call emits exactly one complete JSON object for its arguments.",
                "If this is a MiniMax chat-wire path, stay on the serialized single-tool compatibility route.",
            ),
            retriable=False,
            matched_text="tool-call arguments",
        )

    if "argument list too long" in lower or "[errno 7]" in lower:
        return FailureDiagnosis(
            code="runner_argument_list_too_long",
            problem="The runner command exceeded the OS argument-length limit.",
            why=(
                "This usually happens when a runner needs to receive a very large prompt through argv "
                "instead of stdin or a file-backed prompt path."
            ),
            guidance=(
                "Retry with a shorter fallback prompt that references the quest brief and saved prompt files.",
                "Prefer stdin-capable runners such as Codex or Claude for very large turn prompts.",
                "If the problem persists, inspect `.ds/runs/<run_id>/prompt.md` and reduce duplicated context.",
            ),
            retriable=False,
            matched_text="argument list too long",
        )

    if "missing environment variable" in lower:
        return FailureDiagnosis(
            code="provider_env_missing",
            problem="A required provider environment variable is missing.",
            why="The configured model provider expects an API key or env var that was not present in the runner environment.",
            guidance=(
                "Set the required key in `~/DeepScientist/config/runners.yaml` under `runners.codex.env`.",
                "If you launch from a shell, export the provider key in that same shell before starting `ds`.",
            ),
            retriable=False,
            matched_text="missing environment variable",
        )

    if any(marker in lower for marker in _MODEL_UNAVAILABLE_MARKERS):
        return FailureDiagnosis(
            code="runner_model_unavailable",
            problem="The configured runner model is not available.",
            why="The selected provider or Codex account could not access the requested model id.",
            guidance=(
                "Set `model: inherit` for provider-backed Codex profiles unless the provider explicitly supports the model id.",
                "If you need a fixed model, verify that the same model works in plain `codex exec` before retrying DeepScientist.",
            ),
            retriable=False,
            matched_text="model unavailable",
        )

    if normalized_runner == "codex" and "invalid params" in lower and "bad_request_error" in lower:
        return FailureDiagnosis(
            code="provider_invalid_params",
            problem="The provider rejected the request parameters.",
            why="The upstream provider returned a deterministic request-shape error instead of a transient transport failure.",
            guidance=(
                "Inspect the immediately preceding tool call / tool result sequence for protocol ordering or JSON-shape mistakes.",
                "Do not keep retrying the same request until the request payload or provider config is corrected.",
            ),
            retriable=False,
            matched_text="invalid params",
        )

    if normalized_runner == "codex" and (
        "unknown file extension" in lower
        or ("file extension" in lower and ".png" in lower)
        or ("file extension" in lower and ".jpg" in lower)
        or ("file extension" in lower and ".jpeg" in lower)
        or ("file extension" in lower and ".gif" in lower)
        or ("file extension" in lower and ".webp" in lower)
        or ("file extension" in lower and ".bmp" in lower)
        or ("file extension" in lower and ".mp4" in lower)
    ):
        return FailureDiagnosis(
            code="runner_binary_attachment_path_unsupported",
            problem="Codex rejected a binary attachment path from the prompt.",
            why=(
                "The request exposed an image, video, or other binary file path that the Codex CLI tried to treat "
                "as an inline readable input, but that extension is not supported on stdin-driven prompt parsing."
            ),
            guidance=(
                "Prefer OCR text, extracted text, or archive manifests over raw binary attachment paths in the runner prompt.",
                "If a milestone needs binary delivery, keep the binary path inside the tool call payload instead of embedding it directly in prompt guidance.",
                "Do not keep retrying the same turn until the prompt or attachment summary no longer exposes the unsupported binary path.",
            ),
            retriable=False,
            matched_text="unknown file extension",
        )

    return None
