from __future__ import annotations

import re


_BULLET = re.compile(r"^\s*(?:[-*•]|\d+[.)]|[A-Z][.)])\s+")
_HEADING = re.compile(r"^[A-Z0-9][A-Z0-9 /&(),.'-]{2,80}:?$")
_LABEL_VALUE = re.compile(r"^[A-Za-z][A-Za-z0-9 /()'-]{1,45}:\s*\S")


def normalize_extracted_text(text: str) -> str:
    """Reconstruct paragraphs while preserving headings, bullets, labels and table-like rows."""
    raw_lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    output: list[str] = []
    paragraph = ""

    def flush() -> None:
        nonlocal paragraph
        if paragraph.strip():
            output.append(re.sub(r"[ \t]+", " ", paragraph).strip())
        paragraph = ""

    for original in raw_lines:
        line = re.sub(r"[ \t]+", " ", original).strip()
        if not line:
            flush()
            if output and output[-1] != "":
                output.append("")
            continue
        table_like = "\t" in original or len(re.findall(r"\s{2,}", original)) >= 2
        structural = bool(_BULLET.match(line) or _HEADING.match(line) or _LABEL_VALUE.match(line) or table_like)
        if structural:
            flush()
            output.append(line)
            continue
        if not paragraph:
            paragraph = line
            continue
        if paragraph.endswith("-") and re.match(r"^[a-z]", line):
            paragraph = paragraph[:-1] + line
        elif paragraph.endswith((".", "!", "?", ":", ";")):
            flush()
            paragraph = line
        else:
            paragraph += " " + line
    flush()
    while output and output[-1] == "":
        output.pop()
    return "\n".join(output)


def text_blocks(text: str) -> list[dict[str, object]]:
    """Return stable line blocks when the extractor cannot provide geometric boxes."""
    return [
        {"order": index, "text": line, "bbox": None}
        for index, line in enumerate(text.splitlines(), start=1)
        if line.strip()
    ]
