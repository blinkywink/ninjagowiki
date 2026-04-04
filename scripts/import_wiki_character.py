#!/usr/bin/env python3
"""
Fetch Fandom parse HTML for a character and its Overview/History/Relationships/Gallery tabs.
Writes characters/<slug>/index.html from a small template + embedded wiki fragments.
"""

from __future__ import annotations

import html as html_std
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

BASE = "https://ninjago.fandom.com"
API = f"{BASE}/api.php"
UA = "Mozilla/5.0 (compatible; NinjagoWikiLocalMirror/1.0)"


def api_parse(title: str) -> str:
    q = urllib.parse.urlencode(
        {
            "action": "parse",
            "page": title,
            "prop": "text",
            "format": "json",
            "disablelimitreport": "1",
        }
    )
    url = f"{API}?{q}"
    proc = subprocess.run(
        ["curl", "-sS", "-L", "-A", UA, "--max-time", "180", url],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or f"curl exit {proc.returncode}")
    data = json.loads(proc.stdout)
    if "error" in data:
        raise RuntimeError(str(data["error"]))
    return data["parse"]["text"]["*"]


def file_title_from_fandom_file_href(href: str) -> str | None:
    """Normalize File: title for MediaWiki API (spaces, quotes from URL encoding)."""
    m = re.search(r"ninjago\.fandom\.com/wiki/((?:File|file):[^#?]+)", href, re.I)
    if not m:
        return None
    path = urllib.parse.unquote(m.group(1))
    if path.lower().startswith("file:"):
        path = "File:" + path[5:]
    return path.replace("_", " ")


def api_query_youtube_ids(file_titles: list[str]) -> dict[str, str]:
    """Map File: page title -> YouTube id for Fandom-hosted youtube videos."""
    out: dict[str, str] = {}
    chunk_size = 40
    for i in range(0, len(file_titles), chunk_size):
        chunk = file_titles[i : i + chunk_size]
        titles_param = "|".join(urllib.parse.quote(t, safe="") for t in chunk)
        url = (
            f"{API}?action=query&format=json&prop=imageinfo"
            f"&iiprop=metadata%7Cmime&titles={titles_param}"
        )
        proc = subprocess.run(
            ["curl", "-sS", "-L", "-A", UA, "--max-time", "120", url],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            continue
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            continue
        for page in data.get("query", {}).get("pages", {}).values():
            title = page.get("title")
            if not title:
                continue
            ii = (page.get("imageinfo") or [{}])[0]
            meta_list = ii.get("metadata") or []
            meta = {m["name"]: m["value"] for m in meta_list if "name" in m and "value" in m}
            if ii.get("mime") == "video/youtube" and meta.get("videoId"):
                out[title] = str(meta["videoId"])
    return out


_ANCHOR_OPEN_RE = re.compile(r"<a\b[^>]*>", re.IGNORECASE)


def inject_youtube_ids(html: str) -> str:
    """Add data-youtube-id on Fandom video thumb links so the local lightbox can embed."""
    titles_set: dict[str, None] = {}
    for m in _ANCHOR_OPEN_RE.finditer(html):
        tag = m.group(0)
        lo = tag.lower()
        if "data-youtube-id=" in lo:
            continue
        if "video" not in lo:
            continue
        hm = re.search(
            r'href="(https://ninjago\.fandom\.com/wiki/(?:File|file):[^"#]+)"',
            tag,
            re.I,
        )
        if not hm:
            continue
        t = file_title_from_fandom_file_href(hm.group(1))
        if t:
            titles_set[t] = None
    titles = list(titles_set.keys())
    if not titles:
        return html
    id_map = api_query_youtube_ids(titles)
    if not id_map:
        return html

    def patch_anchor(match: re.Match[str]) -> str:
        tag = match.group(0)
        lo = tag.lower()
        if "data-youtube-id=" in lo:
            return tag
        if "video" not in lo:
            return tag
        hm = re.search(
            r'href="(https://ninjago\.fandom\.com/wiki/(?:File|file):[^"#]+)"',
            tag,
            re.I,
        )
        if not hm:
            return tag
        t = file_title_from_fandom_file_href(hm.group(1))
        if not t:
            return tag
        yid = id_map.get(t)
        if not yid:
            return tag
        if not tag.endswith(">"):
            return tag
        return tag[:-1] + f' data-youtube-id="{yid}">'

    return _ANCHOR_OPEN_RE.sub(patch_anchor, html)


def strip_outer_parser_div(html: str) -> str:
    m = re.search(
        r'<div\b[^>]*\bmw-parser-output\b[^>]*>',
        html,
        re.IGNORECASE,
    )
    if not m:
        return html.strip()
    start_content = m.end()
    depth = 0
    pos = m.start()
    while pos < len(html):
        open_i = html.find("<div", pos)
        close_i = html.find("</div>", pos)
        if close_i == -1:
            break
        if open_i != -1 and open_i < close_i:
            depth += 1
            pos = open_i + 4
        else:
            depth -= 1
            pos = close_i + len("</div>")
            if depth == 0:
                return html[start_content:close_i].strip()
    return html.strip()


TAB_TABLE_RE = re.compile(
    r'<table[^>]*\bid="tabs"[^>]*>.*?</table>',
    re.DOTALL | re.IGNORECASE,
)


def fix_lazy_images(html: str) -> str:
    """Fandom uses lazyload + data-src; without their JS images stay as 1x1 placeholders."""

    def _fix_img(m: re.Match) -> str:
        tag = m.group(0)
        ds = re.search(r'data-src="([^"]+)"', tag, re.I)
        if not ds:
            return tag
        url = ds.group(1)
        # Must not match `src` inside `data-src="..."` (\b sits between - and s there).
        src_m = re.search(r'(?<![\w-])src="([^"]*)"', tag, re.I)
        if src_m and not src_m.group(1).lower().startswith("data:image"):
            return tag
        if src_m:
            tag = re.sub(
                r'(?<![\w-])src="[^"]*"',
                f'src="{url}"',
                tag,
                count=1,
                flags=re.I,
            )
        else:
            tag = tag.replace("<img", f'<img src="{url}"', 1)
        tag = re.sub(r'\sdata-src="[^"]*"', "", tag, flags=re.I)
        tag = re.sub(r"\blazyload\b", "", tag)
        tag = re.sub(r'class="\s*"', "", tag)
        return tag

    html = re.sub(r"<img\b[^>]*>", _fix_img, html, flags=re.I)

    def _strip_redundant_data_src(m: re.Match) -> str:
        tag = m.group(0)
        if 'data-src="' not in tag:
            return tag
        src_m = re.search(r'(?<![\w-])src="([^"]*)"', tag, re.I)
        if not src_m:
            return tag
        s = src_m.group(1).lower()
        if s.startswith("data:image") or not s.startswith("http"):
            return tag
        return re.sub(r'\sdata-src="[^"]*"', "", tag, count=1, flags=re.I)

    return re.sub(r"<img\b[^>]*>", _strip_redundant_data_src, html, flags=re.I)


# Fandom maintenance / spoiler notice boxes (table-based templates)
_SPOILER_NOTICE_TABLE_RE = re.compile(
    r"<table\b[^>]*>[\s\S]*?Spoiler warning![\s\S]*?</table>",
    re.IGNORECASE,
)
_CLEANUP_NOTICE_TABLE_RE = re.compile(
    r"<table\b[^>]*>[\s\S]*?(?:Oh, my! Would you look at this mess\.|"
    r"This article requires cleanup)[\s\S]*?</table>",
    re.IGNORECASE,
)
# Bottom-of-page navbox: <th>…Character galleries…</th> (must not match across nested tables)
_GALLERY_NAV_HEADER_RE = re.compile(
    r"<th\b[^>]*>[\s\S]{0,500}?Character galleries",
    re.IGNORECASE,
)


def _extract_balanced_table(html: str, start: int) -> tuple[str | None, int]:
    """Return (full table HTML including tags, index after </table>) or (None, start)."""
    low = html.lower()
    n = len(html)
    i = start
    depth = 0
    while i < n:
        if low.startswith("<table", i) and (i + 6 >= n or low[i + 6] in " >\t\n/\r"):
            depth += 1
            i += 6
            continue
        if low.startswith("</table>", i):
            depth -= 1
            i += 8
            if depth == 0:
                return html[start:i], i
            continue
        i += 1
    return None, start


def strip_character_gallery_nav_tables(html: str) -> str:
    """Remove the 'Character galleries' link-grid navbox only.

    A global regex from the first ``<table>`` to ``Character galleries`` can span unrelated
    wrappers (cleanup notices, etc.) and delete almost the entire page — e.g. Arin/Gallery.
    """
    pos = 0
    while pos < len(html):
        low = html.lower()
        start = low.find("<table", pos)
        if start < 0:
            break
        block, end = _extract_balanced_table(html, start)
        if block is None:
            pos = start + 6
            continue
        if _GALLERY_NAV_HEADER_RE.search(block):
            html = html[:start] + html[end:]
            pos = start
            continue
        pos = end
    return html


def _extract_balanced_div(html: str, start: int) -> tuple[str | None, int]:
    """Return (full div element from start through closing tag, index after it) or (None, start)."""
    low = html.lower()
    n = len(html)
    i = start
    depth = 0
    while i < n:
        if low.startswith("<div", i) and (i + 4 >= n or low[i + 4] in " >\t\n/\r"):
            depth += 1
            i += 4
            continue
        if low.startswith("</div>", i):
            depth -= 1
            i += len("</div>")
            if depth == 0:
                return html[start:i], i
            continue
        i += 1
    return None, start


def dedupe_toc_ids_in_full_page(html: str) -> str:
    """
    Character pages embed several wiki fragments; each may include id=toc / toctogglecheckbox /
    mw-toc-heading. Deduplicate so checkbox labels and our CSS/JS bind to the correct block.
    """
    search_pos = 0
    i = 0
    while True:
        m = re.search(
            r'<div\b[^>]*\bid\s*=\s*["\']toc["\'][^>]*>',
            html[search_pos:],
            re.I,
        )
        if not m:
            break
        start = search_pos + m.start()
        block, end = _extract_balanced_div(html, start)
        if not block:
            search_pos = start + 1
            continue
        uid = f"toc-{i}"
        cid = f"toctogglecheckbox-{i}"
        hid = f"mw-toc-heading-{i}"
        nb = re.sub(
            r'(<input\b[^>]*?)\sstyle\s*=\s*["\']display:\s*none["\']',
            r"\1",
            block,
            count=1,
            flags=re.I,
        )
        nb = re.sub(r'\bid\s*=\s*["\']toc["\']', f'id="{uid}"', nb, count=1, flags=re.I)
        nb = re.sub(
            r'\bid\s*=\s*["\']toctogglecheckbox["\']',
            f'id="{cid}"',
            nb,
            count=1,
            flags=re.I,
        )
        nb = re.sub(
            r'\bfor\s*=\s*["\']toctogglecheckbox["\']',
            f'for="{cid}"',
            nb,
            flags=re.I,
        )
        nb = re.sub(
            r'\bid\s*=\s*["\']mw-toc-heading["\']',
            f'id="{hid}"',
            nb,
            count=1,
            flags=re.I,
        )
        nb = re.sub(
            r'\baria-labelledby\s*=\s*["\']mw-toc-heading["\']',
            f'aria-labelledby="{hid}"',
            nb,
            count=1,
            flags=re.I,
        )
        html = html[:start] + nb + html[end:]
        search_pos = start + len(nb)
        i += 1
    return html


# Note: no \b after "toc" — word boundary fails between `"` and the following space.
_TOC_OPEN_RE = re.compile(r'<div\b[^>]*\bid\s*=\s*"toc"[^>]*>', re.IGNORECASE)


def extract_first_toc_block(html: str) -> tuple[str, str]:
    """Remove the first id=toc div; return (remaining_html, toc_outer_html)."""
    m = _TOC_OPEN_RE.search(html)
    if not m:
        return html, ""
    start = m.start()
    block, end = _extract_balanced_div(html, start)
    if not block:
        return html, ""
    return html[:start] + html[end:], block.strip()


_H2_OPEN_TAG_RE = re.compile(r"<h2\b[^>]*>", re.IGNORECASE)
_MW_HEADLINE_IN_H2_RE = re.compile(
    r'<span[^>]*\bclass="[^"]*\bmw-headline\b[^"]*"[^>]*>(.*?)</span>',
    re.IGNORECASE | re.DOTALL,
)


def wrap_overview_h2_sections(fragment: str) -> str:
    """
    Wrap each wiki h2-led block in <details> for mobile accordions.
    The lead (quote + paragraphs before the first h2) stays always visible.
    Sections have no 'open' attribute — collapsed by default on mobile.
    Desktop CSS uses display:contents so layout is unchanged.
    """
    fragment = fragment.strip()
    matches = list(_H2_OPEN_TAG_RE.finditer(fragment))
    if not matches:
        return fragment
    parts: list[str] = []
    parts.append(fragment[: matches[0].start()])
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(fragment)
        block = fragment[start:end]
        tm = _MW_HEADLINE_IN_H2_RE.search(block)
        if tm:
            raw_title = re.sub(r"<[^>]+>", "", tm.group(1))
            title = html_std.escape(html_std.unescape(raw_title.strip())) or "Section"
        else:
            title = "Section"
        parts.append(
            "<details class=\"wiki-char-msection\">\n"
            f"<summary class=\"wiki-char-msection-sum\">{title}</summary>\n"
            f"<div class=\"wiki-char-msection-body\">\n{block}\n</div>\n"
            "</details>"
        )
    return "".join(parts)


def split_portable_infobox(html: str) -> tuple[str, str]:
    """Extract first portable infobox aside for a dedicated chart column. Returns (aside_html, prose_html)."""
    inf_m = _INFOBOX_OPEN_RE.search(html)
    if not inf_m:
        return "", html
    aside_block, a0, a1 = _extract_aside_portable_infobox(html, inf_m)
    if not aside_block:
        return "", html
    remainder = (html[:a0] + html[a1:]).strip()
    return aside_block.strip(), remainder


def build_overview_panel_html(prose: str) -> str:
    """Overview tab: prose only (character card is in .wiki-char-hero-card beside the article)."""
    return (
        "              <div class=\"wiki-char-overview-prose wiki-char-msection-prose wiki-import mw-parser-output\">\n"
        + indent_block(prose.strip(), 16)
        + "\n              </div>"
    )


def build_hero_card_html(infobox: str) -> str:
    """Floated character card (PC: right rail, scrolls with page). Empty if no infobox.

    Fandom's portable infobox keeps `pi-theme-*` classes on `<aside>`; styles.css maps those
    to title / header / tab accents for the hero rail only.
    """
    if not (infobox or "").strip():
        return ""
    box = infobox.strip()
    return (
        '          <div class="wiki-char-hero-card wiki-import" aria-label="Character facts">\n'
        + indent_block(box, 12)
        + "\n          </div>\n"
    )


_INFOBOX_OPEN_RE = re.compile(
    r"<aside\b[^>]*\bportable-infobox\b[^>]*>", re.IGNORECASE
)


def _index_after_matching_aside(html: str, content_start: int) -> int | None:
    """Index just after the </aside> that closes the aside whose body starts at content_start."""
    low = html.lower()
    n = len(html)
    depth = 1
    i = content_start
    while i < n:
        o = low.find("<aside", i)
        c = low.find("</aside>", i)
        if c == -1:
            return None
        if o != -1 and o < c:
            depth += 1
            i = o + 6
            continue
        depth -= 1
        nxt = c + len("</aside>")
        if depth == 0:
            return nxt
        i = nxt
    return None


_QUOTE_OPEN_RE = re.compile(
    r'<div\b[^>]*\bclass="[^"]*\bquote\b[^"]*"[^>]*>', re.IGNORECASE
)


def _extract_aside_portable_infobox(html: str, open_m: re.Match[str]) -> tuple[str | None, int, int]:
    start = open_m.start()
    gt = html.find(">", start)
    if gt == -1:
        return None, start, start
    after = _index_after_matching_aside(html, gt + 1)
    if after is None:
        return None, start, start
    return html[start:after], start, after


def _index_after_lead_quote_div(html: str) -> int | None:
    m = _QUOTE_OPEN_RE.search(html)
    if not m:
        return None
    block, end = _extract_balanced_div(html, m.start())
    if not block:
        return None
    return end


def _insert_toc_after_nth_p(html: str, start_from: int, toc_block: str, n: int) -> str:
    """Insert toc_block after the n-th </p> at or after start_from (n is 1-based)."""
    lo = html.lower()
    pos = start_from
    tag = "</p>"
    for _ in range(n):
        i = lo.find(tag, pos)
        if i == -1:
            return html + "\n" + toc_block + "\n"
        pos = i + len(tag)
    return html[:pos] + "\n" + toc_block + "\n" + html[pos:]


def reorder_character_article_layout(html: str) -> str:
    """
    Wikipedia-style lead: first line + first paragraphs + Contents on the LEFT; character
    chart (infobox) floats RIGHT alongside them.

    1) Remove TOC and infobox from the parse tree.
    2) Insert infobox *before* the quote block so the opening line wraps beside the chart
       (float right + following prose).
    3) Re-insert TOC after the first </p> that follows </aside> (lead paragraph).
    """
    toc_m = _TOC_OPEN_RE.search(html)
    if not toc_m:
        return html
    toc_block, toc_end = _extract_balanced_div(html, toc_m.start())
    if not toc_block:
        return html
    h = html[: toc_m.start()] + html[toc_end:]

    inf_m = _INFOBOX_OPEN_RE.search(h)
    if not inf_m:
        return html
    aside_block, a0, a1 = _extract_aside_portable_infobox(h, inf_m)
    if not aside_block:
        return html
    h = h[:a0] + h[a1:]

    qm = _QUOTE_OPEN_RE.search(h)
    if qm:
        ins = qm.start()
        h = h[:ins] + aside_block + "\n" + h[ins:]
    else:
        h = aside_block + "\n" + h

    aside_close = h.find("</aside>", 0)
    if aside_close == -1:
        return h + "\n" + toc_block + "\n"
    after_aside = aside_close + len("</aside>")
    # Skip the quote block so we don't insert TOC on a </p> inside it.
    qe = _index_after_lead_quote_div(h)
    start_toc_scan = qe if qe is not None else after_aside
    h = _insert_toc_after_nth_p(h, start_toc_scan, toc_block, 1)
    return h


def strip_mw_collapsed_character_navboxes(html: str) -> str:
    """
    Remove big Heroes/Allies/Villains link grids (mw-collapsible mw-collapsed + 2px border).
    Fandom no longer always uses the text 'Character galleries' in the title row.
    """

    def is_character_navbox(block: str) -> bool:
        b = block.lower()
        return (
            "mw-collapsible" in b
            and "mw-collapsed" in b
            and "border:2px solid" in b
            and "margin-top:1em" in b
        )

    changed = True
    while changed:
        changed = False
        pos = 0
        while pos < len(html):
            low = html.lower()
            start = low.find("<table", pos)
            if start < 0:
                break
            block, end = _extract_balanced_table(html, start)
            if block is None:
                break
            if is_character_navbox(block):
                html = html[:start] + html[end:]
                changed = True
                break
            pos = end
    return html


def strip_wiki_notice_tables(html: str) -> str:
    """Remove spoiler, cleanup, and footer navbox tables from parsed wiki HTML."""
    prev = None
    while prev != html:
        prev = html
        html = _SPOILER_NOTICE_TABLE_RE.sub("", html)
        html = _CLEANUP_NOTICE_TABLE_RE.sub("", html)
        html = strip_character_gallery_nav_tables(html)
        html = strip_mw_collapsed_character_navboxes(html)
    return html


def rewrite_wiki_html(inner: str) -> str:
    inner = TAB_TABLE_RE.sub("", inner)
    inner = re.sub(
        r'(<a\b[^>]*\bhref=")(/wiki/[^"#]*)(\#[^"]*)?(")',
        lambda m: f'{m.group(1)}{BASE}{m.group(2)}{m.group(3) or ""}{m.group(4)}',
        inner,
        flags=re.IGNORECASE,
    )
    inner = re.sub(
        r'(<a\b[^>]*\bhref=")(/wiki/[^"]*)(")',
        lambda m: f'{m.group(1)}{BASE}{m.group(2)}{m.group(3)}',
        inner,
        flags=re.IGNORECASE,
    )
    # Protocol-relative URLs (//static.wikia...) — avoid mangling https://
    inner = re.sub(r'(?<=[\s",=])//([a-zA-Z0-9])', r"https://\1", inner)
    inner = re.sub(r'(^|>)//([a-zA-Z0-9])', r"\1https://\2", inner)
    inner = re.sub(r"<script\b[^>]*>.*?</script>", "", inner, flags=re.DOTALL | re.IGNORECASE)
    inner = re.sub(r"<style\b[^>]*>.*?</style>", "", inner, flags=re.DOTALL | re.IGNORECASE)
    inner = fix_lazy_images(inner)
    inner = strip_wiki_notice_tables(inner)
    inner = reorder_character_article_layout(inner)
    inner = inject_youtube_ids(inner)
    return inner.strip()


def fetch_sections_optional(wiki_page_title: str) -> dict[str, str] | None:
    """Fetch overview (required) + History / relationships / Gallery when they exist."""
    tabs = wiki_tab_titles(wiki_page_title)
    out: dict[str, str] = {}
    try:
        raw = api_parse(tabs["overview"])
    except (RuntimeError, json.JSONDecodeError, KeyError, TypeError):
        return None
    if not raw or not str(raw).strip():
        return None
    inner = strip_outer_parser_div(raw)
    out["overview"] = rewrite_wiki_html(inner)
    for key in ("history", "relationships", "gallery"):
        try:
            raw = api_parse(tabs[key])
        except (RuntimeError, json.JSONDecodeError, KeyError, TypeError):
            out[key] = ""
            continue
        if not raw or not str(raw).strip():
            out[key] = ""
            continue
        inner = strip_outer_parser_div(raw)
        out[key] = rewrite_wiki_html(inner)
    return out


def wiki_title_from_wiki_url(url: str) -> str | None:
    """`https://ninjago.fandom.com/wiki/Foo_bar` -> `Foo bar` (MediaWiki title)."""
    u = (url or "").strip()
    if "/wiki/" not in u:
        return None
    part = u.split("/wiki/", 1)[-1].split("#")[0].split("?")[0]
    title = urllib.parse.unquote(part).replace("_", " ").strip()
    return title or None


def import_character(
    slug: str,
    display_label: str,
    wiki_page_title: str,
    *,
    root: Path | None = None,
    quiet: bool = False,
) -> Path:
    """
    Fetch Fandom tabs (optional History / relationships / Gallery), write characters/<slug>/index.html.
    Raises FileNotFoundError if the main wiki article does not exist.
    """
    root = root or Path(__file__).resolve().parent.parent
    if not quiet:
        print(f"Fetching… {display_label!r} (wiki: {wiki_page_title!r})", file=sys.stderr)
    parts = fetch_sections_optional(wiki_page_title)
    if parts is None:
        raise FileNotFoundError(f"No wiki overview page: {wiki_page_title!r}")

    overview_no_toc, toc_overview = extract_first_toc_block(parts["overview"])
    infobox_html, overview_prose = split_portable_infobox(overview_no_toc)
    overview_prose = wrap_overview_h2_sections(overview_prose)
    hero_card = build_hero_card_html(infobox_html)
    parts["overview"] = build_overview_panel_html(overview_prose)

    toc_map: dict[str, str] = {"overview": toc_overview}
    for key in SECTION_TAB_KEYS:
        body_no_toc, t = extract_first_toc_block(parts[key])
        parts[key] = wrap_overview_h2_sections(body_no_toc)
        toc_map[key] = t

    extra_tabs = [k for k in SECTION_TAB_KEYS if section_has_visible_content(parts[k])]
    visible_tab_keys: tuple[str, ...] = ("overview",) + tuple(extra_tabs)
    multi_tab = len(extra_tabs) > 0
    toc_sidebar, split_cls = build_toc_sidebar_and_split_class(toc_map, visible_tab_keys)
    toc_bar = ""

    wiki_char_tabs = build_wiki_char_tabs_html(visible_tab_keys)
    wiki_char_panels = build_wiki_char_panels_html(parts, visible_tab_keys, multi_tab)

    wiki_breadcrumb_block = (
        '          <nav class="wiki-char-breadcrumb" aria-label="Breadcrumb">\n'
        '            <a href="/characters">Characters</a>\n'
        '            <span aria-hidden="true">/</span>\n'
        f'            <span>{display_label}</span>\n'
        '          </nav>\n'
        f'          <h1 class="visually-hidden">{display_label}</h1>'
    )

    out_path = root / "characters" / slug / "index.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body = TEMPLATE.format(
        display=display_label,
        extra_head="",
        wiki_breadcrumb_block=wiki_breadcrumb_block,
        hero_card=hero_card,
        wiki_char_split_cls=split_cls,
        toc_sidebar=toc_sidebar,
        toc_bar=toc_bar,
        wiki_char_tabs=wiki_char_tabs,
        wiki_char_panels=wiki_char_panels,
    )
    body = dedupe_toc_ids_in_full_page(body)
    out_path.write_text(body, encoding="utf-8")
    if not quiet:
        print(f"Wrote {out_path} ({len(body)} bytes)", file=sys.stderr)
    return out_path


TEMPLATE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
    <!-- Fandom CDN returns 404 for hotlinked images when Referer is not fandom.com -->
    <meta name="referrer" content="no-referrer" />
    <meta name="description" content="{display} — Ninjago Wiki Project" />
    <title>{display} • Ninjago Wiki Project</title>
    <link rel="stylesheet" href="/styles.css" />
    <meta name="theme-color" content="#06070a" />
{extra_head}  </head>
  <body>
    <a class="skip-link" href="#content">Skip to content</a>

    <header class="site-header">
      <div class="container header-inner">
        <a class="brand" href="/">
          <span class="brand-mark" aria-hidden="true">
            <img class="brand-img" src="/assets/logo.png" alt="" loading="eager" decoding="async" />
          </span>
        </a>

        <input class="menu-toggle" type="checkbox" id="menu-toggle" />
        <label class="menu-button" for="menu-toggle" aria-label="Open navigation" role="button">
          <span class="menu-button-lines" aria-hidden="true"><span></span></span>
        </label>

        <nav class="nav" aria-label="Primary">
          <a href="/characters">Characters</a>
          <a href="/episodes">Episodes</a>
          <a href="/timeline">Timeline</a>
          <a href="/weapons">Weapons</a>
          <a href="/sets">Sets</a>
          <a href="/media">Media</a>
          <a href="/all-pages">All Pages</a>
        </nav>
      </div>
    </header>

    <main id="content" class="page wiki-char-page" data-wiki-char-tab="overview">
      <div class="wiki-char-hero wiki-char-hero--crumb-only">
        <div class="container wiki-char-hero-inner">
{wiki_breadcrumb_block}
        </div>
      </div>

      <div class="{wiki_char_split_cls}">
{toc_sidebar}        <div class="wiki-char-main-wrap">
        <div class="container wiki-char-body">
{toc_bar}
{wiki_char_tabs}        <div class="wiki-char-article-rail">
{hero_card}        <div class="wiki-char-layout wiki-char-layout--full">
          <article class="wiki-char-article">
{wiki_char_panels}
          </article>
        </div>
        </div>
        </div>
        </div>
      </div>
    </main>

    <div id="wiki-lightbox" class="wiki-lightbox" hidden>
      <div class="wiki-lightbox-backdrop" tabindex="-1" aria-hidden="true"></div>
      <div class="wiki-lightbox-layout" role="dialog" aria-modal="true" aria-label="Media viewer">
        <header class="wiki-lightbox-top">
          <button type="button" class="wiki-lightbox-close" aria-label="Close">&times;</button>
        </header>
        <div class="wiki-lightbox-main">
          <button type="button" class="wiki-lightbox-nav wiki-lightbox-prev" aria-label="Previous">&#8249;</button>
          <div class="wiki-lightbox-viewport">
            <img class="wiki-lightbox-img" alt="" decoding="async" />
            <div class="wiki-lightbox-video" hidden>
              <iframe class="wiki-lightbox-iframe" title="YouTube video" allowfullscreen="" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"></iframe>
            </div>
          </div>
          <button type="button" class="wiki-lightbox-nav wiki-lightbox-next" aria-label="Next">&#8250;</button>
        </div>
        <footer class="wiki-lightbox-bottom">
          <div class="wiki-lightbox-thumbs" role="tablist" aria-label="All images in this article"></div>
        </footer>
      </div>
    </div>

    <footer class="site-footer">
      <div class="container footer-inner footer-inner--min">
        <div class="footer-left">
          <div class="footer-meta">
            <div class="footer-line footer-line--muted">Fan-made Ninjago wiki. Not affiliated with LEGO or the official show.</div>
          </div>
        </div>
        <div class="footer-links" aria-label="Footer links">
          <a class="footer-link" href="/about">About</a>
        </div>
      </div>
    </footer>

    <script>
      (function () {{
        function syncWikiCharTocPanels(tabId) {{
          document.querySelectorAll(".wiki-char-toc-panel[data-wiki-toc-tab]").forEach(function (el) {{
            var match = el.getAttribute("data-wiki-toc-tab") === tabId;
            var empty = el.getAttribute("data-wiki-toc-empty") === "1";
            el.hidden = !(match && !empty);
          }});
        }}
        function setWikiCharTabData(tabId) {{
          var root = document.querySelector("main.wiki-char-page");
          if (root) root.setAttribute("data-wiki-char-tab", tabId || "overview");
        }}
        function wikiCharTabIds() {{
          var out = [];
          document.querySelectorAll(".wiki-char-tab[data-tab]").forEach(function (b) {{
            out.push(b.getAttribute("data-tab"));
          }});
          return out;
        }}
        function saveWikiCharTab(tabId) {{
          var ids = wikiCharTabIds();
          var id = tabId || "overview";
          if (ids.length === 0) id = "overview";
          else if (ids.indexOf(id) === -1) id = ids[0] || "overview";
          try {{
            var base = location.pathname + location.search;
            var useHash = ids.length > 1 && id !== "overview";
            history.replaceState(null, "", useHash ? base + "#tab-" + id : base);
          }} catch (e2) {{}}
        }}
        function applyWikiCharTab(tabId) {{
          var id = tabId || "overview";
          var tabs = document.querySelectorAll(".wiki-char-tab");
          var panels = document.querySelectorAll(".wiki-char-panel");
          tabs.forEach(function (b) {{
            var on = b.getAttribute("data-tab") === id;
            b.classList.toggle("is-active", on);
            b.setAttribute("aria-selected", on ? "true" : "false");
          }});
          panels.forEach(function (p) {{
            var show = p.id === "panel-" + id;
            p.hidden = !show;
            p.classList.toggle("is-hidden", !show);
          }});
          syncWikiCharTocPanels(id);
          setWikiCharTabData(id);
        }}
        function resolveInitialWikiCharTab() {{
          var ids = wikiCharTabIds();
          var hm = /^#tab-([a-z]+(?:-[a-z]+)*)$/.exec(location.hash || "");
          if (hm && ids.indexOf(hm[1]) !== -1) return hm[1];
          return "overview";
        }}
        var initialWikiTab = resolveInitialWikiCharTab();
        applyWikiCharTab(initialWikiTab);
        saveWikiCharTab(initialWikiTab);
        document.querySelectorAll(".wiki-char-tab").forEach(function (btn) {{
          btn.addEventListener("click", function () {{
            var id = btn.getAttribute("data-tab");
            applyWikiCharTab(id);
            saveWikiCharTab(id);
          }});
        }});
        /* TOC: hash links activate the tab that owns this Contents block, then navigate */
        (function () {{
          document.querySelectorAll(".wiki-char-toc-mount").forEach(function (mount) {{
            mount.addEventListener("click", function (e) {{
              var a = e.target.closest("a[href^='#']");
              if (!a) return;
              var href = a.getAttribute("href") || "";
              if (href.length < 2) return;
              var panel = a.closest(".wiki-char-toc-panel[data-wiki-toc-tab]");
              var tabId = panel ? panel.getAttribute("data-wiki-toc-tab") : "overview";
              var tabBtn = document.querySelector('.wiki-char-tab[data-tab="' + tabId + '"]');
              if (tabBtn && !tabBtn.classList.contains("is-active")) {{
                tabBtn.click();
              }}
            }});
          }});
        }})();
        /* Desktop: collapse Contents column to a slim strip (sessionStorage) */
        (function () {{
          var split = document.querySelector(".wiki-char-content-split--with-toc");
          if (!split) return;
          var deskHide = document.getElementById("wiki-char-toc-sidebar-hide");
          var deskReveal = document.getElementById("wiki-char-toc-sidebar-reveal");
          var mqDesk = window.matchMedia("(min-width: 900px)");
          var storageKeyDesk = "wikiCharTocDesk:" + location.pathname;
          function setDeskCollapsed(collapsed) {{
            split.classList.toggle("is-toc-desktop-collapsed", collapsed);
            if (deskHide) {{
              deskHide.hidden = !!collapsed;
              deskHide.setAttribute("aria-expanded", collapsed ? "false" : "true");
            }}
            if (deskReveal) {{
              deskReveal.hidden = !collapsed;
              deskReveal.setAttribute("aria-expanded", collapsed ? "true" : "false");
            }}
            try {{
              sessionStorage.setItem(storageKeyDesk, collapsed ? "1" : "0");
            }} catch (err) {{}}
          }}
          function resetDeskChromeForMobile() {{
            split.classList.remove("is-toc-desktop-collapsed");
            if (deskHide) {{
              deskHide.hidden = false;
              deskHide.setAttribute("aria-expanded", "true");
            }}
            if (deskReveal) {{
              deskReveal.hidden = true;
              deskReveal.setAttribute("aria-expanded", "false");
            }}
          }}
          if (deskHide) deskHide.addEventListener("click", function () {{ if (mqDesk.matches) setDeskCollapsed(true); }});
          if (deskReveal) deskReveal.addEventListener("click", function () {{ if (mqDesk.matches) setDeskCollapsed(false); }});
          try {{
            if (sessionStorage.getItem(storageKeyDesk) === "1" && mqDesk.matches) setDeskCollapsed(true);
          }} catch (err) {{}}
          if (mqDesk.addEventListener) {{
            mqDesk.addEventListener("change", function () {{
              if (!mqDesk.matches) resetDeskChromeForMobile();
              else try {{
                if (sessionStorage.getItem(storageKeyDesk) === "1") setDeskCollapsed(true);
              }} catch (e2) {{}}
            }});
          }}
        }})();
        /* TOC: root list collapsed by default (checkbox + CSS); nested branches toggle per row (skip horizontal bar) */
        (function () {{
          var mqRoot = window.matchMedia("(min-width: 720px)");
          document.querySelectorAll(".wiki-import div.toc").forEach(function (toc) {{
            if (toc.closest(".wiki-char-toc-shell--mobile")) return;
            if (toc.closest(".wiki-char-toc-sidebar")) return;
            var cb = toc.querySelector(":scope > input.toctogglecheckbox");
            var title = toc.querySelector(":scope > .toctitle");
            if (!cb || !title) return;
            var h2 = title.querySelector("h2");
            if (mqRoot.matches && h2) {{
              h2.setAttribute("tabindex", "0");
              h2.style.cursor = "pointer";
              h2.addEventListener("click", function (e) {{
                if (e.target.closest("label, a")) return;
                cb.checked = !cb.checked;
                cb.dispatchEvent(new Event("change", {{ bubbles: true }}));
              }});
              h2.addEventListener("keydown", function (e) {{
                if (e.key === "Enter" || e.key === " ") {{
                  e.preventDefault();
                  cb.checked = !cb.checked;
                  cb.dispatchEvent(new Event("change", {{ bubbles: true }}));
                }}
              }});
            }}
            var label = title.querySelector("label.toctogglelabel");
            if (label && !label.getAttribute("aria-label")) {{
              label.setAttribute("aria-label", "Show or hide contents list");
            }}
            function syncRoot() {{
              if (!mqRoot.matches) {{
                title.setAttribute("aria-expanded", "true");
                return;
              }}
              title.setAttribute("aria-expanded", cb.checked ? "true" : "false");
            }}
            cb.addEventListener("change", syncRoot);
            if (mqRoot.addEventListener) {{
              mqRoot.addEventListener("change", syncRoot);
            }} else if (mqRoot.addListener) {{
              mqRoot.addListener(syncRoot);
            }}
            syncRoot();
          }});
          document.querySelectorAll(".wiki-import div.toc li").forEach(function (li) {{
            if (li.closest(".wiki-char-toc-shell--mobile")) return;
            var nested = li.querySelector(":scope > ul");
            var directA = li.querySelector(":scope > a");
            if (!nested || !directA) return;
            li.classList.add("toc-branch");
            nested.classList.add("toc-branch-children");
            nested.hidden = true;
            var btn = document.createElement("button");
            btn.type = "button";
            btn.className = "toc-collapse-btn";
            btn.setAttribute("aria-expanded", "false");
            btn.setAttribute("aria-label", "Toggle subsections");
            var row = document.createElement("span");
            row.className = "toc-branch-row";
            li.insertBefore(row, directA);
            row.appendChild(directA);
            row.appendChild(btn);
            btn.addEventListener("click", function (e) {{
              e.preventDefault();
              e.stopPropagation();
              var open = nested.hidden;
              nested.hidden = !open;
              btn.setAttribute("aria-expanded", open ? "true" : "false");
              btn.classList.toggle("is-open", open);
            }});
          }});
        }})();
        /* Portable infobox image tabs (Current / Pre–S8) — Fandom JS not loaded */
        (function () {{
          document.querySelectorAll(".wiki-import .pi-image-collection.wds-tabber").forEach(function (tabber) {{
            var tabLis = tabber.querySelectorAll(".wds-tabs .wds-tabs__tab");
            var panels = Array.prototype.filter.call(tabber.children, function (el) {{
              return el.classList && el.classList.contains("wds-tab__content");
            }});
            if (!tabLis.length || !panels.length) return;
            var n = Math.min(tabLis.length, panels.length);
            tabLis.forEach(function (tab, idx) {{
              if (idx >= n) return;
              tab.setAttribute("role", "tab");
              tab.setAttribute("aria-selected", tab.classList.contains("wds-is-current") ? "true" : "false");
              tab.setAttribute("tabindex", tab.classList.contains("wds-is-current") ? "0" : "-1");
              tab.addEventListener("click", function () {{
                tabLis.forEach(function (t, j) {{
                  var on = j === idx;
                  t.classList.toggle("wds-is-current", on);
                  t.setAttribute("tabindex", on ? "0" : "-1");
                  t.setAttribute("aria-selected", on ? "true" : "false");
                }});
                panels.forEach(function (panel, j) {{
                  if (j < n) panel.classList.toggle("wds-is-current", j === idx);
                }});
              }});
            }});
          }});
        }})();
        /* Wikia video gallery: real YouTube iframes (thumbnails are tiny; play icon clicks missed <img>) */
        (function () {{
          document.querySelectorAll(".wiki-import .wikia-gallery a.image.video[data-youtube-id]").forEach(function (anchor) {{
            var id = anchor.getAttribute("data-youtube-id");
            if (!id) return;
            var rawTitle = anchor.getAttribute("title") || "YouTube video";
            var title = rawTitle.indexOf("(") > 0 ? rawTitle.split("(")[0].trim() : rawTitle;
            var wrap = document.createElement("div");
            wrap.className = "wiki-video-embed";
            var ifr = document.createElement("iframe");
            ifr.setAttribute("src", "https://www.youtube-nocookie.com/embed/" + encodeURIComponent(id) + "?rel=0");
            ifr.setAttribute("title", title);
            ifr.setAttribute("allowfullscreen", "");
            ifr.setAttribute("loading", "lazy");
            ifr.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
            ifr.setAttribute(
              "allow",
              "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            );
            wrap.appendChild(ifr);
            anchor.replaceWith(wrap);
          }});
        }})();
        /* Full-screen media viewer: images + YouTube embeds, scrollable thumbnails */
        (function () {{
          var root = document.getElementById("wiki-lightbox");
          var pageRoot = document.querySelector("main.wiki-char-page");
          if (!root || !pageRoot) return;
          var backdrop = root.querySelector(".wiki-lightbox-backdrop");
          var btnClose = root.querySelector(".wiki-lightbox-close");
          var btnPrev = root.querySelector(".wiki-lightbox-prev");
          var btnNext = root.querySelector(".wiki-lightbox-next");
          var lbImg = root.querySelector(".wiki-lightbox-img");
          var lbVideo = root.querySelector(".wiki-lightbox-video");
          var lbIframe = root.querySelector(".wiki-lightbox-iframe");
          var thumbsEl = root.querySelector(".wiki-lightbox-thumbs");
          if (!lbImg || !lbVideo || !lbIframe || !thumbsEl) return;

          var list = [];
          var idx = 0;
          var lbScrollY = 0;
          var lbHtmlOverflow = "";
          var lbHtmlMaxWidth = "";

          function largerUrl(url) {{
            if (!url) return url;
            return url.replace(/\\/scale-to-width-down\\/\\d+/gi, "");
          }}

          function thumbUrl(url) {{
            if (!url) return url;
            if ((/\\/scale-to-width-down\\/\\d+/i).test(url)) {{
              return url.replace(/\\/scale-to-width-down\\/\\d+/gi, "/scale-to-width-down/96");
            }}
            var q = url.indexOf("?");
            if (q === -1) return url + "/scale-to-width-down/96";
            return url.slice(0, q) + "/scale-to-width-down/96" + url.slice(q);
          }}

          function gather() {{
            return Array.prototype.slice
              .call(pageRoot.querySelectorAll("img[src]"))
              .filter(function (im) {{
                var s = im.getAttribute("src") || "";
                if (!s || s.indexOf("data:") === 0) return false;
                if (im.closest(".wiki-lightbox")) return false;
                if (im.closest(".wiki-lightbox-thumbs")) return false;
                if (im.closest("noscript")) return false;
                return true;
              }})
              .map(function (im) {{
                var a = im.closest("a");
                var yt = (a && a.getAttribute("data-youtube-id")) || "";
                return {{ img: im, yt: yt || null }};
              }});
          }}

          function rebuildThumbs() {{
            thumbsEl.innerHTML = "";
            if (!list.length) return;
            list.forEach(function (item, i) {{
              var b = document.createElement("button");
              b.type = "button";
              b.className = "wiki-lightbox-thumb";
              if (item.yt) b.classList.add("wiki-lightbox-thumb--video");
              b.setAttribute(
                "aria-label",
                (item.yt ? "Play video " : "Show image ") + (i + 1) + " of " + list.length
              );
              var ti = document.createElement("img");
              ti.alt = "";
              ti.decoding = "async";
              ti.loading = "lazy";
              var u = (item.img.currentSrc || item.img.src || "").trim();
              ti.src = thumbUrl(u);
              b.appendChild(ti);
              b.addEventListener("click", function () {{
                idx = i;
                render();
              }});
              thumbsEl.appendChild(b);
            }});
          }}

          function syncThumbStrip() {{
            var btns = thumbsEl.querySelectorAll(".wiki-lightbox-thumb");
            for (var i = 0; i < btns.length; i++) {{
              var on = i === idx;
              btns[i].classList.toggle("is-selected", on);
              btns[i].setAttribute("aria-current", on ? "true" : "false");
              if (on) {{
                try {{
                  btns[i].scrollIntoView({{ inline: "center", block: "nearest", behavior: "smooth" }});
                }} catch (err) {{
                  btns[i].scrollIntoView();
                }}
              }}
            }}
          }}

          function render() {{
            if (!list.length) return;
            idx = (idx + list.length) % list.length;
            var item = list[idx];
            var el = item.img;
            var url = (el.currentSrc || el.src || "").trim();
            if (item.yt) {{
              lbImg.removeAttribute("src");
              lbImg.style.display = "none";
              lbImg.alt = "";
              lbVideo.hidden = false;
              lbIframe.src =
                "https://www.youtube-nocookie.com/embed/" +
                encodeURIComponent(item.yt) +
                "?autoplay=1&rel=0";
            }} else {{
              lbIframe.removeAttribute("src");
              lbVideo.hidden = true;
              lbImg.style.display = "";
              lbImg.src = largerUrl(url);
              lbImg.alt = el.getAttribute("alt") || "";
            }}
            var multi = list.length > 1;
            btnPrev.disabled = !multi;
            btnNext.disabled = !multi;
            btnPrev.style.visibility = multi ? "visible" : "hidden";
            btnNext.style.visibility = multi ? "visible" : "hidden";
            btnPrev.setAttribute("aria-hidden", multi ? "false" : "true");
            btnNext.setAttribute("aria-hidden", multi ? "false" : "true");
            syncThumbStrip();
          }}

          function openAt(img) {{
            list = gather();
            idx = -1;
            for (var j = 0; j < list.length; j++) {{
              if (list[j].img === img) {{
                idx = j;
                break;
              }}
            }}
            if (idx < 0) idx = 0;
            rebuildThumbs();
            render();
            root.hidden = false;
            lbScrollY = window.scrollY || document.documentElement.scrollTop || 0;
            lbHtmlOverflow = document.documentElement.style.overflow;
            lbHtmlMaxWidth = document.documentElement.style.maxWidth;
            document.documentElement.style.overflow = "hidden";
            document.documentElement.style.maxWidth = "100%";
            document.documentElement.classList.add("wiki-lightbox-open");
            document.body.style.top = -lbScrollY + "px";
            document.body.style.width = "100%";
            document.body.style.maxWidth = "100%";
            document.body.classList.add("wiki-lightbox-open");
            btnClose.focus();
          }}

          function closeLb() {{
            root.hidden = true;
            lbImg.removeAttribute("src");
            lbImg.alt = "";
            lbImg.style.display = "";
            lbIframe.removeAttribute("src");
            lbVideo.hidden = true;
            thumbsEl.innerHTML = "";
            document.body.style.top = "";
            document.body.style.width = "";
            document.body.style.maxWidth = "";
            document.body.classList.remove("wiki-lightbox-open");
            document.documentElement.style.overflow = lbHtmlOverflow;
            document.documentElement.style.maxWidth = lbHtmlMaxWidth;
            document.documentElement.classList.remove("wiki-lightbox-open");
            window.scrollTo(0, lbScrollY);
          }}

          pageRoot.addEventListener("click", function (e) {{
            var a = e.target.closest("a.image.lightbox");
            if (!a && e.target.closest("aside.portable-infobox")) {{
              a = e.target.closest("aside.portable-infobox figure.pi-image a.image");
            }}
            if (!a || !pageRoot.contains(a)) return;
            var im = a.querySelector("img[src]");
            if (!im) return;
            var s = im.getAttribute("src") || "";
            if (!s || s.indexOf("data:") === 0) return;
            e.preventDefault();
            e.stopPropagation();
            openAt(im);
          }});

          btnClose.addEventListener("click", closeLb);
          backdrop.addEventListener("click", closeLb);
          btnPrev.addEventListener("click", function () {{
            idx--;
            render();
          }});
          btnNext.addEventListener("click", function () {{
            idx++;
            render();
          }});

          document.addEventListener("keydown", function (e) {{
            if (root.hidden) return;
            if (e.key === "Escape") {{
              e.preventDefault();
              closeLb();
            }} else if (e.key === "ArrowLeft" && list.length > 1) {{
              e.preventDefault();
              idx--;
              render();
            }} else if (e.key === "ArrowRight" && list.length > 1) {{
              e.preventDefault();
              idx++;
              render();
            }}
          }});
        }})();
      }})();
    </script>
    <script src="/app.js" defer></script>
  </body>
</html>
"""


def indent_block(text: str, spaces: int) -> str:
    pad = " " * spaces
    lines = text.splitlines()
    return "\n".join(pad + ln if ln else "" for ln in lines)


SECTION_TAB_KEYS = ("history", "relationships", "gallery")

TAB_LABELS = {
    "overview": "Overview",
    "history": "History",
    "relationships": "Relationships",
    "gallery": "Gallery",
}


def section_has_visible_content(html: str) -> bool:
    """True if section has text, tables, or embedded media (not empty wiki stubs)."""
    s = (html or "").strip()
    if not s:
        return False
    if re.search(r"<(?:img|video|iframe|picture|figure|svg|table|audio)\b", s, re.I):
        return True
    text = re.sub(r"<[^>]+>", " ", s)
    text = html_std.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return bool(re.search(r"\w", text, re.UNICODE))


def build_toc_panel_rows(toc_map: dict[str, str], indent_mount: int, tab_keys: tuple[str, ...]) -> str:
    """TOC sidebar panels only for tabs that exist and have a non-empty Contents block."""
    chunks: list[str] = []
    for key in tab_keys:
        block = (toc_map.get(key) or "").strip()
        if not block:
            continue
        hidden_attr = "" if key == "overview" else " hidden"
        chunks.append(
            f'                <div class="wiki-char-toc-panel" data-wiki-toc-tab="{key}"{hidden_attr}>\n'
            f'                  <div class="wiki-char-toc-mount wiki-import mw-parser-output">\n'
            + indent_block(block, indent_mount)
            + "\n"
            f'                  </div>\n'
            f'                </div>\n'
        )
    return "".join(chunks)


def build_toc_sidebar_and_split_class(
    toc_map: dict[str, str], visible_tab_keys: tuple[str, ...]
) -> tuple[str, str]:
    """TOC sidebar markup + `wiki-char-content-split` class when any tab has a Contents block."""
    has_any_toc = any((toc_map.get(k) or "").strip() for k in visible_tab_keys)
    if not has_any_toc:
        return "", "wiki-char-content-split"
    panel_rows_side = build_toc_panel_rows(toc_map, 18, visible_tab_keys)
    toc_sidebar = (
        '        <aside class="wiki-char-toc-sidebar" aria-label="Article contents">\n'
        '          <div class="wiki-char-toc-sidebar-viewport" id="wiki-char-toc-sidebar-viewport">\n'
        '            <div class="wiki-char-toc-sidebar-slide" id="wiki-char-toc-sidebar-slide">\n'
        '              <div class="wiki-char-toc-sidebar-main" id="wiki-char-toc-sidebar-main">\n'
        '                <button type="button" class="wiki-char-toc-sidebar-hide" id="wiki-char-toc-sidebar-hide" aria-expanded="true" aria-controls="wiki-char-toc-sidebar-slide" title="Hide contents column">\n'
        '                  <svg class="wiki-char-toc-chevron" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path fill="currentColor" d="M15.41 16.59 10.83 12l4.58-4.59L14 6l-6 6 6 6 1.41-1.41z"/></svg>\n'
        "                </button>\n"
        '                <div class="wiki-char-toc-panels">\n'
        + panel_rows_side
        + "                </div>\n"
        + "              </div>\n"
        + '              <button type="button" class="wiki-char-toc-sidebar-reveal" id="wiki-char-toc-sidebar-reveal" aria-expanded="false" aria-controls="wiki-char-toc-sidebar-slide" hidden title="Show contents column">\n'
        + '                <svg class="wiki-char-toc-chevron" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path fill="currentColor" d="M8.59 16.59 13.17 12 8.59 7.41 10 6l6 6-6 6z"/></svg>\n'
        + "              </button>\n"
        + "            </div>\n"
        + "          </div>\n"
        + "        </aside>\n"
    )
    return toc_sidebar, "wiki-char-content-split wiki-char-content-split--with-toc"


def build_wiki_char_tabs_html(visible_tab_keys: tuple[str, ...]) -> str:
    """Tab strip only when at least one of History / Relationships / Gallery exists."""
    if len(visible_tab_keys) <= 1:
        return ""
    lines = [
        '        <div class="wiki-char-tabs" role="tablist" aria-label="Article sections">',
    ]
    for i, key in enumerate(visible_tab_keys):
        active = i == 0
        label = TAB_LABELS[key]
        cls = "wiki-char-tab is-active" if active else "wiki-char-tab"
        aria_sel = "true" if active else "false"
        lines.append(
            f'          <button type="button" class="{cls}" role="tab" aria-selected="{aria_sel}" '
            f'aria-controls="panel-{key}" id="tab-{key}" data-tab="{key}">{label}</button>'
        )
    lines.append("        </div>")
    return "\n".join(lines) + "\n"


def build_wiki_char_panels_html(
    parts: dict[str, str],
    visible_tab_keys: tuple[str, ...],
    multi_tab: bool,
) -> str:
    chunks: list[str] = []
    for i, key in enumerate(visible_tab_keys):
        label = TAB_LABELS[key]
        label_esc = html_std.escape(label, quote=True)
        if multi_tab:
            active = i == 0
            hidden_cls = "" if active else " is-hidden"
            hidden_attr = "" if active else " hidden"
            role_attr = f'role="tabpanel" aria-labelledby="tab-{key}"'
        else:
            hidden_cls = ""
            hidden_attr = ""
            role_attr = f'role="region" aria-label="{label_esc}"'
        if key == "overview":
            chunks.append(
                f'            <section id="panel-{key}" class="wiki-char-panel{hidden_cls}" {role_attr}{hidden_attr}>\n'
                f'              <h2 class="wiki-char-h2 visually-hidden">{label}</h2>\n'
                f'{parts["overview"]}\n'
                f"            </section>"
            )
        else:
            chunks.append(
                f'            <section id="panel-{key}" class="wiki-char-panel{hidden_cls}" role="tabpanel" '
                f'aria-labelledby="tab-{key}"{hidden_attr}>\n'
                f'              <h2 class="wiki-char-h2 visually-hidden">{label}</h2>\n'
                '              <div class="wiki-import wiki-char-msection-prose mw-parser-output">\n'
                f'{indent_block(parts[key], 16)}\n'
                "              </div>\n"
                "            </section>"
            )
    return "\n\n".join(chunks)


def slug_to_wiki_display(slug: str) -> str:
    """URL slug -> MediaWiki page title (e.g. arin -> Arin, lord-garmadon -> Lord Garmadon)."""
    return slug.replace("-", " ").replace("_", " ").strip().title()


def wiki_tab_titles(display: str) -> dict[str, str]:
    return {
        "overview": display,
        "history": f"{display}/History",
        "relationships": f"{display}'s relationships",
        "gallery": f"{display}/Gallery",
    }


def main() -> None:
    if len(sys.argv) > 2:
        print("Usage: import_wiki_character.py [slug]", file=sys.stderr)
        print("  slug: filesystem segment, e.g. kai, arin (default: kai)", file=sys.stderr)
        sys.exit(1)
    slug = sys.argv[1] if len(sys.argv) == 2 else "kai"
    wiki_pt = slug_to_wiki_display(slug)
    import_character(slug, wiki_pt, wiki_pt)
    print(
        f"Reminder: set assets/data/characters.json entry href to /characters/{slug} "
        f"(homepage search merges this automatically; characters page needs it too).",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
