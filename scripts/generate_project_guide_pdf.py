from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"
MARKDOWN_PATH = DOCS_DIR / "FULL_PROJECT_GUIDE.md"
PDF_PATH = DOCS_DIR / "FULL_PROJECT_GUIDE.pdf"

PAGE_WIDTH = 612
PAGE_HEIGHT = 792
MARGIN_X = 48
MARGIN_Y = 48
BODY_FONT_SIZE = 10
TITLE_FONT_SIZE = 20
HEADER_FONT_SIZE = 14
MONO_FONT_SIZE = 8.5
LINE_HEIGHT = 13


def _escape_pdf_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", "")
    )


class PDFPage:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def text(self, x: float, y: float, value: str, font: str, size: float) -> None:
        escaped = _escape_pdf_text(value)
        self.commands.append(
            f"BT /{font} {size:.2f} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm ({escaped}) Tj ET"
        )

    def stream(self) -> bytes:
        return "\n".join(self.commands).encode("latin-1", "replace")


class PDFBuilder:
    def __init__(self) -> None:
        self.pages: list[bytes] = []

    def add_page(self, page: PDFPage) -> None:
        self.pages.append(page.stream())

    def write(self, destination: Path) -> None:
        font_defs = {
            "F1": b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            "F2": b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
            "F3": b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
        }

        objects: dict[int, bytes] = {}
        next_id = 1

        def reserve() -> int:
            nonlocal next_id
            object_id = next_id
            next_id += 1
            return object_id

        def set_object(object_id: int, data: bytes) -> None:
            objects[object_id] = data

        pages_id = reserve()
        font_ids = {name: reserve() for name in font_defs}
        for name, font_id in font_ids.items():
            set_object(font_id, font_defs[name])

        page_ids: list[int] = []
        for page_stream in self.pages:
            content_id = reserve()
            set_object(
                content_id,
                b"<< /Length "
                + str(len(page_stream)).encode("ascii")
                + b" >>\nstream\n"
                + page_stream
                + b"\nendstream",
            )
            page_id = reserve()
            page_ids.append(page_id)
            resources = (
                f"<< /Font << /F1 {font_ids['F1']} 0 R /F2 {font_ids['F2']} 0 R "
                f"/F3 {font_ids['F3']} 0 R >> >>"
            ).encode("ascii")
            page_obj = (
                f"<< /Type /Page /Parent {pages_id} 0 R "
                f"/MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
                f"/Resources ".encode("ascii")
                + resources
                + f" /Contents {content_id} 0 R >>".encode("ascii")
            )
            set_object(page_id, page_obj)

        kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
        set_object(
            pages_id,
            f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>".encode(
                "ascii"
            ),
        )

        catalog_id = reserve()
        set_object(catalog_id, f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii"))

        output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets: list[int] = [0]
        for object_id in range(1, next_id):
            offsets.append(len(output))
            output.extend(f"{object_id} 0 obj\n".encode("ascii"))
            output.extend(objects[object_id])
            output.extend(b"\nendobj\n")

        xref_offset = len(output)
        output.extend(f"xref\n0 {next_id}\n".encode("ascii"))
        output.extend(b"0000000000 65535 f \n")
        for object_id in range(1, next_id):
            output.extend(f"{offsets[object_id]:010d} 00000 n \n".encode("ascii"))

        output.extend(
            (
                f"trailer\n<< /Size {next_id} /Root {catalog_id} 0 R >>\n"
                f"startxref\n{xref_offset}\n%%EOF\n"
            ).encode("ascii")
        )
        destination.write_bytes(output)


def wrap_text(text: str, max_chars: int) -> list[str]:
    if not text:
        return [""]

    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = word if not current else f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines or [text]


def render_markdown_to_pages(markdown: str) -> list[PDFPage]:
    pages: list[PDFPage] = []
    page = PDFPage()
    y = PAGE_HEIGHT - MARGIN_Y

    def ensure_space(lines_needed: int = 1) -> None:
        nonlocal page, y
        required = lines_needed * LINE_HEIGHT
        if y - required < MARGIN_Y:
            pages.append(page)
            page = PDFPage()
            y = PAGE_HEIGHT - MARGIN_Y

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.startswith("# "):
            ensure_space(3)
            page.text(MARGIN_X, y, line[2:].strip(), "F2", TITLE_FONT_SIZE)
            y -= 28
            continue

        if line.startswith("## "):
            ensure_space(2)
            page.text(MARGIN_X, y, line[3:].strip(), "F2", HEADER_FONT_SIZE)
            y -= 20
            continue

        if not line:
            y -= LINE_HEIGHT
            continue

        font = "F1"
        size = BODY_FONT_SIZE
        indent = 0
        max_chars = 90

        if line.startswith("- "):
            indent = 12
            max_chars = 84
        elif line[:2].isdigit() and line[1:3] == ". ":
            indent = 12
            max_chars = 84
        elif line.startswith("```"):
            font = "F3"
            size = MONO_FONT_SIZE
            max_chars = 96
        elif line.startswith("    "):
            font = "F3"
            size = MONO_FONT_SIZE
            max_chars = 92

        wrapped = wrap_text(line, max_chars=max_chars)
        ensure_space(len(wrapped) + 1)
        for segment in wrapped:
            page.text(MARGIN_X + indent, y, segment, font, size)
            y -= LINE_HEIGHT

    pages.append(page)
    return pages


def main() -> None:
    markdown = MARKDOWN_PATH.read_text(encoding="utf-8")
    builder = PDFBuilder()
    for page in render_markdown_to_pages(markdown):
        builder.add_page(page)
    builder.write(PDF_PATH)
    print(f"Created {PDF_PATH}")


if __name__ == "__main__":
    main()
