"""Tests for the triage agent."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import A4  # type: ignore[import-untyped]
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

from src.agents.triage import triage_document
from src.utils.errors import TriageError


def _make_simple_pdf(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    text = c.beginText(40, 800)
    text.textLine("Sample Financial Report")
    text.textLine("Balance sheet and income statement for FY 2024.")
    c.drawText(text)
    c.showPage()
    c.save()


def test_triage_missing_document_raises(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.pdf"
    with pytest.raises(TriageError):
        triage_document(doc_id="missing_doc", document_path=str(missing_path))


def test_triage_produces_profile_for_simple_pdf(tmp_path: Path) -> None:
    pdf_path = tmp_path / "simple.pdf"
    _make_simple_pdf(pdf_path)

    profile = triage_document(doc_id="simple_doc", document_path=str(pdf_path))

    assert profile.doc_id == "simple_doc"
    assert profile.origin_type is not None
    assert profile.layout_complexity is not None
    assert profile.language.code in {"en", "unknown"}
    assert profile.heuristic_signals.avg_chars_per_page >= 0

    assert os.path.exists(
        os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            ".refinery",
            "profiles",
            "simple_doc.json",
        )
    )

