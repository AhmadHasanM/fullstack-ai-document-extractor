import re
import google.generativeai as genai
from typing import Dict, List


class MarkdownFormatter:
    """Format extracted content into structured markdown using Gemini"""

    def __init__(self, api_key: str):
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel("gemini-2.5-flash")
        else:
            self.model = None
            print("Warning: No Gemini API key. Using basic formatting.")

    async def format(self, extraction_result: Dict) -> str:
        if not self.model:
            return self._basic_format(extraction_result)

        try:
            content_summary = self._prepare_content_summary(
                extraction_result
            )

            if not self._has_meaningful_content(
                extraction_result,
                content_summary
            ):
                return self._basic_format(
                    extraction_result
                )

            prompt = self._build_prompt(content_summary)

            response = self.model.generate_content(
                prompt
            )

            text = self._safe_response_text(
                response
            )

            if not text.strip():
                return self._basic_format(
                    extraction_result
                )

            return text.strip()

        except Exception as e:
            print(
                f"Error formatting with Gemini: {e}"
            )
            return self._basic_format(
                extraction_result
            )

    # ------------------------------------------------ #
    # Gemini prompt                                    #
    # ------------------------------------------------ #

    def _build_prompt(
        self,
        content_summary: str
    ) -> str:
        return f"""
You are a document formatter.

Your ONLY task is converting OCR/PDF extracted text into clean Markdown.

STRICT RULES:
- Use ONLY the provided content.
- DO NOT invent title, author, abstract, references, formulas, tables, sections, or explanations.
- DO NOT add information that does not exist in source text.
- If text is noisy, preserve meaning and clean spacing only.
- If title is clearly visible in source, use it.
- If title is not clear, use "# Document".
- Keep original reading order.
- Preserve headings when visible.
- Preserve paragraphs.
- Preserve lists.
- Preserve tables only if present in source.
- Preserve images using provided image paths only.
- If text is incomplete, keep it incomplete. Never guess missing parts.
- Output Markdown only.

SOURCE CONTENT:

{content_summary}
"""

    # ------------------------------------------------ #
    # Validation                                       #
    # ------------------------------------------------ #

    def _has_meaningful_content(
        self,
        extraction_result: Dict,
        content_summary: str
    ) -> bool:

        page_texts = []

        for page in extraction_result.get(
            "pages",
            []
        ):
            txt = page.get(
                "raw_text",
                ""
            ).strip()

            if txt:
                page_texts.append(txt)

        merged = " ".join(page_texts).strip()

        if len(merged) >= 80:
            return True

        alpha_count = len(
            re.findall(
                r"[A-Za-z0-9]",
                merged
            )
        )

        if alpha_count >= 40:
            return True

        if len(content_summary.strip()) >= 120:
            return True

        return False

    def _safe_response_text(
        self,
        response
    ) -> str:
        try:
            if hasattr(response, "text"):
                if response.text:
                    return response.text
        except Exception:
            pass

        try:
            candidates = getattr(
                response,
                "candidates",
                []
            )

            for candidate in candidates:
                content = getattr(
                    candidate,
                    "content",
                    None
                )

                if not content:
                    continue

                parts = getattr(
                    content,
                    "parts",
                    []
                )

                texts = []

                for part in parts:
                    t = getattr(
                        part,
                        "text",
                        ""
                    )

                    if t:
                        texts.append(t)

                if texts:
                    return "\n".join(texts)

        except Exception:
            pass

        return ""

    # ------------------------------------------------ #
    # Content summary                                  #
    # ------------------------------------------------ #

    def _prepare_content_summary(
        self,
        extraction_result: Dict
    ) -> str:
        parts = []

        for page in extraction_result.get(
            "pages",
            []
        ):
            page_num = page.get(
                "page_number",
                "?"
            )

            text = page.get(
                "raw_text",
                ""
            ).strip()

            if text:
                parts.append(
                    f"\n--- Page {page_num} ---\n{text}"
                )

        tables = extraction_result.get(
            "tables",
            []
        )

        if tables:
            parts.append(
                "\n\n--- Tables ---"
            )

            for table in tables:
                page_num = table.get(
                    "page_number",
                    "?"
                )

                parts.append(
                    f"\nTable (page {page_num}):"
                )

                parts.append(
                    table.get(
                        "markdown",
                        ""
                    )
                )

        images = extraction_result.get(
            "images",
            []
        )

        if images:
            parts.append(
                "\n\n--- Images ---"
            )

            for img in images:
                parts.append(
                    f"Image file: "
                    f"{img['path']} | "
                    f"page {img['page_number']}"
                )

        return "\n".join(parts)

    # ------------------------------------------------ #
    # Basic fallback                                   #
    # ------------------------------------------------ #

    def _basic_format(
        self,
        extraction_result: Dict
    ) -> str:
        parts: List[str] = []

        parts.append("# Document\n")

        pages = extraction_result.get(
            "pages",
            []
        )

        for page in pages:
            page_num = page.get(
                "page_number",
                "?"
            )

            raw_text = page.get(
                "raw_text",
                ""
            ).strip()

            parts.append(
                f"\n## Page {page_num}\n"
            )

            if raw_text:
                parts.append(
                    self._apply_basic_formula_heuristics(
                        raw_text
                    )
                )
            else:
                parts.append(
                    "_No readable text_"
                )

        tables = extraction_result.get(
            "tables",
            []
        )

        if tables:
            parts.append(
                "\n\n## Tables\n"
            )

            for table in tables:
                page_num = table.get(
                    "page_number",
                    "?"
                )

                idx = table.get(
                    "table_index",
                    0
                )

                parts.append(
                    f"\n### Table {idx + 1} "
                    f"(Page {page_num})\n"
                )

                parts.append(
                    table.get(
                        "markdown",
                        ""
                    )
                )

        images = extraction_result.get(
            "images",
            []
        )

        if images:
            parts.append(
                "\n\n## Images\n"
            )

            for img in images:
                path = img.get(
                    "path",
                    ""
                )

                filename = img.get(
                    "filename",
                    "image"
                )

                page_num = img.get(
                    "page_number",
                    "?"
                )

                parts.append(
                    f"![{filename}]"
                    f"({path}) "
                    f"(Page {page_num})"
                )

        return "\n".join(parts)

    # ------------------------------------------------ #
    # Formula heuristic                                #
    # ------------------------------------------------ #

    def _apply_basic_formula_heuristics(
        self,
        text: str
    ) -> str:

        equation_line = re.compile(
            r"^([A-Za-zΑ-Ωα-ω_\s]+\s*=\s*[^\n]{3,})$",
            re.MULTILINE
        )

        def wrap_equation(m):
            expr = m.group(1).strip()

            if "$" in expr:
                return m.group(0)

            if re.fullmatch(
                r"[A-Za-z\s]+=\s*[A-Za-z\s]+",
                expr
            ):
                return m.group(0)

            return f"$$\n{expr}\n$$"

        return equation_line.sub(
            wrap_equation,
            text
        )

    # ------------------------------------------------ #
    # Metadata                                         #
    # ------------------------------------------------ #

    def add_metadata_section(
        self,
        markdown: str,
        metadata: Dict
    ) -> str:

        front_matter = (
            "---\n"
            f"title: "
            f"{metadata.get('title', 'Untitled')}\n"
            f"author: "
            f"{metadata.get('author', 'Unknown')}\n"
            f"pages: "
            f"{metadata.get('page_count', 0)}\n"
            "---\n\n"
        )

        return front_matter + markdown