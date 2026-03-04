"""Vision-augmented extraction strategy using a multimodal LLM via HTTP API.

This strategy is designed for scanned or low-confidence documents where
text-based strategies underperform. It assumes an OpenRouter-compatible
API endpoint, but the HTTP client is written generically.
"""

from __future__ import annotations

import base64
import os
import time
from typing import Any, Dict, List, Tuple

import httpx  # type: ignore[import-untyped]
import pdfplumber  # type: ignore[import-untyped]

from ..models.document_profile import DocumentProfile
from ..models.extracted_document import ExtractedDocument, TextBlock
from ..models.provenance import BoundingBox
from ..utils.errors import ConfigError, ExtractionError
from ..utils.logging import get_logger
from .base import BaseExtractor


logger = get_logger(__name__)

DEFAULT_VISION_MODEL = os.getenv("REFINERY_VISION_MODEL", "openrouter/gpt-4o-mini")
OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"


class VisionExtractor(BaseExtractor):
    """High-cost vision-augmented extraction strategy with budget guarding."""

    def __init__(self, budget_usd: float = 0.50) -> None:
        self.budget_usd = budget_usd
        self.last_cost_estimate: float = 0.0

    def extract(self, document_path: str, profile: DocumentProfile) -> Tuple[ExtractedDocument, float]:
        api_key = os.getenv(OPENROUTER_API_KEY_ENV)
        if not api_key:
            raise ConfigError(
                f"VisionExtractor requires {OPENROUTER_API_KEY_ENV} to be set for API access."
            )

        start_time = time.time()
        pages_png: List[bytes] = []

        try:
            with pdfplumber.open(document_path) as pdf:
                for page in pdf.pages:
                    pil_img = page.to_image(resolution=144).original
                    buf = self._pil_to_png_bytes(pil_img)
                    pages_png.append(buf)
        except Exception as exc:  # noqa: BLE001
            logger.exception("VisionExtractor failed to rasterize PDF", document_path=document_path)
            raise ExtractionError(f"VisionExtractor rasterization failed for {document_path}") from exc

        total_cost_estimate = 0.0
        text_blocks: List[TextBlock] = []
        block_id = 0

        client = httpx.Client(timeout=60.0)

        for page_number, png_bytes in enumerate(pages_png, start=1):
            if total_cost_estimate > self.budget_usd:
                logger.warning(
                    "VisionExtractor budget exceeded, stopping early",
                    extra={"document_path": document_path, "budget_usd": self.budget_usd},
                )
                break

            page_text, est_cost = self._call_vision_model(client, api_key, png_bytes)
            total_cost_estimate += est_cost

            if not page_text.strip():
                continue

            bbox = BoundingBox(page_number=page_number, x0=0, y0=0, x1=0, y1=0)
            block = TextBlock(
                id=f"vision-block-{block_id}",
                text=page_text,
                page_number=page_number,
                bbox=bbox,
                reading_order=block_id,
            )
            text_blocks.append(block)
            block_id += 1

        client.close()

        if not text_blocks:
            raise ExtractionError("VisionExtractor produced no text blocks.")

        self.last_cost_estimate = total_cost_estimate
        confidence_score = 0.9
        duration = time.time() - start_time

        logger.info(
            "VisionExtractor completed",
            extra={
                "document_path": document_path,
                "num_pages": len(pages_png),
                "blocks": len(text_blocks),
                "confidence_score": confidence_score,
                "cost_estimate_usd": total_cost_estimate,
                "duration_sec": duration,
            },
        )

        extracted = ExtractedDocument(
            document_id=profile.doc_id,
            num_pages=len(pages_png),
            text_blocks=text_blocks,
            tables=[],
            figures=[],
            metadata={},
        )

        return extracted, confidence_score

    @staticmethod
    def _pil_to_png_bytes(image: Any) -> bytes:
        """Serialize a PIL image to PNG bytes."""

        from io import BytesIO

        buf = BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()

    def _call_vision_model(
        self,
        client: httpx.Client,
        api_key: str,
        png_bytes: bytes,
    ) -> Tuple[str, float]:
        """Call the multimodal vision model and return extracted text and cost estimate."""

        encoded_image = base64.b64encode(png_bytes).decode("ascii")
        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": "You are a document OCR and layout parser. Extract readable text preserving table structure using markdown where appropriate.",
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Extract all text content from this page, preserving table structure in markdown when possible.",
                    },
                    {
                        "type": "input_image",
                        "image_url": {
                            "url": f"data:image/png;base64,{encoded_image}",
                        },
                    },
                ],
            },
        ]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        body = {
            "model": DEFAULT_VISION_MODEL,
            "messages": messages,
        }

        try:
            response = client.post("https://openrouter.ai/api/v1/chat/completions", json=body, headers=headers)
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            logger.exception("VisionExtractor API call failed")
            raise ExtractionError("VisionExtractor API call failed") from exc

        data = response.json()
        text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )

        # Very rough cost estimate based on content length
        tokens_estimate = max(1, len(text) // 4)
        # Assume $0.15 per 1k tokens as a conservative upper bound
        cost_estimate = tokens_estimate / 1000.0 * 0.15

        return text, cost_estimate

