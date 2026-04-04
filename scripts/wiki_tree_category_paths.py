#!/usr/bin/env python3
"""
Map wiki article titles → longest category slug path from fandom_content_category_tree.json.

Each `directPages` entry is assigned the path of category slugs from the tree root down to
that node. If a title appears under multiple categories, the deepest (longest) path wins;
ties break lexicographically for stable output.

Used for laying out mirrored pages as pages/<content/.../category>/<article-slug>/.
"""

from __future__ import annotations

import html
import json
import textwrap
import urllib.parse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
TREE_JSON = ROOT / "assets" / "data" / "fandom_content_category_tree.json"


def norm_wiki_title_key(title: str) -> str:
    return " ".join((title or "").strip().lower().split())


def build_longest_category_path_by_title(tree_root: dict) -> dict[str, str]:
    """
    Return mapping: norm_wiki_title_key -> 'content/subcat/leaf' (slug segments only).
    """
    best: dict[str, list[str]] = {}

    def consider(title: str, segs: list[str]) -> None:
        k = norm_wiki_title_key(title)
        if not k:
            return
        cur = best.get(k)
        if cur is None:
            best[k] = list(segs)
            return
        if len(segs) > len(cur):
            best[k] = list(segs)
        elif len(segs) == len(cur) and segs < cur:
            best[k] = list(segs)

    def walk(node: dict, ancestor_slugs: list[str]) -> None:
        slug = (node.get("slug") or "").strip()
        segs = ancestor_slugs + [slug] if slug else list(ancestor_slugs)
        for title in node.get("directPages") or []:
            if isinstance(title, str) and title.strip():
                consider(title.strip(), segs)
        for ch in node.get("children") or []:
            walk(ch, segs)

    walk(tree_root, [])
    return {k: "/".join(v) for k, v in best.items()}


def load_tree(root: Path | None = None) -> dict:
    path = (root or ROOT) / "assets" / "data" / "fandom_content_category_tree.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    tree = data.get("tree")
    if not isinstance(tree, dict):
        raise ValueError("JSON missing tree object")
    return tree


def load_title_to_category_path(root: Path | None = None) -> dict[str, str]:
    """Convenience: load tree file and return title key -> category path string."""
    return build_longest_category_path_by_title(load_tree(root))


UNSORTED_SEGMENT = "_unsorted"


def category_path_for_title(
    title: str, title_to_path: dict[str, str], *, fallback: str = UNSORTED_SEGMENT
) -> str:
    k = norm_wiki_title_key(title)
    return title_to_path.get(k) or fallback


def pages_article_dir(root: Path, category_path: str, article_slug: str) -> Path:
    """Filesystem directory for one mirrored article (contains index.html)."""
    parts = [p for p in (category_path or "").strip("/").split("/") if p]
    return root.joinpath("pages", *parts, article_slug)


def all_pages_hash_path(segments: list[str]) -> str:
    """Full slug path as hash (includes root slug if present). Rarely used for UI links."""
    if not segments:
        return ""
    return "#" + "/".join(urllib.parse.quote(s, safe="") for s in segments)


def all_pages_nav_hash_path(tree_root: dict, segments: list[str]) -> str:
    """
    Fragment for /all-pages links that must match all-pages/tree.js.

    Tree navigation omits the root node slug (e.g. content): URLs are #characters/females,
    not #content/characters/females. findNode() walks from the JSON root, so a leading
    'content' segment would look for a non-existent child named 'content'.
    """
    root_slug = (tree_root.get("slug") or "").strip()
    trimmed = list(segments)
    while trimmed and root_slug and trimmed[0] == root_slug:
        trimmed.pop(0)
    if not trimmed:
        return ""
    return "#" + "/".join(urllib.parse.quote(s, safe="") for s in trimmed)


def find_tree_node_for_slug_path(tree_root: dict, segments: list[str]) -> dict | None:
    """Return the tree node for a slug path (e.g. ['content','characters']), or None."""
    if not segments:
        return tree_root
    root_slug = (tree_root.get("slug") or "").strip()
    if len(segments) == 1 and segments[0] == root_slug:
        return tree_root
    cur: dict = tree_root
    start_idx = 1 if segments and segments[0] == root_slug else 0
    for idx in range(start_idx, len(segments)):
        seg = segments[idx]
        children = cur.get("children") or []
        nxt: dict | None = None
        for ch in children:
            if isinstance(ch, dict) and (ch.get("slug") or "").strip() == seg:
                nxt = ch
                break
        if nxt is None:
            return None
        cur = nxt
    return cur


def display_name_for_slug_prefix(tree_root: dict, segments_prefix: list[str]) -> str:
    node = find_tree_node_for_slug_path(tree_root, segments_prefix)
    if node:
        label = (node.get("displayName") or node.get("title") or "").strip()
        if label.startswith("Category:"):
            label = label[9:].strip()
        if label:
            return label
    seg = segments_prefix[-1] if segments_prefix else ""
    if seg == UNSORTED_SEGMENT:
        return "Unsorted"
    if not seg:
        return "Content"
    return seg.replace("-", " ").replace("_", " ").title()


def build_content_mirror_breadcrumb_nav_html(
    category_path: str,
    page_title_plain: str,
    *,
    tree: dict | None = None,
    root: Path | None = None,
) -> str:
    """
    Breadcrumb for mirrored wiki pages: Home → Content tree (links to /all-pages#…) → page title.

    Matches all-pages/tree.js: root label links to /all-pages; each category segment gets a hash link.
    """
    tree_root = tree if tree is not None else load_tree(root)
    parts = [p for p in (category_path or "").strip("/").split("/") if p]
    title_esc = html.escape(page_title_plain.strip() or "Page", quote=False)
    root_display = (tree_root.get("displayName") or tree_root.get("title") or "Content").strip()
    if root_display.startswith("Category:"):
        root_display = root_display[9:].strip()
    root_display_esc = html.escape(root_display or "Content", quote=False)

    lines = [
        '<nav class="wiki-char-breadcrumb" aria-label="Breadcrumb">',
        '  <a href="/">Home</a>',
        '  <span aria-hidden="true">/</span>',
        f'  <a href="/all-pages">{root_display_esc}</a>',
    ]
    root_slug = (tree_root.get("slug") or "").strip()
    # Skip first slug when it is the tree root (e.g. content): avoids "Content / Content / …"
    start_i = 1 if parts and parts[0] == root_slug else 0
    for i in range(start_i, len(parts)):
        prefix = parts[: i + 1]
        label_esc = html.escape(display_name_for_slug_prefix(tree_root, prefix), quote=False)
        hash_path = all_pages_nav_hash_path(tree_root, prefix)
        lines.append('  <span aria-hidden="true">/</span>')
        lines.append(f'  <a href="/all-pages{hash_path}">{label_esc}</a>')
    lines.append('  <span aria-hidden="true">/</span>')
    lines.append(f'  <span>{title_esc}</span>')
    lines.append("</nav>")
    lines.append(f'<h1 class="visually-hidden">{title_esc}</h1>')
    raw = "\n".join(lines)
    return textwrap.indent(raw, "          ")
