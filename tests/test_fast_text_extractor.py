"""Tests for fast text extraction block grouping."""

from __future__ import annotations

from src.strategies.fast_text_extractor import _build_text_blocks_from_words


def test_build_text_blocks_groups_words_into_paragraphs() -> None:
    words = [
        {"text": "Revenue", "x0": 10, "x1": 40, "top": 100, "bottom": 110},
        {"text": "increased", "x0": 45, "x1": 90, "top": 100.5, "bottom": 110.5},
        {"text": "sharply", "x0": 95, "x1": 130, "top": 100.2, "bottom": 110.2},
        {"text": "this", "x0": 10, "x1": 25, "top": 114, "bottom": 124},
        {"text": "year.", "x0": 30, "x1": 55, "top": 114.1, "bottom": 124.1},
        # Large vertical gap -> second paragraph
        {"text": "Outlook", "x0": 10, "x1": 45, "top": 150, "bottom": 160},
        {"text": "remains", "x0": 50, "x1": 85, "top": 150.2, "bottom": 160.2},
        {"text": "positive.", "x0": 90, "x1": 130, "top": 150.1, "bottom": 160.1},
    ]

    blocks = _build_text_blocks_from_words(words=words, page_number=1, block_id_start=0)

    assert len(blocks) == 2
    assert blocks[0].text == "Revenue increased sharply this year."
    assert blocks[1].text == "Outlook remains positive."
    assert blocks[0].reading_order == 0
    assert blocks[1].reading_order == 1


def test_build_text_blocks_ignores_blank_words() -> None:
    words = [
        {"text": " ", "x0": 0, "x1": 0, "top": 0, "bottom": 0},
        {"text": "", "x0": 0, "x1": 0, "top": 0, "bottom": 0},
    ]
    blocks = _build_text_blocks_from_words(words=words, page_number=1, block_id_start=3)
    assert blocks == []

