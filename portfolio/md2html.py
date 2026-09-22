#!/usr/bin/env python3
"""Convert portfolio_etfs.md to a mobile-optimized standalone HTML file.

Usage: uv run python portfolio/md2html.py
"""
from __future__ import annotations

import html
import re
from pathlib import Path

HERE = Path(__file__).parent
SRC = HERE / "portfolio_etfs.md"
DST = HERE / "portfolio_etfs.html"

CSS = """
:root {
  color-scheme: light dark;
  --bg: #ffffff;
  --fg: #1a1d21;
  --muted: #5c6570;
  --accent: #0b5fff;
  --accent-soft: #e8f0ff;
  --border: #dfe3e8;
  --code-bg: #f2f4f7;
  --thead-bg: #f7f8fa;
  --warn-bg: #fff8e6;
  --warn-border: #f0d48a;
  --ok-bg: #e9f7ef;
  --ok-border: #9fd6b5;
  --card: #ffffff;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #12151a;
    --fg: #e6e9ee;
    --muted: #9aa3ad;
    --accent: #6ea8ff;
    --accent-soft: #1b2a4a;
    --border: #2a3038;
    --code-bg: #1c2128;
    --thead-bg: #1a1f26;
    --warn-bg: #2a2416;
    --warn-border: #6b5a2a;
    --ok-bg: #14251c;
    --ok-border: #2f5c44;
    --card: #171b21;
  }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  padding: 0 0 4rem;
  background: var(--bg);
  color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, sans-serif;
  font-size: 16px;
  line-height: 1.55;
  overflow-wrap: break-word;
}
.wrap {
  max-width: 46rem;
  margin: 0 auto;
  padding: 1rem 1rem 2rem;
}
@media (min-width: 600px) { .wrap { padding: 1.5rem 1.5rem 3rem; } }

header.hero {
  padding: 1.25rem 0 0.75rem;
  border-bottom: 3px solid var(--accent);
  margin-bottom: 1.25rem;
}
header.hero h1 { margin: 0 0 0.35rem; font-size: 1.55rem; line-height: 1.25; }
@media (min-width: 600px) { header.hero h1 { font-size: 1.9rem; } }
header.hero .sub { color: var(--muted); font-size: 0.92rem; }

h1, h2, h3, h4 { line-height: 1.3; font-weight: 700; }
h1 { font-size: 1.45rem; margin: 2rem 0 0.75rem; }
h2 {
  font-size: 1.2rem;
  margin: 2.25rem 0 0.75rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border);
}
h3 { font-size: 1.05rem; margin: 1.5rem 0 0.5rem; color: var(--accent); }

p { margin: 0.75rem 0; }
strong { font-weight: 700; }
em { font-style: italic; color: var(--muted); }

a { color: var(--accent); text-decoration: underline; word-break: break-all; }
a:hover { background: var(--accent-soft); }

code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 0.86em;
  background: var(--code-bg);
  padding: 0.1em 0.35em;
  border-radius: 4px;
}
pre {
  background: var(--code-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.75rem;
  overflow-x: auto;
  font-size: 0.82rem;
}
pre code { background: none; padding: 0; }

ul, ol { padding-left: 1.35rem; margin: 0.75rem 0; }
li { margin: 0.4rem 0; }
li::marker { color: var(--accent); }

hr {
  border: none;
  border-top: 1px solid var(--border);
  margin: 2rem 0;
}

/* ---- Tables: horizontal scroll on mobile ---- */
.tbl-wrap {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  margin: 1rem 0 1.25rem;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--card);
}
.tbl-wrap::-webkit-scrollbar { height: 6px; }
.tbl-wrap::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
table { border-collapse: collapse; width: 100%; min-width: max-content; font-size: 0.88rem; }
th, td {
  padding: 0.55rem 0.7rem;
  text-align: left;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
  vertical-align: top;
}
th {
  background: var(--thead-bg);
  font-weight: 700;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: var(--muted);
  position: sticky;
  top: 0;
}
tbody tr:last-child td { border-bottom: none; }
tbody tr:nth-child(even) { background: color-mix(in srgb, var(--thead-bg) 45%, transparent); }
/* let wide cells wrap where helpful without forcing min-width blowout on first col */
td:first-child, th:first-child { white-space: normal; min-width: 9.5rem; }

.scroll-hint {
  font-size: 0.75rem;
  color: var(--muted);
  margin: -0.85rem 0 1rem;
  display: block;
}
@media (min-width: 720px) { .scroll-hint { display: none; } }

.callout {
  border-left: 4px solid var(--accent);
  background: var(--accent-soft);
  border-radius: 0 8px 8px 0;
  padding: 0.75rem 1rem;
  margin: 1rem 0;
}
.callout.warn { border-left-color: var(--warn-border); background: var(--warn-bg); }
.callout.ok { border-left-color: var(--ok-border); background: var(--ok-bg); }
.callout p:first-child { margin-top: 0; }
.callout p:last-child { margin-bottom: 0; }

.tag {
  display: inline-block;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  background: var(--accent);
  color: #fff;
  border-radius: 999px;
  padding: 0.15rem 0.6rem;
  margin-right: 0.35rem;
}

nav.toc {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0.9rem 1rem;
  margin: 1.25rem 0;
}
nav.toc .toc-title {
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--muted);
  margin-bottom: 0.5rem;
}
nav.toc ol { list-style: none; padding: 0; margin: 0; columns: 1; }
nav.toc li { margin: 0.3rem 0; }
nav.toc a { text-decoration: none; font-size: 0.95rem; }
nav.toc a:hover { text-decoration: underline; }
@media (min-width: 560px) { nav.toc ol { columns: 2; column-gap: 1.5rem; } }

.num-cards {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 0.6rem;
  margin: 1rem 0;
}
@media (min-width: 560px) { .num-cards { grid-template-columns: repeat(4, 1fr); } }
.num-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0.7rem 0.75rem;
  text-align: center;
}
.num-card .v { font-size: 1.25rem; font-weight: 800; color: var(--accent); display: block; }
.num-card .k { font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }

footer.meta {
  margin-top: 3rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border);
  color: var(--muted);
  font-size: 0.82rem;
}
"""


def inline(text: str) -> str:
    """Escape HTML then apply inline markdown."""
    s = html.escape(text, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    # bare URLs
    s = re.sub(
        r"(?<![\"=>])\b(https?://[^\s<]+[^\s<.,;:)\]])",
        r'<a href="\1" rel="noopener">\1</a>',
        s,
    )
    return s


def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def convert(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    first_h1 = True
    toc_items: list[tuple[str, str]] = []
    n = len(lines)

    # pre-scan headings for TOC (skip the very first title)
    h_count = 0
    for ln in lines:
        m = re.match(r"^(#{1,3})\s+(.*)$", ln)
        if m:
            h_count += 1
            if h_count > 1:
                toc_items.append((m.group(2), slug(m.group(2))))

    toc_html = ""
    if toc_items:
        parts = [f'<li><a href="#{s}">{inline(t)}</a></li>' for t, s in toc_items]
        toc_html = (
            '<nav class="toc"><div class="toc-title">Contents</div><ol>'
            + "".join(parts)
            + "</ol></nav>"
        )
        out.append(toc_html)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # blank
        if not stripped:
            i += 1
            continue

        # hr
        if stripped == "---":
            out.append("<hr>")
            i += 1
            continue

        # heading
        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            text = m.group(2)
            sid = slug(text)
            if level == 1 and first_h1:
                first_h1 = False
                # hero handled separately below from original H1; skip duplicate
                # Actually render as section H1 after hero — keep it as h1 without id clash
                out.append(f'<h1 id="{sid}">{inline(text)}</h1>')
            else:
                out.append(f'<h{level} id="{sid}">{inline(text)}</h{level}>')
            i += 1
            continue

        # table
        if stripped.startswith("|") and i + 1 < n and re.match(r"^\|[\s:|-]+\|", lines[i + 1].strip()):
            header = split_row(stripped)
            i += 2  # skip separator
            rows: list[list[str]] = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i].strip()))
                i += 1
            ths = "".join(f"<th>{inline(c)}</th>" for c in header)
            body_rows = []
            for r in rows:
                # pad/truncate to header length
                if len(r) < len(header):
                    r = r + [""] * (len(header) - len(r))
                tds = "".join(f"<td>{inline(c)}</td>" for c in r[: len(header)])
                body_rows.append(f"<tr>{tds}</tr>")
            table = (
                f'<div class="tbl-wrap"><table><thead><tr>{ths}</tr></thead>'
                f'<tbody>{"".join(body_rows)}</tbody></table></div>'
                '<span class="scroll-hint">↔ scroll table sideways</span>'
            )
            out.append(table)
            continue

        # ordered list
        if re.match(r"^\d+\.\s+", stripped):
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i].strip()):
                item = re.sub(r"^\d+\.\s+", "", lines[i].strip())
                items.append(f"<li>{inline(item)}</li>")
                i += 1
            out.append("<ol>" + "".join(items) + "</ol>")
            continue

        # unordered list
        if stripped.startswith("- "):
            items = []
            while i < n and lines[i].strip().startswith("- "):
                item = lines[i].strip()[2:]
                items.append(f"<li>{inline(item)}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue

        # paragraph: gather until blank/structure
        para = [stripped]
        i += 1
        while i < n:
            nxt = lines[i].strip()
            if (
                not nxt
                or nxt == "---"
                or nxt.startswith("#")
                or nxt.startswith("|")
                or nxt.startswith("- ")
                or re.match(r"^\d+\.\s+", nxt)
            ):
                break
            para.append(nxt)
            i += 1
        out.append(f"<p>{inline(' '.join(para))}</p>")

    return "\n".join(out)


def slug(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    s = re.sub(r"[\s_]+", "-", s).strip("-")
    return s or "sec"


def build_kpi_cards(body_html: str) -> str:
    """Insert a KPI card row after the review h1 if markers present."""
    return body_html


def main() -> None:
    md = SRC.read_text(encoding="utf-8")

    # Split hero title from body: first H1 + following intro paragraph
    lines = md.splitlines()
    assert lines[0].startswith("# ")
    title = lines[0][2:].strip()

    # find second H1 (the review section)
    review_idx = next(
        (j for j, ln in enumerate(lines) if j > 0 and ln.startswith("# Full portfolio review")),
        None,
    )

    # Hero = first H1 + text until first table (the holdings blurb)
    # Body = everything from first table onward, converted
    # Simpler: convert whole doc; extract first h1 as hero via post-process.
    body = convert(md)

    # Replace first <h1 ...>Portfolio ETFs</h1> + following content structure:
    # We'll craft hero manually and remove the first rendered H1.
    body = re.sub(r'<h1 id="portfolio-etfs">Portfolio ETFs</h1>', "", body, count=1)

    kpis = (
        '<div class="num-cards">'
        '<div class="num-card"><span class="v">77%</span><span class="k">Equity now</span></div>'
        '<div class="num-card"><span class="v">0%</span><span class="k">Bonds now</span></div>'
        '<div class="num-card"><span class="v">0.99</span><span class="k">Target Sharpe</span></div>'
        '<div class="num-card"><span class="v">0.94</span><span class="k">Target Sortino</span></div>'
        "</div>"
    )

    # Insert KPI cards right before the review H1
    review_h1 = re.search(r'<h1 id="full-portfolio-review[^"]*">', body)
    if review_h1:
        body = body[: review_h1.start()] + kpis + "\n" + body[review_h1.start() :]

    meta_m = re.search(r"Generated.*", md)
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#0b5fff" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#12151a" media="(prefers-color-scheme: dark)">
<meta name="description" content="Portfolio ETFs full review: allocation analysis, Sharpe/Sortino optimiser, LS vs Smart PAC, 3-pillar plan.">
<title>Portfolio ETFs — Full Review</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="hero">
  <div><span class="tag">Review</span><span class="tag">2026-09-22</span></div>
  <h1>{html.escape(title)}</h1>
  <p class="sub">Full review: 3-pillar allocation · Sharpe/Sortino optimum · LS vs Smart PAC · three-bucket plan</p>
</header>
<main>
{body}
</main>
<footer class="meta">
  Source: <code>portfolio/portfolio_etfs.md</code> · engine <code>backtesting/portfolio_risk_reward.py</code> ·
  124 tests passing · numbers are backtest medians, not guarantees.
</footer>
</div>
</body>
</html>
"""
    DST.write_text(page, encoding="utf-8")
    print(f"wrote {DST} ({DST.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
