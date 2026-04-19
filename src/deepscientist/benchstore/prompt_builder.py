from __future__ import annotations

import json

from pathlib import Path
from typing import Any

from ..shared import read_text


def _format_optional_lines(title: str, items: list[str]) -> list[str]:
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    if not cleaned:
        return [f"{title}: none"]
    return [f"{title}:"] + [f"- {item}" for item in cleaned]


class BenchStorePromptBuilder:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = Path(repo_root)
        self.system_prompt_path = self.repo_root / "src" / "prompts" / "benchstore" / "system.md"

    def system_prompt(self) -> str:
        return read_text(self.system_prompt_path).strip()

    def build_setup_prompt(
        self,
        *,
        entry: dict[str, Any],
        hardware_payload: dict[str, Any] | None = None,
        benchmark_local_path: str | None = None,
        locale: str = "zh",
    ) -> str:
        name = str(entry.get("name") or "Unnamed benchmark").strip() or "Unnamed benchmark"
        benchmark_id = str(entry.get("id") or "unknown").strip() or "unknown"
        one_line = str(entry.get("one_line") or "").strip()
        task_description = str(entry.get("task_description") or "").strip()
        recommended_when = str(entry.get("recommended_when") or "").strip()
        not_recommended_when = str(entry.get("not_recommended_when") or "").strip()
        capability_tags = [str(item).strip() for item in (entry.get("capability_tags") or []) if str(item).strip()]
        track_fit = [str(item).strip() for item in (entry.get("track_fit") or []) if str(item).strip()]
        primary_outputs = [str(item).strip() for item in (entry.get("primary_outputs") or []) if str(item).strip()]
        launch_profiles = entry.get("launch_profiles") if isinstance(entry.get("launch_profiles"), list) else []
        risk_flags = [str(item).strip() for item in (entry.get("risk_flags") or []) if str(item).strip()]
        risk_notes = [str(item).strip() for item in (entry.get("risk_notes") or []) if str(item).strip()]
        paper = entry.get("paper") if isinstance(entry.get("paper"), dict) else {}
        resources = entry.get("resources") if isinstance(entry.get("resources"), dict) else {}
        environment = entry.get("environment") if isinstance(entry.get("environment"), dict) else {}
        dataset_download = entry.get("dataset_download") if isinstance(entry.get("dataset_download"), dict) else {}
        credential_requirements = entry.get("credential_requirements") if isinstance(entry.get("credential_requirements"), dict) else {}
        minimum = resources.get("minimum") if isinstance(resources.get("minimum"), dict) else {}
        recommended = resources.get("recommended") if isinstance(resources.get("recommended"), dict) else {}
        dataset_sources = dataset_download.get("sources") if isinstance(dataset_download.get("sources"), list) else []
        credential_items = [str(item) for item in (credential_requirements.get("items") or []) if str(item).strip()]
        raw_payload = entry.get("raw_payload") if isinstance(entry.get("raw_payload"), dict) else {}
        hardware_summary = (
            str(hardware_payload.get("prompt_hardware_summary") or "").strip()
            if isinstance(hardware_payload, dict)
            else ""
        )
        local_path = str(benchmark_local_path or "").strip()

        locale_header = "请使用中文输出，并优先给出可执行、可落地、设备匹配的判断。" if locale == "zh" else (
            "Please respond in English and prefer concrete, device-aware, executable setup decisions."
        )

        lines: list[str] = [
            self.system_prompt(),
            "",
            "## Current Bench Context",
            f"- benchmark_id: {benchmark_id}",
            f"- benchmark_name: {name}",
            f"- one_line: {one_line or 'none'}",
            f"- aisb_direction: {str(entry.get('aisb_direction') or 'unknown').strip() or 'unknown'}",
            f"- task_mode: {str(entry.get('task_mode') or 'unknown').strip() or 'unknown'}",
            f"- requires_execution: {bool(entry.get('requires_execution'))}",
            f"- requires_paper: {bool(entry.get('requires_paper'))}",
            f"- integrity_level: {str(entry.get('integrity_level') or 'unknown').strip() or 'unknown'}",
            f"- snapshot_status: {str(entry.get('snapshot_status') or 'unknown').strip() or 'unknown'}",
            f"- support_level: {str(entry.get('support_level') or 'unknown').strip() or 'unknown'}",
            f"- difficulty: {str(entry.get('difficulty') or 'unknown').strip() or 'unknown'}",
            f"- time_band: {str(entry.get('time_band') or 'unknown').strip() or 'unknown'}",
            f"- cost_band: {str(entry.get('cost_band') or 'unknown').strip() or 'unknown'}",
            f"- data_access: {str(entry.get('data_access') or 'unknown').strip() or 'unknown'}",
        ]
        lines.extend(
            [
                "",
                "## Device Summary",
                f"- prompt_hardware_summary: {hardware_summary}" if hardware_summary else "- prompt_hardware_summary: unavailable",
            ]
        )
        lines.extend(["", "## Local Install State", f"- benchmark_local_path: {local_path or 'not installed or not resolved yet'}"])
        lines.extend(["", "## Benchmark Narrative", task_description or "- no long-form task_description was provided"])
        lines.extend(["", "## Paper Metadata"])
        lines.extend(
            [
                f"- paper_title: {str(paper.get('title') or 'unknown').strip() or 'unknown'}",
                f"- paper_venue: {str(paper.get('venue') or 'unknown').strip() or 'unknown'}",
                f"- paper_year: {str(paper.get('year') or 'unknown').strip() or 'unknown'}",
                f"- paper_url: {str(paper.get('url') or 'unknown').strip() or 'unknown'}",
            ]
        )
        lines.extend(["", "## Structured Resource Requirements"])
        lines.extend([f"- minimum: {minimum or {}}", f"- recommended: {recommended or {}}"])
        lines.extend(_format_optional_lines("primary_outputs", primary_outputs))
        lines.extend(
            _format_optional_lines(
                "launch_profiles",
                [
                    " | ".join(
                        part
                        for part in [
                            str(profile.get("id") or "").strip(),
                            str(profile.get("label") or "").strip(),
                            str(profile.get("description") or "").strip(),
                        ]
                        if part
                    )
                    for profile in launch_profiles
                    if isinstance(profile, dict)
                ],
            )
        )
        lines.extend(["", "## Runtime Environment"])
        lines.extend(
            [
                f"- python: {str(environment.get('python') or 'unknown').strip() or 'unknown'}",
                f"- cuda: {str(environment.get('cuda') or 'unknown').strip() or 'unknown'}",
                f"- pytorch: {str(environment.get('pytorch') or 'unknown').strip() or 'unknown'}",
                f"- flash_attn: {str(environment.get('flash_attn') or 'unknown').strip() or 'unknown'}",
            ]
        )
        lines.extend(_format_optional_lines("key_packages", [str(item) for item in (environment.get("key_packages") or [])]))
        lines.extend(_format_optional_lines("environment_notes", [str(item) for item in (environment.get("notes") or [])]))
        lines.extend(["", "## Dataset Route"])
        lines.extend(
            [
                f"- dataset_primary_method: {str(dataset_download.get('primary_method') or 'unknown').strip() or 'unknown'}",
            ]
        )
        lines.extend(_format_optional_lines("dataset_notes", [str(item) for item in (dataset_download.get("notes") or [])]))
        lines.extend(
            _format_optional_lines(
                "dataset_sources",
                [
                    " | ".join(
                        part
                        for part in [
                            str(source.get("kind") or "").strip(),
                            str(source.get("access") or "").strip(),
                            str(source.get("url") or "").strip(),
                            str(source.get("note") or "").strip(),
                        ]
                        if part
                    )
                    for source in dataset_sources
                    if isinstance(source, dict)
                ],
            )
        )
        lines.extend(["", "## Credential Requirements"])
        lines.extend(
            [
                f"- credential_mode: {str(credential_requirements.get('mode') or 'unknown').strip() or 'unknown'}",
            ]
        )
        lines.extend(_format_optional_lines("credential_items", credential_items))
        lines.extend(_format_optional_lines("credential_notes", [str(item) for item in (credential_requirements.get("notes") or [])]))
        lines.extend(["", "## Risks"])
        lines.extend(_format_optional_lines("risk_flags", risk_flags))
        lines.extend(_format_optional_lines("risk_notes", risk_notes))
        lines.extend(["", "## Tags and Routing Hints"])
        lines.extend(_format_optional_lines("capability_tags", capability_tags))
        lines.extend(_format_optional_lines("track_fit", track_fit))
        lines.extend(["", "## Fit Advice"])
        lines.extend([f"- recommended_when: {recommended_when or 'none'}", f"- not_recommended_when: {not_recommended_when or 'none'}"])
        if raw_payload:
            lines.extend(["", "## Raw Catalog Payload", "```json", json.dumps(raw_payload, ensure_ascii=False, indent=2), "```"])
        lines.extend(
            [
                "",
                "## Required Output",
                locale_header,
                "Prepare a benchmark-specific setup packet that is realistic for the current device.",
                "Do not produce a generic research brief.",
                "Do not fill missing benchmark facts with fabricated content.",
                "",
                "Your setup packet should determine:",
                "- a concrete project title",
                "- the real task goal for this benchmark",
                "- whether the current device is sufficient, borderline, or insufficient",
                "- the minimum safe runtime route",
                "- whether paper-facing output should stay in scope",
                "- benchmark-specific launch constraints",
                "- the strongest next launch instruction for the downstream runtime",
            ]
        )
        return "\n".join(lines).strip()
