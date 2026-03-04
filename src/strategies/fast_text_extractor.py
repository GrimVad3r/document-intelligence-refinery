"""Fast text-based extraction strategy using pdfplumber.

This strategy is cost-efficient and is the default for native digital,
single-column documents where a reliable character stream is present.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple

import pdfplumber  # type: ignore[import-untyped]

from ..models.document_profile import DocumentProfile
from ..models.extracted_document import ExtractedDocument, Table, TableCell, TextBlock
from ..models.provenance import BoundingBox
from ..utils.errors import ExtractionError
from ..utils.logging import get_logger
from .base import BaseExtractor


logger = get_logger(__name__)


def _make_bbox(page_number: int, x0: float, top: float, x1: float, bottom: float) -> BoundingBox:
    """Create a bounding box from pdfplumber-style coordinates."""

    return BoundingBox(page_number=page_number, x0=x0, y0=bottom, x1=x1, y1=top)


def _build_text_blocks_from_words(
    words: List[Dict[str, Any]],
    page_number: int,
    block_id_start: int,
    line_merge_tolerance: float = 2.5,
) -> List[TextBlock]:
    """Group word-level OCR into paragraph-like text blocks.

    The fast extractor previously emitted one block per word, which caused
    extremely fragmented LDUs and poor retrieval quality. This groups words
    into lines first, then merges adjacent lines into paragraph-like blocks.
    """

    cleaned: List[Dict[str, Any]] = []
    for word in words:
        text = str(word.get("text", "")).strip()
        if not text:
            continue
        cleaned.append(
            {
                "text": text,
                "x0": float(word.get("x0", 0.0)),
                "x1": float(word.get("x1", 0.0)),
                "top": float(word.get("top", 0.0)),
                "bottom": float(word.get("bottom", 0.0)),
            }
        )

    if not cleaned:
        return []

    cleaned.sort(key=lambda w: (w["top"], w["x0"]))

    # 1) Merge words into lines
    lines: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None
    for word in cleaned:
        if current is None:
            current = {
                "words": [word],
                "top": word["top"],
                "bottom": word["bottom"],
                "x0": word["x0"],
                "x1": word["x1"],
            }
            continue

        same_line = abs(word["top"] - float(current["top"])) <= line_merge_tolerance
        if same_line:
            current["words"].append(word)
            current["top"] = min(float(current["top"]), word["top"])
            current["bottom"] = max(float(current["bottom"]), word["bottom"])
            current["x0"] = min(float(current["x0"]), word["x0"])
            current["x1"] = max(float(current["x1"]), word["x1"])
        else:
            lines.append(current)
            current = {
                "words": [word],
                "top": word["top"],
                "bottom": word["bottom"],
                "x0": word["x0"],
                "x1": word["x1"],
            }

    if current is not None:
        lines.append(current)

    for line in lines:
        line["words"].sort(key=lambda w: w["x0"])
        line["text"] = " ".join(w["text"] for w in line["words"])
        line["height"] = max(1.0, float(line["bottom"]) - float(line["top"]))

    lines.sort(key=lambda ln: (float(ln["top"]), float(ln["x0"])))

    # 2) Merge lines into paragraph-like blocks
    paragraphs: List[Dict[str, Any]] = []
    para: Dict[str, Any] | None = None

    def _start_para(line: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "lines": [line],
            "top": float(line["top"]),
            "bottom": float(line["bottom"]),
            "x0": float(line["x0"]),
            "x1": float(line["x1"]),
        }

    for line in lines:
        if para is None:
            para = _start_para(line)
            continue

        prev_line = para["lines"][-1]
        prev_bottom = float(prev_line["bottom"])
        gap = float(line["top"]) - prev_bottom
        max_line_height = max(float(prev_line["height"]), float(line["height"]))
        paragraph_break_threshold = max(3.0, max_line_height * 1.4)

        if gap > paragraph_break_threshold:
            paragraphs.append(para)
            para = _start_para(line)
            continue

        para["lines"].append(line)
        para["top"] = min(float(para["top"]), float(line["top"]))
        para["bottom"] = max(float(para["bottom"]), float(line["bottom"]))
        para["x0"] = min(float(para["x0"]), float(line["x0"]))
        para["x1"] = max(float(para["x1"]), float(line["x1"]))

    if para is not None:
        paragraphs.append(para)

    text_blocks: List[TextBlock] = []
    for i, paragraph in enumerate(paragraphs):
        text = " ".join(str(line["text"]).strip() for line in paragraph["lines"] if str(line["text"]).strip())
        if not text:
            continue
        text_blocks.append(
            TextBlock(
                id=f"block-{block_id_start + i}",
                text=text,
                page_number=page_number,
                bbox=_make_bbox(
                    page_number=page_number,
                    x0=float(paragraph["x0"]),
                    top=float(paragraph["top"]),
                    x1=float(paragraph["x1"]),
                    bottom=float(paragraph["bottom"]),
                ),
                reading_order=block_id_start + i,
            )
        )

    return text_blocks


class FastTextExtractor(BaseExtractor):
    """Implementation of the low-cost text extraction strategy."""

    def extract(self, document_path: str, profile: DocumentProfile) -> Tuple[ExtractedDocument, float]:
        start_time = time.time()
        try:
            with pdfplumber.open(document_path) as pdf:
                text_blocks = []
                tables = []

                total_chars = 0
                total_area = 0.0
                total_image_area = 0.0

                block_id_counter = 0
                table_id_counter = 0

                for page_index, page in enumerate(pdf.pages, start=1):
                    page_width = float(page.width or 0.0)
                    page_height = float(page.height or 0.0)
                    page_area = page_width * page_height if page_width and page_height else 0.0
                    total_area += page_area

                    # Text blocks: group words into paragraph-like blocks.
                    page_words = page.extract_words(use_text_flow=True) or []
                    page_blocks = _build_text_blocks_from_words(
                        words=page_words,
                        page_number=page_index,
                        block_id_start=block_id_counter,
                    )
                    for block in page_blocks:
                        total_chars += len(block.text)
                    text_blocks.extend(page_blocks)
                    block_id_counter += len(page_blocks)

                    # Tables (basic heuristic using extract_tables)
                    for table_data in page.extract_tables() or []:
                        if not table_data:
                            continue
                        headers = [h.strip() if h else "" for h in table_data[0]]
                        rows = table_data[1:]
                        cells = []
                        for r_idx, row in enumerate(rows):
                            for c_idx, value in enumerate(row):
                                cell_text = (value or "").strip()
                                if not cell_text:
                                    continue
                                cell = TableCell(
                                    row_index=r_idx,
                                    col_index=c_idx,
                                    text=cell_text,
                                    bbox=None,
                                )
                                cells.append(cell)

                        table = Table(
                            id=f"table-{table_id_counter}",
                            page_number=page_index,
                            caption=None,
                            headers=headers,
                            cells=cells,
                        )
                        tables.append(table)
                        table_id_counter += 1

                    # Estimate image area ratio
                    for image in page.images or []:
                        x0 = float(image.get("x0", 0.0))
                        y0 = float(image.get("y0", 0.0))
                        x1 = float(image.get("x1", 0.0))
                        y1 = float(image.get("y1", 0.0))
                        total_image_area += max(0.0, (x1 - x0) * (y1 - y0))

                if not pdf.pages:
                    raise ExtractionError("No pages found in PDF during fast text extraction.")

                num_pages = len(pdf.pages)

        except Exception as exc:  # noqa: BLE001
            logger.exception("FastTextExtractor failed", document_path=document_path)
            raise ExtractionError(f"FastTextExtractor failed for {document_path}") from exc

        avg_chars_per_page = total_chars / max(num_pages, 1)
        char_density = (total_chars / total_area) if total_area > 0 else 0.0
        image_area_ratio = (total_image_area / total_area) if total_area > 0 else 0.0

        # Confidence: higher when char density high and image area low
        confidence_components = []
        if avg_chars_per_page > 200:
            confidence_components.append(0.4)
        elif avg_chars_per_page > 100:
            confidence_components.append(0.25)
        else:
            confidence_components.append(0.1)

        if char_density > 0.002:
            confidence_components.append(0.4)
        elif char_density > 0.001:
            confidence_components.append(0.25)
        else:
            confidence_components.append(0.1)

        if image_area_ratio < 0.1:
            confidence_components.append(0.2)
        elif image_area_ratio < 0.3:
            confidence_components.append(0.1)
        else:
            confidence_components.append(0.0)

        confidence_score = min(1.0, max(0.0, sum(confidence_components)))

        duration = time.time() - start_time
        logger.info(
            "FastTextExtractor completed",
            extra={
                "document_path": document_path,
                "num_pages": num_pages,
                "avg_chars_per_page": avg_chars_per_page,
                "char_density": char_density,
                "image_area_ratio": image_area_ratio,
                "confidence_score": confidence_score,
                "duration_sec": duration,
            },
        )

        extracted = ExtractedDocument(
            document_id=profile.doc_id,
            num_pages=num_pages,
            text_blocks=text_blocks,
            tables=tables,
            figures=[],
            metadata={},
        )

        return extracted, confidence_score

