from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from deepscientist.config import ConfigManager
from deepscientist.home import ensure_home_layout, repo_root
import deepscientist.latex_runtime as latex_runtime
from deepscientist.latex_runtime import (
    QuestLatexService,
    _latex_source_tokens,
    _parse_synctex_records,
    _source_selection_for_synctex,
    _synctex_sample_points,
)
from deepscientist.quest import QuestService
from deepscientist.skills import SkillInstaller


def test_parse_synctex_edit_records() -> None:
    payload = _parse_synctex_records(
        "\n".join(
            [
                "SyncTeX result begin",
                "Output:/tmp/main.pdf",
                "Input:/tmp/project/sections/intro.tex",
                "Line:42",
                "Column:7",
                "Offset:0",
                "Context:ignored",
                "SyncTeX result end",
            ]
        )
    )

    assert payload["input"] == "/tmp/project/sections/intro.tex"
    assert payload["line"] == "42"
    assert payload["column"] == "7"


def test_source_selection_prefers_exact_pdf_word_near_synctex_column() -> None:
    source = "\n".join(
        [
            r"\section{Method}",
            r"The method baseline is different from the improved method used here.",
            "",
        ]
    )

    selection = _source_selection_for_synctex(
        source,
        line=2,
        column=55,
        pdf_word="method",
    )

    assert selection["precision"] == "exact_word"
    assert selection["start_line"] == 2
    assert selection["text"] == "method"
    assert selection["start_column"] > source.splitlines()[1].index("improved")
    assert selection["end_column"] > selection["start_column"]


def test_source_selection_uses_pdf_line_context_for_repeated_words() -> None:
    line = "The method baseline is different from the improved method used here."
    source = "\\section{Method}\n" + line + "\n"

    selection = _source_selection_for_synctex(
        source,
        line=2,
        column=1,
        pdf_word="method",
        pdf_context_words=["different", "from", "the", "improved", "method", "used", "here"],
        pdf_context_index=4,
    )

    assert selection["precision"] == "exact_word"
    assert selection["text"] == "method"
    assert selection["start_column"] == line.rindex("method") + 1


def test_source_selection_never_selects_entire_line_when_word_is_missing() -> None:
    source = "This line has several source tokens but not the PDF token.\n"

    selection = _source_selection_for_synctex(
        source,
        line=1,
        column=19,
        pdf_word="unmatched",
    )

    assert selection["precision"] == "nearest_token"
    assert selection["start_line"] == 1
    assert selection["end_line"] == 1
    assert selection["end_column"] - selection["start_column"] < len(source)


def test_source_selection_ignores_trailing_latex_comments() -> None:
    source = "\n".join(
        [
            r"\begin{document}",
            r"% method only appears in this comment",
            r"Visible method appears here. % another method comment",
            "",
        ]
    )

    tokens = _latex_source_tokens(source, min_line=1, max_line=4)
    assert not any(token["line"] == 2 and token["text"] == "method" for token in tokens)
    assert not any(token["text"] == "another" for token in tokens)

    selection = _source_selection_for_synctex(
        source,
        line=2,
        column=4,
        pdf_word="method",
    )

    assert selection["precision"] == "exact_word"
    assert selection["start_line"] == 3
    assert selection["text"] == "method"


def test_source_selection_ignores_latex_comment_environment() -> None:
    source = "\n".join(
        [
            r"\begin{comment}",
            "method inside comment environment",
            r"\end{comment}",
            "Visible method outside comment.",
            "",
        ]
    )

    selection = _source_selection_for_synctex(
        source,
        line=2,
        column=3,
        pdf_word="method",
    )

    assert selection["precision"] == "exact_word"
    assert selection["start_line"] == 4
    assert selection["text"] == "method"


def test_single_letter_pdf_word_does_not_match_substrings() -> None:
    source = "alpha beta gamma\n"

    selection = _source_selection_for_synctex(
        source,
        line=1,
        column=3,
        pdf_word="a",
    )

    assert selection["precision"] == "line_column"
    assert selection["start_column"] == 3
    assert selection["end_column"] == 3
    assert selection["text"] == ""


def test_single_letter_pdf_word_can_select_exact_article_only() -> None:
    source = "alpha beta a gamma\n"

    selection = _source_selection_for_synctex(
        source,
        line=1,
        column=12,
        pdf_word="a",
    )

    assert selection["precision"] == "exact_word"
    assert selection["text"] == "a"
    assert selection["start_column"] == source.index(" a ") + 2
    assert selection["end_column"] == selection["start_column"] + 1


def test_low_information_pdf_word_without_evidence_moves_to_line_start() -> None:
    source = r"Prior work \cite{smith2020} reports 2 different results in section 2." + "\n"

    selection = _source_selection_for_synctex(
        source,
        line=1,
        column=None,
        pdf_word="2",
        pdf_context_words=["2"],
        pdf_context_index=0,
    )

    assert selection["precision"] == "line_start"
    assert selection["reason"] == "low_information_pdf_word_insufficient_evidence"
    assert selection["start_line"] == 1
    assert selection["start_column"] == 1
    assert selection["end_column"] == 1
    assert selection["text"] == ""


def test_low_information_pdf_word_with_column_support_can_select_source_token() -> None:
    source = "The model achieved 2 improvements and section 2 confirms it.\n"
    target_column = source.index("2") + 1

    selection = _source_selection_for_synctex(
        source,
        line=1,
        column=target_column,
        pdf_word="2",
    )

    assert selection["precision"] == "exact_word"
    assert selection["text"] == "2"
    assert selection["start_line"] == 1
    assert selection["start_column"] == target_column
    assert selection["end_column"] == target_column + 1


def test_low_information_pdf_word_with_context_support_can_select_source_token() -> None:
    source = "The model achieved 2 improvements.\n"

    selection = _source_selection_for_synctex(
        source,
        line=1,
        column=None,
        pdf_word="2",
        pdf_context_words=["model", "achieved", "2", "improvements"],
        pdf_context_index=2,
    )

    assert selection["precision"] == "exact_word"
    assert selection["text"] == "2"
    assert selection["start_line"] == 1
    assert selection["start_column"] == source.index("2") + 1


def test_source_selection_maps_maketitle_back_to_title_declaration() -> None:
    source = "\n".join(
        [
            r"\documentclass{article}",
            r"\title{\red{Precise Risk-to-Proof Joint Inspection}}",
            r"\author{Anonymous Authors}",
            r"\begin{document}",
            r"\maketitle",
            r"\section{Introduction}",
            "",
        ]
    )

    selection = _source_selection_for_synctex(
        source,
        line=5,
        column=None,
        pdf_word="Risk-to-Proof",
        pdf_context_words=["Precise", "Risk-to-Proof", "Joint", "Inspection"],
        pdf_context_index=1,
    )

    assert selection["precision"] == "exact_word"
    assert selection["start_line"] == 2
    assert selection["text"] == "Risk-to-Proof"
    assert selection["strategy"] == "front_matter"
    assert selection["region"] == "title"


def test_source_selection_maps_ieee_abstract_display_back_to_abstract_not_keywords() -> None:
    source = "\n".join(
        [
            r"\documentclass[journal]{IEEEtran}",
            r"\begin{document}",
            r"\IEEEtitleabstractindextext{",
            r"\begin{abstract}",
            r"Outsourced training is used for industrial fault diagnosis models.",
            r"\end{abstract}",
            r"\begin{IEEEkeywords}",
            r"Outsourced training, industrial fault diagnosis.",
            r"\end{IEEEkeywords}}",
            r"\maketitle",
            r"\IEEEdisplaynontitleabstractindextext",
            "",
        ]
    )

    selection = _source_selection_for_synctex(
        source,
        line=11,
        column=None,
        pdf_word="Outsourced",
        pdf_context_words=["Outsourced", "training", "is", "used", "for"],
        pdf_context_index=0,
    )

    assert selection["precision"] == "exact_word"
    assert selection["start_line"] == 5
    assert selection["text"] == "Outsourced"
    assert selection["strategy"] == "front_matter"
    assert selection["region"] == "abstract"


def test_source_selection_maps_front_matter_macro_invocation_to_title_use() -> None:
    source = "\n".join(
        [
            r"\documentclass{article}",
            r"\newcommand{\name}{$\mathtt{PoL\mbox{-}JI}$\xspace}",
            r"\begin{document}",
            r"\title{\name: Risk-aware inspection}",
            r"\maketitle",
            "",
        ]
    )

    selection = _source_selection_for_synctex(
        source,
        line=5,
        column=None,
        pdf_word="PoL-JI",
        pdf_context_words=["PoL-JI", "Risk-aware", "inspection"],
        pdf_context_index=0,
    )

    assert selection["precision"] == "exact_word"
    assert selection["start_line"] == 4
    assert selection["text"] == r"\name"
    assert selection["strategy"] == "front_matter"
    assert selection["region"] == "title"


def test_synctex_sample_points_prioritize_pdf_word_center_and_bbox() -> None:
    samples = _synctex_sample_points(
        10,
        20,
        pdf_word_center={"x": 30, "y": 40},
        pdf_word_bbox={"left": 20, "top": 35, "right": 44, "bottom": 47},
    )

    assert samples[0]["kind"] == "word_center"
    assert samples[0]["x"] == 30
    assert samples[0]["y"] == 40
    assert any(sample["kind"] == "click" for sample in samples)
    assert len(samples) >= 5


def test_synctex_edit_returns_backend_source_selection_range(temp_home: Path, monkeypatch) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("synctex precise selection quest")
    quest_root = Path(quest["quest_root"])
    project_id = quest["quest_id"]

    latex_root = quest_root / "paper" / "latex"
    latex_root.mkdir(parents=True, exist_ok=True)
    source_line = "The method baseline is different from the improved method used here."
    source_path = latex_root / "main.tex"
    source_path.write_text("\\documentclass{article}\n" + source_line + "\n", encoding="utf-8")
    pdf_path = latex_root / "main.pdf"
    synctex_path = latex_root / "main.synctex.gz"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    synctex_path.write_bytes(b"fake synctex")

    service = QuestLatexService(quest_service)
    folder_id = f"quest-dir::{project_id}::paper%2Flatex"
    build_id = "latex-test-selection"
    build_path = service._build_record_path(project_id, "paper/latex", build_id)
    build_path.parent.mkdir(parents=True, exist_ok=True)
    build_path.write_text(
        __import__("json").dumps(
            {
                "build_id": build_id,
                "project_id": project_id,
                "folder_id": folder_id,
                "folder_path": "paper/latex",
                "output_pdf_path": str(pdf_path),
                "synctex_ready": True,
                "synctex_path": str(synctex_path),
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        latex_runtime.RuntimeToolService,
        "resolve_binary",
        lambda self, binary, preferred_tools=(): {"path": "/usr/bin/synctex", "source": "test"},
    )

    def _fake_run(*args, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout="\n".join(
                [
                    "SyncTeX result begin",
                    f"Input:{source_path}",
                    "Line:2",
                    "Column:1",
                    "Offset:0",
                    "SyncTeX result end",
                ]
            ),
            stderr="",
        )

    monkeypatch.setattr(latex_runtime.subprocess, "run", _fake_run)

    result = service.synctex_edit(
        project_id,
        folder_id,
        build_id,
        page=1,
        x=10,
        y=20,
        pdf_word="method",
        pdf_context_words=["different", "from", "the", "improved", "method", "used", "here"],
        pdf_context_index=4,
        pdf_word_bbox={"left": 8, "top": 18, "right": 28, "bottom": 26},
        pdf_word_center={"x": 18, "y": 22},
    )

    assert result["ok"] is True
    assert result["precision"] == "exact_word"
    assert result["sample_count"] >= 5
    assert result["selection"]["text"] == "method"
    assert result["selection"]["start_line"] == 2
    assert result["selection"]["start_column"] == source_line.rindex("method") + 1


def test_latex_manifest_lists_nested_editable_files(temp_home: Path) -> None:
    ensure_home_layout(temp_home)
    ConfigManager(temp_home).ensure_files()
    quest_service = QuestService(temp_home, skill_installer=SkillInstaller(repo_root(), temp_home))
    quest = quest_service.create("latex manifest nested files quest")
    quest_root = Path(quest["quest_root"])
    project_id = quest["quest_id"]

    latex_root = quest_root / "paper" / "latex"
    sections_root = latex_root / "sections"
    sections_root.mkdir(parents=True, exist_ok=True)
    (latex_root / "main.tex").write_text(
        "\n".join(
            [
                r"\documentclass{article}",
                r"\begin{document}",
                r"\input{sections/intro}",
                r"\bibliography{refs}",
                r"\end{document}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (sections_root / "intro.tex").write_text(r"\section{Intro}" + "\n", encoding="utf-8")
    (latex_root / "refs.bib").write_text("@article{x,title={X}}\n", encoding="utf-8")

    folder_id = f"quest-dir::{project_id}::paper%2Flatex"
    manifest = QuestLatexService(quest_service).manifest(project_id, folder_id)

    by_relative = {item["relative_path"]: item for item in manifest["files"]}
    assert manifest["main_file_path"] == "paper/latex/main.tex"
    assert by_relative["main.tex"]["role"] == "main"
    assert by_relative["sections/intro.tex"]["role"] == "tex"
    assert by_relative["refs.bib"]["role"] == "bib"
    assert {"kind": "input", "path": "sections/intro.tex"} in by_relative["main.tex"]["dependencies"]
    assert {"kind": "bibliography", "path": "refs.bib"} in by_relative["main.tex"]["dependencies"]
