#!/usr/bin/env python3
"""Patch wiki page inline lightbox click handlers to open the viewer for thumb images too."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

OLD = """          pageRoot.addEventListener("click", function (e) {
            var a = e.target.closest("a.image.lightbox");
            if (!a && e.target.closest("aside.portable-infobox")) {
              a = e.target.closest("aside.portable-infobox figure.pi-image a.image");
            }
            if (!a || !pageRoot.contains(a)) return;
            var im = a.querySelector("img[src]");
            if (!im) return;
            var s = im.getAttribute("src") || "";
            if (!s || s.indexOf("data:") === 0) return;
            e.preventDefault();
            e.stopPropagation();
            openAt(im);
          });"""

NEW = """          function resolveLightboxImage(e) {
            if (e.target.closest("a.info-icon")) return null;
            var t = e.target;
            var a = t.closest("a.image.lightbox");
            if (!a && t.closest("aside.portable-infobox")) {
              a = t.closest("aside.portable-infobox figure.pi-image a.image");
            }
            if (!a) a = t.closest(".wiki-import a.image");
            if (!a) a = t.closest(".wiki-import a.mw-file-description");
            var im = null;
            if (a && pageRoot.contains(a)) {
              im = a.querySelector("img[src]");
            } else {
              im = t.closest(".wiki-import img[src]");
            }
            if (!im || !pageRoot.contains(im)) return null;
            if (im.closest(".wiki-lightbox") || im.closest(".wiki-lightbox-thumbs") || im.closest("noscript")) {
              return null;
            }
            var s = im.getAttribute("src") || "";
            if (!s || s.indexOf("data:") === 0) return null;
            return im;
          }

          pageRoot.addEventListener("click", function (e) {
            var im = resolveLightboxImage(e);
            if (!im) return;
            e.preventDefault();
            e.stopPropagation();
            openAt(im);
          });"""


def main() -> None:
    patched = 0
    skipped = 0
    for path in ROOT.rglob("index.html"):
        if path.parts[-2] in {".git", "node_modules"}:
            continue
        text = path.read_text(encoding="utf-8")
        if 'getElementById("wiki-lightbox")' not in text:
            continue
        if OLD not in text:
            if "resolveLightboxImage" in text:
                skipped += 1
            continue
        path.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
        patched += 1
    print(f"Patched {patched} files ({skipped} already patched)")


if __name__ == "__main__":
    main()
