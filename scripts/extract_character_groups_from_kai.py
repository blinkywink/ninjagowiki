#!/usr/bin/env python3
"""Parse Ninjago + Dragons Rising navbox tables from characters/kai/index.html → character_groups.json."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KAI = ROOT / "characters" / "kai" / "index.html"
OUT = ROOT / "assets" / "data" / "character_groups.json"

CAT_ORDER = ["Heroes", "Allies", "Villains", "Creatures", "Other"]


def merge_categories(nj: dict[str, list[str]], dr: dict[str, list[str]]) -> dict[str, list[str]]:
    """Ninjago first, then Dragons Rising; drop duplicates (case-insensitive)."""
    merged: dict[str, list[str]] = {}
    for key in CAT_ORDER:
        seen: set[str] = set()
        out: list[str] = []
        for name in nj.get(key, []) + dr.get(key, []):
            n = name.strip()
            if not n:
                continue
            low = n.casefold()
            if low in seen:
                continue
            seen.add(low)
            out.append(n)
        merged[key] = out
    return merged


def extract_names(cell_html: str) -> list[str]:
    names: list[str] = []
    for m in re.finditer(r'<a\b[^>]*\btitle="([^"]+)"', cell_html):
        t = m.group(1).replace("&#39;", "'").replace("&amp;", "&")
        names.append(t)
    for m in re.finditer(
        r'<strong[^>]*class="[^"]*mw-selflink[^"]*"[^>]*>([^<]+)</strong>',
        cell_html,
        re.I,
    ):
        names.append(m.group(1).strip())
    # de-dupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def parse_table(html: str, font: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for m in re.finditer(
        rf'<span style="color:white; font-family:{re.escape(font)}">([^<]+)</span>\s*</td>\s*<td[^>]*>(.*?)</td>\s*</tr>',
        html,
        re.DOTALL | re.IGNORECASE,
    ):
        label = m.group(1).strip()
        body = m.group(2)
        rows[label] = extract_names(body)
    return rows


def main() -> None:
    raw = KAI.read_text(encoding="utf-8", errors="replace")
    i0 = raw.find('<th colspan="2" bgcolor="#162e43"')
    i1 = raw.find('<th colspan="2" bgcolor="orange"')
    if i0 == -1 or i1 == -1:
        raise SystemExit("Could not find navbox tables in kai/index.html")
    ninjago_html = raw[i0:i1]
    i2 = raw.find("</tbody></table>", i1)
    if i2 == -1:
        raise SystemExit("Could not find end of Dragons Rising table")
    dr_html = raw[i1 : i2 + len("</tbody></table>")]

    ninjago = parse_table(ninjago_html, "Kunoichi")
    dragons_rising = parse_table(dr_html, "DragonsRising")
    merged = merge_categories(ninjago, dragons_rising)
    data = {
        "v": 2,
        "ninjago": ninjago,
        "dragonsRising": dragons_rising,
        "merged": merged,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Wrote {OUT} — merged categories: "
        + ", ".join(f"{k}={len(merged[k])}" for k in CAT_ORDER)
    )


if __name__ == "__main__":
    main()
