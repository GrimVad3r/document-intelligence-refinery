"""Fast text-based extraction strategy using pdfplumber.

This strategy is cost-efficient and is the default for native digital,
single-column documents where a reliable character stream is present.
"""

from __future__ import annotations

import time
from typing import Tuple

import pdfplumber  # type: ignore[import-untyped]

from ..models.document_profile import DocumentProfile
from ..models.extracted_document import ExtractedDocument, Table, TableCell, TextBlock
from ..models.provenance import BoundingBox
from ..utils.errors import ExtractionError
from ..utils.logging import get_logger
from .base import BaseExtractor


logger = get_logger(__name__)


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

                    # Text blocks
                    for char_block in page.extract_words(use_text_flow=True) or []:
                        text = char_block.get("text", "")
                        if not text.strip():
                            continue
                        x0 = float(char_block.get("x0", 0.0))
                        y0 = float(char_block.get("bottom", 0.0))
                        x1 = float(char_block.get("x1", 0.0))
                        y1 = float(char_block.get("top", 0.0))
                        bbox = BoundingBox(page_number=page_index, x0=x0, y0=y0, x1=x1, y1=y1)

                        total_chars += len(text)
                        block = TextBlock(
                            id=f"block-{block_id_counter}",
                            text=text,
                            page_number=page_index,
                            bbox=bbox,
                            reading_order=block_id_counter,
                        )
                        text_blocks.append(block)
                        block_id_counter += 1

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

