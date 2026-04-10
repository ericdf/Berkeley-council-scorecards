"""
methodology_pdf.py
==================
Renders METHODOLOGY.md → scores/pdfs/methodology.pdf

Usage:
    python methodology_pdf.py
"""

import os
import sys

import markdown
from weasyprint import HTML, CSS

HERE     = os.path.dirname(__file__)
SRC      = os.path.join(HERE, "METHODOLOGY.md")
PDF_DIR  = os.path.join(HERE, "scores", "pdfs")
OUT_PDF  = os.path.join(PDF_DIR, "methodology.pdf")

CSS_STYLE = """
@page {
    size: letter;
    margin: 1in 1in 1in 1in;
    @bottom-center {
        content: "Berkeley City Council Scorecard · Methodology · " counter(page) " of " counter(pages);
        font-size: 9pt;
        color: #888;
        font-family: 'Helvetica Neue', sans-serif;
    }
}

body {
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 10.5pt;
    line-height: 1.55;
    color: #1a1a1a;
    max-width: 100%;
}

h1 {
    font-size: 20pt;
    font-weight: 700;
    color: #1a1a1a;
    margin-bottom: 4pt;
    border-bottom: 2px solid #c0392b;
    padding-bottom: 6pt;
}

h2 {
    font-size: 14pt;
    font-weight: 700;
    color: #c0392b;
    margin-top: 20pt;
    margin-bottom: 6pt;
    border-bottom: 1px solid #e0e0e0;
    padding-bottom: 3pt;
    page-break-after: avoid;
}

h3 {
    font-size: 11.5pt;
    font-weight: 700;
    color: #2c3e50;
    margin-top: 14pt;
    margin-bottom: 4pt;
    page-break-after: avoid;
}

h4 {
    font-size: 10.5pt;
    font-weight: 700;
    color: #555;
    margin-top: 10pt;
    margin-bottom: 3pt;
    page-break-after: avoid;
}

p {
    margin: 0 0 8pt 0;
}

ul, ol {
    margin: 4pt 0 8pt 0;
    padding-left: 20pt;
}

li {
    margin-bottom: 3pt;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin: 10pt 0;
    font-size: 9.5pt;
    page-break-inside: avoid;
}

th {
    background: #2c3e50;
    color: #fff;
    font-weight: 600;
    padding: 5pt 8pt;
    text-align: left;
    border: 1px solid #2c3e50;
}

td {
    padding: 4pt 8pt;
    border: 1px solid #ddd;
    vertical-align: top;
}

tr:nth-child(even) td {
    background: #f8f8f8;
}

code {
    font-family: 'Courier New', monospace;
    font-size: 9pt;
    background: #f0f0f0;
    padding: 1pt 3pt;
    border-radius: 2pt;
}

hr {
    border: none;
    border-top: 1px solid #ddd;
    margin: 16pt 0;
}

strong {
    color: #1a1a1a;
}

blockquote {
    border-left: 3px solid #c0392b;
    margin: 8pt 0 8pt 0;
    padding: 4pt 12pt;
    background: #fdf5f5;
    color: #555;
    font-style: italic;
}

.version-line {
    font-size: 9pt;
    color: #888;
    margin-bottom: 16pt;
}
"""


def build_html(md_text: str) -> str:
    body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "nl2br"],
    )
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Berkeley Council Scorecard — Methodology</title></head>
<body>
{body}
</body>
</html>"""


def main():
    if not os.path.exists(SRC):
        print(f"ERROR: {SRC} not found", file=sys.stderr)
        sys.exit(1)

    os.makedirs(PDF_DIR, exist_ok=True)

    with open(SRC, encoding="utf-8") as f:
        md_text = f.read()

    html = build_html(md_text)
    HTML(string=html, base_url=HERE).write_pdf(
        OUT_PDF,
        stylesheets=[CSS(string=CSS_STYLE)],
    )
    print(f"Methodology PDF → {OUT_PDF}")


if __name__ == "__main__":
    main()
