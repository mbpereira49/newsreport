from __future__ import annotations

import html
from datetime import date

from daily_digest.config import PublicationConfig
from daily_digest.models import ModuleBlock, StoryCluster


def render_fallback_digest(
    publication: PublicationConfig,
    run_date: date,
    entries: list[dict],
    clusters: list[StoryCluster],
    modules: list[ModuleBlock],
) -> str:
    source_catalog = {source.id: source for cluster in clusters for source in cluster.source_refs()}
    lines: list[str] = [
        f"# {publication.name}",
        "",
        f"*{run_date.strftime('%A, %B %-d, %Y')}*",
        "",
    ]

    non_empty_modules = [module for module in modules if _module_has_content(module)]
    for module in non_empty_modules:
        lines.extend(_render_module(module))
        lines.append("")

    lines.append("## Today's Brief")
    lines.append("")
    for entry in entries:
        lines.append(f"### {entry.get('headline', 'Untitled')}")
        if entry.get("dek"):
            lines.append(f"*{entry['dek']}*")
            lines.append("")
        if entry.get("body"):
            lines.append(str(entry["body"]))
            lines.append("")
        if entry.get("why_it_matters"):
            lines.append(f"**Why it matters:** {entry['why_it_matters']}")
            lines.append("")

        source_links = []
        for source_id in entry.get("source_ids", []):
            source = source_catalog.get(source_id)
            if source:
                source_links.append(f"[{source.publisher}]({source.url})")
        if source_links:
            lines.append("Sources: " + ", ".join(source_links))
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def render_html_digest(
    publication: PublicationConfig,
    run_date: date,
    entries: list[dict],
    clusters: list[StoryCluster],
    modules: list[ModuleBlock],
) -> str:
    source_catalog = {source.id: source for cluster in clusters for source in cluster.source_refs()}
    visible_modules = [module for module in modules if _module_has_content(module)]
    lead_entry = entries[0] if entries else None
    secondary_entries = entries[1:]

    html_parts = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_escape(publication.name)} - {run_date.isoformat()}</title>",
        "<style>",
        NEWSPAPER_CSS,
        "</style>",
        "</head>",
        "<body>",
        '<main class="page">',
        _render_html_masthead(publication, run_date),
    ]

    if visible_modules:
        html_parts.append('<aside class="brief-strip" aria-label="Daily notes">')
        for module in visible_modules:
            html_parts.append(_render_html_module(module))
        html_parts.append("</aside>")

    if lead_entry:
        html_parts.append(_render_html_lead(lead_entry, source_catalog))

    if secondary_entries:
        html_parts.append('<section class="story-grid" aria-label="Digest stories">')
        for index, entry in enumerate(secondary_entries, start=2):
            html_parts.append(_render_html_story(entry, source_catalog, index))
        html_parts.append("</section>")

    html_parts.extend(
        [
        '<footer class="edition-footer">',
        f"{_escape(publication.name)} · {_escape(run_date.strftime('%B %-d, %Y'))}",
            "</footer>",
            "</main>",
            "</body>",
            "</html>",
        ]
    )
    return "\n".join(html_parts) + "\n"


def _module_has_content(module: ModuleBlock) -> bool:
    if module.kind == "calendar_json":
        return bool(module.content.get("events"))
    if module.kind == "text_file":
        return bool(str(module.content.get("text", "")).strip())
    return bool(module.content)


def _render_module(module: ModuleBlock) -> list[str]:
    lines = [f"## {module.title}", ""]
    if module.kind == "calendar_json":
        events = module.content.get("events", [])
        for event in events:
            when = event.get("time") or event.get("start") or event.get("date", "")
            summary = event.get("title") or event.get("summary") or "Untitled event"
            lines.append(f"- {when}: {summary}")
    elif module.kind == "text_file":
        lines.append(str(module.content.get("text", "")).strip())
    else:
        lines.append(str(module.content))
    return lines


def _render_html_masthead(publication: PublicationConfig, run_date: date) -> str:
    date_label = run_date.strftime("%A, %B %-d, %Y")
    timezone_label = publication.timezone.replace("_", " ")
    return (
        '<header class="masthead">'
        '<div class="masthead-rule"></div>'
        '<p class="kicker">Personal edition</p>'
        f"<h1>{_escape(publication.name)}</h1>"
        f'<p class="dateline">{_escape(date_label)} · {_escape(timezone_label)}</p>'
        '<div class="masthead-rule heavy"></div>'
        "</header>"
    )


def _render_html_module(module: ModuleBlock) -> str:
    title = _escape(module.title)
    if module.kind == "calendar_json":
        events = module.content.get("events", [])
        rows = []
        for event in events:
            when = _escape(str(event.get("time") or event.get("start") or event.get("date", "")))
            summary = _escape(str(event.get("title") or event.get("summary") or "Untitled event"))
            rows.append(f"<li><span>{when}</span>{summary}</li>")
        body = "<ul>" + "".join(rows) + "</ul>"
    elif module.kind == "text_file":
        body = "".join(f"<p>{_escape(paragraph)}</p>" for paragraph in _paragraphs(str(module.content.get("text", ""))))
    else:
        body = f"<p>{_escape(str(module.content))}</p>"
    return f'<section class="brief-card"><h2>{title}</h2>{body}</section>'


def _render_html_lead(entry: dict, source_catalog: dict) -> str:
    dek = str(entry.get("dek", "")).strip()
    body = str(entry.get("body", "")).strip()
    dek_html = f'<p class="dek">{_escape(dek)}</p>' if dek else ""
    body_html = f'<div class="body-copy">{_html_paragraphs(body)}</div>' if body else ""
    lower_class = "lead-lower" if body else "lead-lower meta-only"
    return (
        '<section class="lead-story">'
        '<div class="section-label">Lead story</div>'
        f"<h2>{_escape(str(entry.get('headline', 'Untitled')))}</h2>"
        f"{dek_html}"
        f'<div class="{lower_class}">'
        f"{body_html}"
        '<div class="story-meta">'
        f"{_render_why(entry)}"
        f"{_render_html_sources(entry, source_catalog)}"
        "</div>"
        "</div>"
        "</section>"
    )


def _render_html_story(entry: dict, source_catalog: dict, index: int) -> str:
    dek = str(entry.get("dek", "")).strip()
    body = str(entry.get("body", "")).strip()
    dek_html = f'<p class="dek">{_escape(dek)}</p>' if dek else ""
    body_html = f'<div class="body-copy">{_html_paragraphs(body)}</div>' if body else ""
    return (
        '<article class="story-card">'
        f'<div class="story-number">{index:02d}</div>'
        f"<h2>{_escape(str(entry.get('headline', 'Untitled')))}</h2>"
        f"{dek_html}"
        f"{body_html}"
        f"{_render_why(entry)}"
        f"{_render_html_sources(entry, source_catalog)}"
        "</article>"
    )


def _render_why(entry: dict) -> str:
    why = str(entry.get("why_it_matters", "")).strip()
    if not why:
        return ""
    return f'<p class="why"><strong>Why it matters:</strong> {_escape(why)}</p>'


def _render_html_sources(entry: dict, source_catalog: dict) -> str:
    links: list[str] = []
    seen: set[tuple[str, str]] = set()
    for source_id in entry.get("source_ids", []):
        source = source_catalog.get(source_id)
        if not source:
            continue
        key = (source.publisher, source.url)
        if key in seen:
            continue
        seen.add(key)
        links.append(
            f'<a href="{_escape_attr(source.url)}" target="_blank" rel="noreferrer">{_escape(source.publisher)}</a>'
        )
    if not links:
        return ""
    return '<p class="sources">Sources: ' + " · ".join(links) + "</p>"


def _html_paragraphs(value: str) -> str:
    paragraphs = _paragraphs(value)
    if not paragraphs:
        return ""
    return "".join(f"<p>{_escape(paragraph)}</p>" for paragraph in paragraphs)


def _paragraphs(value: str) -> list[str]:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    if "\n\n" in normalized:
        return [part.strip() for part in normalized.split("\n\n") if part.strip()]
    return [part.strip() for part in normalized.split("\n") if part.strip()]


def _escape(value: str) -> str:
    return html.escape(value, quote=False)


def _escape_attr(value: str) -> str:
    return html.escape(value, quote=True)


NEWSPAPER_CSS = """
:root {
  color-scheme: light;
  --ink: #121212;
  --muted: #555555;
  --line: #222222;
  --fine-line: #d9d9d9;
  --paper: #ffffff;
  --paper-soft: #f7f7f7;
  --wash: #f2f2f2;
  --accent: #1f4e79;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  background: #ffffff;
  color: var(--ink);
  font-family: "Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
  line-height: 1.5;
}

.page {
  width: min(1180px, calc(100% - 32px));
  margin: 18px auto 32px;
  padding: 24px 44px 40px;
  background: var(--paper);
  border: 0;
  box-shadow: none;
}

.masthead {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 8px 18px;
  align-items: center;
  text-align: center;
}

.masthead-rule {
  grid-column: 1 / -1;
  display: block;
  border-top: 1px solid var(--line);
}

.masthead-rule.heavy {
  border-top: 3px double var(--line);
}

.kicker,
.dateline,
.sources,
.story-number,
.section-label,
.edition-footer {
  color: var(--muted);
  letter-spacing: 0;
}

.kicker {
  grid-column: 1;
  grid-row: 2;
  justify-self: start;
  margin: 0;
  color: var(--muted);
  font-family: "Franklin Gothic Medium", "Arial Narrow", Arial, Helvetica, sans-serif;
  font-size: 0.72rem;
  font-weight: 700;
  text-transform: uppercase;
}

.masthead h1 {
  grid-column: 1 / -1;
  grid-row: 3;
  margin: 0 auto;
  font-family: "Hoefler Text", "Bodoni 72", Didot, Baskerville, Georgia, serif;
  font-size: 4.7rem;
  line-height: 0.92;
  font-weight: 800;
  letter-spacing: 0;
}

.dateline {
  grid-column: 3;
  grid-row: 2;
  justify-self: end;
  margin: 0;
  padding: 0;
  background: transparent;
  border: 0;
  border-radius: 0;
  font-family: "Franklin Gothic Medium", "Arial Narrow", Arial, Helvetica, sans-serif;
  font-size: 0.76rem;
  text-transform: uppercase;
  white-space: nowrap;
}

.brief-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0;
  margin: 16px 0 18px;
  padding: 8px 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}

.brief-card {
  min-width: 0;
  padding: 4px 14px;
  background: transparent;
  border-left: 1px solid var(--fine-line);
  border-radius: 0;
}

.brief-card:first-child {
  border-left: 0;
}

.brief-card h2 {
  margin: 0 0 5px;
  color: var(--ink);
  font-family: "Franklin Gothic Medium", "Arial Narrow", Arial, Helvetica, sans-serif;
  font-size: 0.78rem;
  font-weight: 800;
  text-transform: uppercase;
}

.brief-card p,
.brief-card li {
  margin: 0;
  font-size: 0.9rem;
  line-height: 1.35;
}

.brief-card p + p,
.brief-card li + li {
  margin-top: 8px;
}

.brief-card ul {
  margin: 0;
  padding-left: 0;
  list-style: none;
}

.brief-card li span {
  display: inline-block;
  min-width: 4.5rem;
  color: var(--accent);
  font-family: "Franklin Gothic Medium", "Arial Narrow", Arial, Helvetica, sans-serif;
  font-size: 0.8rem;
  font-weight: 700;
}

.lead-story {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(220px, 310px);
  gap: 18px 26px;
  margin-bottom: 20px;
  padding: 18px 0 20px;
  border-top: 3px solid var(--line);
  border-bottom: 1px solid var(--line);
  color: var(--ink);
}

.section-label,
.story-number {
  font-weight: 700;
  text-transform: uppercase;
}

.section-label {
  grid-column: 1 / -1;
  width: auto;
  padding: 0 0 4px;
  border-bottom: 1px solid var(--fine-line);
  color: var(--accent);
  font-family: "Franklin Gothic Medium", "Arial Narrow", Arial, Helvetica, sans-serif;
  font-size: 0.72rem;
}

.lead-story h2 {
  grid-column: 1 / -1;
  margin: 0;
  font-size: 3rem;
  line-height: 1.02;
  font-weight: 700;
  letter-spacing: 0;
}

.dek {
  margin: 4px 0 8px;
  color: #312e2a;
  font-size: 1.08rem;
  font-style: italic;
  font-weight: 400;
}

.lead-story .dek {
  grid-column: 1 / -1;
  max-width: 820px;
  color: #312e2a;
  font-size: 1.16rem;
}

.lead-lower {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(220px, 300px);
  gap: 28px;
  align-items: start;
  margin-top: 4px;
}

.lead-lower.meta-only {
  grid-template-columns: minmax(220px, 340px);
}

.story-meta {
  padding: 0 0 0 14px;
  background: transparent;
  border-left: 1px solid var(--fine-line);
  border-radius: 0;
  color: var(--ink);
}

.body-copy p {
  margin: 0 0 0.85rem;
}

.lead-story .body-copy {
  color: var(--ink);
}

.story-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0 28px;
}

.story-card {
  display: block;
  min-width: 0;
  width: 100%;
  margin: 0 0 18px;
  padding: 0 0 16px;
  background: transparent;
  border-bottom: 1px solid var(--fine-line);
  border-radius: 0;
  break-inside: avoid;
}

.story-card:not(:nth-child(3n+1)) {
  padding-left: 18px;
  border-left: 1px solid var(--fine-line);
}

.story-number {
  width: auto;
  margin-bottom: 7px;
  padding: 0;
  background: transparent;
  border-radius: 0;
  color: var(--accent);
  font-family: "Franklin Gothic Medium", "Arial Narrow", Arial, Helvetica, sans-serif;
  font-size: 0.72rem;
}

.story-card h2 {
  margin: 0;
  font-size: 1.36rem;
  line-height: 1.12;
  font-weight: 700;
}

.story-card .dek {
  font-size: 0.98rem;
  margin-top: 8px;
}

.why {
  margin: 12px 0 0;
  padding: 8px 0 0;
  background: transparent;
  border-top: 1px solid var(--fine-line);
  border-left: 0;
  border-radius: 0;
  font-size: 0.95rem;
}

.lead-story .why {
  background: transparent;
}

.sources {
  margin: 12px 0 0;
  font-size: 0.78rem;
}

.lead-story .sources {
  color: var(--muted);
}

a {
  color: var(--accent);
  text-decoration: none;
  border-bottom: 1px solid rgba(31, 78, 121, 0.35);
}

.lead-story a {
  color: var(--accent);
  border-bottom-color: rgba(31, 78, 121, 0.35);
}

.edition-footer {
  margin-top: 30px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
  font-size: 0.78rem;
  text-align: center;
}

@media (max-width: 860px) {
  .page {
    width: 100%;
    margin: 0;
    padding: 20px 18px 34px;
    border-radius: 0;
    border-left: 0;
    border-right: 0;
    box-shadow: none;
  }

  .masthead {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .kicker,
  .masthead h1,
  .dateline {
    grid-column: 1;
    grid-row: auto;
  }

  .masthead h1 {
    font-size: 3rem;
  }

  .dateline {
    justify-self: start;
    white-space: normal;
  }

  .lead-story {
    grid-template-columns: 1fr;
    padding: 16px 0 18px;
  }

  .lead-story h2 {
    font-size: 2.1rem;
  }

  .lead-lower,
  .story-grid {
    grid-template-columns: 1fr;
  }

  .story-grid {
    grid-template-columns: 1fr;
  }

  .story-meta {
    padding-left: 0;
    border-left: 0;
    border-top: 1px solid var(--fine-line);
    padding-top: 12px;
  }

  .story-card:not(:nth-child(3n+1)) {
    padding-left: 0;
    border-left: 0;
  }
}

@media print {
  body {
    background: #fff;
  }

  .page {
    width: auto;
    margin: 0;
    padding: 0;
    border: 0;
    box-shadow: none;
  }

  a {
    color: inherit;
    border-bottom: 0;
  }
}
""".strip()
