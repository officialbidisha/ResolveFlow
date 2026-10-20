"""Render INFRA_FROM_SCRATCH.md to PDF via headless Chrome.

Usage: python3 build_infra_pdf.py <input.md> <output.pdf>
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

CSS = """
@page {
  size: A4;
  margin: 18mm 16mm 18mm 16mm;
  @bottom-center { content: counter(page); font: 9pt -apple-system, Helvetica, sans-serif; color: #888; }
}
:root { --ink:#1d1f24; --muted:#5b6170; --accent:#6b3fa0; --line:#d9dce3; --soft:#f5f3fa; --code:#f4f5f7; }
html { font-size: 10.4pt; }
body { font-family: -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif; color: var(--ink);
       line-height: 1.5; background: #fff; }
h1 { font-size: 21pt; color: var(--accent); margin: 0 0 6pt; break-before: page; }
h1:first-of-type { break-before: avoid; font-size: 24pt; }
h2 { font-size: 15pt; color: var(--accent); border-bottom: 1.5pt solid var(--accent);
     padding-bottom: 3pt; margin-top: 18pt; break-after: avoid; }
h2.newpage { break-before: page; margin-top: 0; }
h3 { font-size: 11.6pt; margin: 14pt 0 4pt; break-after: avoid; }
p, li { orphans: 3; widows: 3; }
a { color: var(--accent); text-decoration: none; }
code { font-family: Menlo, "SF Mono", Consolas, monospace; font-size: 8.8pt; background: var(--code);
       padding: 0.5pt 3pt; border-radius: 3pt; }
pre { background: var(--code); border: 0.6pt solid var(--line); border-radius: 4pt; padding: 7pt 9pt;
      font-size: 7.6pt; line-height: 1.38; white-space: pre-wrap; word-break: break-word; break-inside: avoid; }
pre code { background: none; padding: 0; font-size: inherit; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 10pt; font-size: 9pt; break-inside: auto; }
th, td { border: 0.6pt solid var(--line); padding: 4pt 6pt; vertical-align: top; text-align: left; }
th { background: var(--soft); }
tr { break-inside: avoid; }
blockquote { margin: 8pt 0; padding: 7pt 11pt; background: var(--soft); border-left: 3pt solid var(--accent);
             border-radius: 0 4pt 4pt 0; break-inside: avoid; }
blockquote p { margin: 3pt 0; }
hr { border: none; border-top: 0.6pt solid var(--line); margin: 14pt 0; }
.toc { border: 0.6pt solid var(--line); border-radius: 4pt; padding: 8pt 14pt; margin: 10pt 0; font-size: 9.6pt; }
.toc ul { list-style: none; padding-left: 12pt; margin: 2pt 0; }
.toc > ul { padding-left: 0; }
.toc li { margin: 1pt 0; }
"""


def main(src: Path, out: Path) -> None:
    text = src.read_text()
    # Table of contents right after the subtitle line.
    text = text.replace("## How to use this document", "## Contents\n\n[TOC]\n\n## How to use this document", 1)
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
        extension_configs={"toc": {"toc_depth": "1-2", "title": ""}},
    )
    body = md.convert(text)
    # Start chapters and grill rounds on a new page.
    body = re.sub(r'<h2 id="(chapter|round)', r'<h2 class="newpage" id="\1', body)
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Deployment, CI/CD, Observability &amp; Tooling — From Scratch</title>
<style>{CSS}</style></head><body>{body}</body></html>"""
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "doc.html"
        page.write_text(html)
        subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
             "--generate-pdf-document-outline", f"--print-to-pdf={out}", page.as_uri()],
            check=True, capture_output=True,
        )
    print(f"wrote {out}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
