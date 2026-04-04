(() => {
  /** Collapse punctuation/spaces so "pixal" matches "P.I.X.A.L." / "p i x a l". */
  const foldSearch = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]/g, "");

  const searchInput = document.getElementById("search-input");
  const searchClear = document.getElementById("search-clear");
  const resultsEl = document.getElementById("search-results");
  const tagButtons = Array.from(document.querySelectorAll(".tag"));
  const trendingLinks = Array.from(document.querySelectorAll(".article-list a[data-tags]"));

  if (searchInput && resultsEl) {
    /** `/characters/slug` article pages — override index.html `#anchor` links from characters.json */
    const localCharacterHrefRe = /^\/characters\/[a-z0-9-]+\/?$/i;

    const localCharacterHrefMap = (characters) => {
      const map = new Map();
      for (const c of characters || []) {
        const href = String(c.href || "")
          .trim()
          .split("?")[0];
        if (!localCharacterHrefRe.test(href)) continue;
        const add = (folded) => {
          if (folded && !map.has(folded)) map.set(folded, href);
        };
        add(foldSearch(c.display));
        add(foldSearch(c.slug));
      }
      return map;
    };

    const applyLocalCharacterHrefs = (domItems, hrefMap) =>
      domItems.map((it) => {
        const href = hrefMap.get(foldSearch(it.label));
        return href ? { ...it, url: href } : it;
      });

    const thumbMedia = window.matchMedia("(max-width: 859px)");
    const defaultSearchThumb = () =>
      thumbMedia.matches ? "/assets/hero-mobile.png" : "/assets/hero.png";

    const thumbForAnchor = (anchor) => {
      const explicit = anchor.getAttribute("data-search-thumb");
      if (explicit) return explicit;
      const img = anchor.querySelector("img");
      if (img) {
        const s = img.currentSrc || img.src;
        if (s) return s;
      }
      return defaultSearchThumb();
    };

    const thumbForItem = (it) => {
      if (it.searchThumb) return it.searchThumb;
      if (it.anchor) return thumbForAnchor(it.anchor);
      return defaultSearchThumb();
    };

    const mergeWikiPagesIntoItems = (baseItems, wikiManifest) => {
      const rows = wikiManifest && Array.isArray(wikiManifest.pages) ? wikiManifest.pages : [];
      const extra = rows
        .map((p) => {
          const url = String(p.href || "")
            .trim()
            .split("?")[0];
          const label = String(p.display || p.wikiTitle || "").trim() || "Wiki page";
          const keywords = String(p.keywords || label).toLowerCase();
          const haystack = foldSearch(`${keywords} ${label}`);
          const st = String(p.thumb || "").trim();
          return {
            url,
            keywords,
            label,
            haystack,
            anchor: null,
            searchThumb: st || undefined,
          };
        })
        .filter((x) => x.url && x.haystack);
      return baseItems.concat(extra);
    };

    const domItems = Array.from(document.querySelectorAll('a[data-search], a[data-tags]'))
      .map((a) => {
        const url = a.getAttribute("href") || "";
        const raw = (a.getAttribute("data-search") || a.getAttribute("data-tags") || "").trim();
        const keywords = raw.toLowerCase();
        const label = a.querySelector(".article-name")?.textContent?.trim()
          || a.querySelector(".card-title")?.textContent?.trim()
          || a.textContent?.trim()
          || "Open page";
        const haystack = foldSearch(`${raw} ${label}`);
        return { url, keywords, label, haystack, anchor: a };
      })
      .filter((x) => x.url && x.haystack);

    let items = domItems;

    Promise.all([
      fetch("/assets/data/characters.json")
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
      fetch("/assets/data/wiki_pages.json")
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
    ])
      .then(([charData, wikiData]) => {
        let next = domItems;
        if (charData && Array.isArray(charData.characters)) {
          const map = localCharacterHrefMap(charData.characters);
          next = applyLocalCharacterHrefs(domItems, map);
        }
        next = mergeWikiPagesIntoItems(next, wikiData);
        items = next;
        if (searchInput.value.trim()) renderResults(searchInput.value);
      })
      .catch(() => {});

    /**
     * Rank for homepage search: visible label / word prefixes first, then keyword prefixes,
     * then loose substring on folded keywords+label (old behavior).
     * `tier` higher = better; `sub` / `idx` are tie-breakers within tier.
     */
    const computeSearchRank = (it, qFold) => {
      const labelFold = foldSearch(it.label);
      const kwFold = foldSearch(it.keywords);

      if (labelFold.startsWith(qFold)) {
        return { tier: 100, sub: 0, idx: 0 };
      }

      const labelWords = String(it.label)
        .toLowerCase()
        .split(/[^a-z0-9.]+/)
        .filter(Boolean);
      for (let i = 0; i < labelWords.length; i++) {
        if (foldSearch(labelWords[i]).startsWith(qFold)) {
          return { tier: 90, sub: i, idx: 0 };
        }
      }

      if (kwFold.startsWith(qFold)) {
        return { tier: 70, sub: 0, idx: 0 };
      }

      const kwWords = String(it.keywords)
        .toLowerCase()
        .split(/[^a-z0-9.]+/)
        .filter(Boolean);
      for (let i = 0; i < kwWords.length; i++) {
        if (foldSearch(kwWords[i]).startsWith(qFold)) {
          return { tier: 65, sub: i, idx: 0 };
        }
      }

      const idx = it.haystack.indexOf(qFold);
      if (idx === -1) return { tier: 0, sub: 0, idx: 0 };
      return { tier: 20, sub: 0, idx };
    };

    const compareSearchRank = (a, b) => {
      const ra = a.rank;
      const rb = b.rank;
      if (rb.tier !== ra.tier) return rb.tier - ra.tier;
      if (ra.tier === 20) {
        if (ra.idx !== rb.idx) return ra.idx - rb.idx;
      } else if (ra.sub !== rb.sub) {
        return ra.sub - rb.sub;
      }
      return a.label.localeCompare(b.label, undefined, { sensitivity: "base" });
    };

    const renderResults = (query) => {
      const rawQ = query.trim();
      resultsEl.innerHTML = "";
      if (!rawQ) return;

      const qFold = foldSearch(rawQ);
      if (!qFold) {
        const empty = document.createElement("div");
        empty.className = "result result--empty";
        empty.innerHTML = "<span>Nothing matched.</span><small>Use letters or numbers in your search.</small>";
        resultsEl.appendChild(empty);
        return;
      }

      const MAX_RESULTS = 3;

      const ranked = items
        .map((it) => ({ ...it, rank: computeSearchRank(it, qFold) }))
        .filter((x) => x.rank.tier > 0)
        .sort(compareSearchRank)
        .slice(0, MAX_RESULTS);

      if (ranked.length === 0) {
        const empty = document.createElement("div");
        empty.className = "result result--empty";
        empty.innerHTML = `<span>Nothing matched.</span><small>Try another name (Lloyd, Nya, Codex...)</small>`;
        resultsEl.appendChild(empty);
        return;
      }

      for (const it of ranked) {
        const thumbSrc = escapeAttr(thumbForItem(it));
        const row = document.createElement("a");
        row.className = "result result-row";
        row.href = it.url;
        row.innerHTML = `
          <span class="result-thumb" aria-hidden="true"><img src="${thumbSrc}" alt="" width="48" height="48" decoding="async" /></span>
          <span class="result-main">
            <span class="result-title">${escapeHtml(it.label)}</span>
            <small>${escapeHtml(it.keywords.slice(0, 60))}${it.keywords.length > 60 ? "..." : ""}</small>
          </span>
        `;
        resultsEl.appendChild(row);
      }
    };

    const onClear = () => {
      searchInput.value = "";
      resultsEl.innerHTML = "";
      searchInput.focus();
    };

    const onInput = () => renderResults(searchInput.value);

    searchInput.addEventListener("input", onInput, { passive: true });
    if (searchClear) searchClear.addEventListener("click", onClear);
  }

  if (tagButtons.length) {
    let activeTag = null;

    const applyFilter = (tag) => {
      activeTag = tag;
      tagButtons.forEach((b) => b.classList.toggle("is-active", b.dataset.tag === tag));

      trendingLinks.forEach((a) => {
        const tags = (a.getAttribute("data-tags") || "").toLowerCase();
        const ok = !tag || tags.includes(tag);
        a.closest("li").style.display = ok ? "" : "none";
      });
    };

    for (const btn of tagButtons) {
      btn.addEventListener("click", () => {
        const tag = btn.dataset.tag;
        applyFilter(activeTag === tag ? null : tag);
      });
    }
  }

  // Characters page: merged wiki chart groups + search (see character_groups.json).
  const charactersSearch = document.getElementById("characters-search");
  const charactersGrid = document.getElementById("characters-grid");
  const loadStatusEl = document.getElementById("characters-load-status");
  const browseRootEl = document.getElementById("characters-browse-root");
  const searchPanelEl = document.getElementById("characters-search-panel");
  const searchNoteEl = document.getElementById("characters-search-note");

  if (charactersSearch && charactersGrid && loadStatusEl && browseRootEl && searchPanelEl) {
    let manifest = [];
    let searchMode = false;

    const CAT_ORDER = ["Heroes", "Allies", "Villains", "Creatures", "Other"];

    /**
     * How well the display name matches a prefix query (higher = show first).
     * 100 = folded full name starts with query (Lloyd, Lord Garmadon for "l").
     * 90 = first word only (after stripping punctuation).
     * 70 = a later word only (e.g. "Life" in Arc Dragon of Life — still findable, but below real L… names).
     */
    const charDisplaySearchRank = (c, qFold) => {
      if (!qFold) return 0;
      const full = foldSearch(c.display);
      if (full.startsWith(qFold)) return 100;
      const words = String(c.display)
        .toLowerCase()
        .split(/[^a-z0-9.]+/)
        .filter(Boolean);
      if (!words.length) return 0;
      if (foldSearch(words[0]).startsWith(qFold)) return 90;
      if (words.slice(1).some((w) => foldSearch(w).startsWith(qFold))) return 70;
      return 0;
    };

    const nameMatchesPrefix = (c, qFold) => charDisplaySearchRank(c, qFold) > 0;

    const slugifyWikiTitle = (title) =>
      String(title)
        .toLowerCase()
        .replace(/[^\w\s-]/g, "")
        .replace(/[-\s]+/g, "-")
        .replace(/^-|-$/g, "") || "x";

    const findInManifest = (wikiTitle) => {
      const t = String(wikiTitle).trim();
      for (const c of manifest) {
        if (c.display === t) return c;
      }
      const tf = foldSearch(t);
      for (const c of manifest) {
        if (foldSearch(c.display) === tf) return c;
      }
      const wantSlug = slugifyWikiTitle(t);
      for (const c of manifest) {
        if (c.slug === wantSlug) return c;
      }
      return null;
    };

    const applyCharImgSrc = (img) => {
      const fixed = (img.getAttribute("data-card-image") || "").trim();
      const media = window.matchMedia("(max-width: 859px)");
      const fallback = media.matches ? "/assets/hero-mobile.png" : "/assets/hero.png";
      img.src = fixed || fallback;
    };

    const makeCharCard = (c) => {
      const a = document.createElement("a");
      a.className = "char-card";
      a.id = c.slug;
      a.href = c.href || c.wikiUrl;
      a.setAttribute("data-filter", c.filter);
      const img = document.createElement("img");
      img.className = "char-img";
      img.alt = "";
      img.decoding = "async";
      img.loading = "lazy";
      img.setAttribute("data-card-image", c.img);
      applyCharImgSrc(img);
      const nm = document.createElement("div");
      nm.className = "char-name";
      nm.textContent = c.display;
      a.appendChild(img);
      a.appendChild(nm);
      return a;
    };

    const removeSearchCards = () => {
      charactersGrid.querySelectorAll(".char-card").forEach((el) => el.remove());
    };

    const exitSearchToBrowse = () => {
      searchMode = false;
      removeSearchCards();
      searchPanelEl.hidden = true;
      browseRootEl.hidden = false;
      loadStatusEl.textContent = "";
      if (searchNoteEl) {
        searchNoteEl.hidden = true;
        searchNoteEl.textContent = "";
      }
    };

    const runCharSearch = (qFold) => {
      searchMode = true;
      browseRootEl.hidden = true;
      searchPanelEl.hidden = false;
      if (searchNoteEl) {
        searchNoteEl.hidden = true;
        searchNoteEl.textContent = "";
      }
      removeSearchCards();
      const matches = manifest.filter((c) => nameMatchesPrefix(c, qFold));
      matches.sort((a, b) => {
        const ra = charDisplaySearchRank(a, qFold);
        const rb = charDisplaySearchRank(b, qFold);
        if (rb !== ra) return rb - ra;
        return a.display.localeCompare(b.display, undefined, { sensitivity: "base" });
      });
      const frag = document.createDocumentFragment();
      for (const c of matches) {
        frag.appendChild(makeCharCard(c));
      }
      charactersGrid.appendChild(frag);
      loadStatusEl.textContent = "";
    };

    const scrollToHash = () => {
      const h = decodeURIComponent((location.hash || "").slice(1));
      if (!h) return;
      document.getElementById(h)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    };

    const mergeGroupsClient = (nj, dr) => {
      const out = {};
      for (const cat of CAT_ORDER) {
        const seen = new Set();
        const list = [];
        for (const name of [...(nj[cat] || []), ...(dr[cat] || [])]) {
          const n = String(name).trim();
          if (!n) continue;
          const low = n.toLowerCase();
          if (seen.has(low)) continue;
          seen.add(low);
          list.push(n);
        }
        out[cat] = list;
      }
      return out;
    };

    const buildMergedBrowse = (groupsData) => {
      browseRootEl.innerHTML = "";
      let merged =
        groupsData &&
        (groupsData.merged ||
          (groupsData.ninjago && groupsData.dragonsRising
            ? mergeGroupsClient(groupsData.ninjago, groupsData.dragonsRising)
            : null));
      if (!merged || typeof merged !== "object") {
        browseRootEl.innerHTML =
          '<p class="characters-browse-empty">Could not load character groups. Try refreshing.</p>';
        return;
      }

      for (const cat of CAT_ORDER) {
        const names = merged[cat];
        if (!names || !names.length) continue;

        const section = document.createElement("section");
        section.className = "char-group";
        const h2 = document.createElement("h2");
        h2.className = "char-group-title";
        h2.textContent = cat;

        const grid = document.createElement("div");
        grid.className = "characters-grid characters-grid--group";
        grid.setAttribute("aria-label", `${cat}`);

        const entries = names
          .map((wikiTitle) => ({ c: findInManifest(wikiTitle) }))
          .filter((e) => e.c);
        entries.sort((a, b) =>
          a.c.display.localeCompare(b.c.display, undefined, { sensitivity: "base" }),
        );

        if (!entries.length) continue;

        for (const { c } of entries) {
          grid.appendChild(makeCharCard(c));
        }

        section.appendChild(h2);
        section.appendChild(grid);
        browseRootEl.appendChild(section);
      }
    };

    charactersSearch.addEventListener(
      "input",
      () => {
        const raw = String(charactersSearch.value || "").trim();
        if (!raw) {
          exitSearchToBrowse();
          return;
        }
        const qFold = foldSearch(raw);
        if (!qFold) {
          exitSearchToBrowse();
          if (searchNoteEl) {
            searchNoteEl.hidden = false;
            searchNoteEl.textContent = "Use letters or numbers in your search.";
          }
          return;
        }
        if (searchNoteEl) {
          searchNoteEl.hidden = true;
          searchNoteEl.textContent = "";
        }
        runCharSearch(qFold);
      },
      { passive: true },
    );

    fetch("/assets/data/characters.json")
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((data) => {
        manifest = data.characters || [];
        if (!manifest.length) {
          browseRootEl.innerHTML =
            '<p class="characters-browse-empty">No character data.</p>';
          return;
        }
        return fetch("/assets/data/character_groups.json")
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null)
          .then((groupsData) => {
            buildMergedBrowse(groupsData);
            browseRootEl.hidden = false;
            searchPanelEl.hidden = true;
            scrollToHash();
            window.addEventListener("hashchange", () => {
              if (!String(charactersSearch.value || "").trim()) scrollToHash();
            });
          });
      })
      .catch(() => {
        browseRootEl.innerHTML =
          '<p class="characters-browse-empty">Could not load characters. Try refreshing.</p>';
      });
  }

  // Homepage simple cards: root-absolute fallbacks (narrow = mobile hero art).
  const simpleCardImages = Array.from(document.querySelectorAll(".simple-card-img"));
  if (simpleCardImages.length) {
    const media = window.matchMedia("(max-width: 859px)");
    const applySimpleCardImages = () => {
      const fallback = media.matches ? "/assets/hero-mobile.png" : "/assets/hero.png";
      for (const img of simpleCardImages) {
        const fixed = (img.getAttribute("data-card-image") || "").trim();
        img.src = fixed || fallback;
      }
    };
    applySimpleCardImages();
    media.addEventListener?.("change", applySimpleCardImages);
  }

  // If mobile menu is open and user taps a nav link, close it.
  const nav = document.querySelector(".nav");
  const toggle = document.getElementById("menu-toggle");
  if (nav && toggle) {
    nav.addEventListener("click", (e) => {
      const target = e.target;
      if (target && target.tagName === "A") toggle.checked = false;
    });
  }

  // Character articles: on refresh, keep scroll position instead of jumping back to an old #hash.
  const wikiCharMain = document.querySelector("main.wiki-char-page");
  if (wikiCharMain) {
    const scrollKey = () => `wikiCharScrollY:${location.pathname}${location.search}`;

    window.addEventListener("pagehide", () => {
      try {
        sessionStorage.setItem(scrollKey(), String(window.scrollY));
      } catch {
        /* ignore quota / private mode */
      }
    });

    const isReloadNavigation = () => {
      const nav = performance.getEntriesByType?.("navigation")?.[0];
      if (nav && "type" in nav) return nav.type === "reload";
      try {
        return performance.navigation?.type === 1;
      } catch {
        return false;
      }
    };

    const applyReloadScrollRestore = () => {
      if (!isReloadNavigation()) return;
      let raw;
      try {
        raw = sessionStorage.getItem(scrollKey());
      } catch {
        return;
      }
      if (raw == null) return;
      const y = Number.parseInt(raw, 10);
      if (Number.isNaN(y) || y < 0) return;

      const scrollAndStripHash = () => {
        window.scrollTo(0, y);
        const h = location.hash;
        const keepWikiTabHash = /^#tab-(overview|history|relationships|gallery)$/.test(h);
        if (h && !keepWikiTabHash) {
          try {
            history.replaceState(null, "", `${location.pathname}${location.search}`);
          } catch {
            /* ignore */
          }
        }
      };

      scrollAndStripHash();
      requestAnimationFrame(() => {
        scrollAndStripHash();
        setTimeout(scrollAndStripHash, 50);
      });
    };

    window.addEventListener("pageshow", (e) => {
      if (e.persisted) return;
      applyReloadScrollRestore();
    });

    /* Mobile only: expand the <details> that contains a hash target. Desktop: always expanded (flat article). */
    const mqMobile = window.matchMedia("(max-width: 899px)");
    const mqDesktop = window.matchMedia("(min-width: 900px)");
    const overviewMsections = () =>
      document.querySelectorAll(
        ".wiki-char-overview-prose details.wiki-char-msection, .wiki-char-msection-prose details.wiki-char-msection",
      );

    const setAllMsectionsOpenForDesktop = () => {
      if (!mqDesktop.matches) return;
      for (const det of overviewMsections()) {
        det.open = true;
      }
    };

    const openOverviewDetailsForHash = () => {
      if (!mqMobile.matches || !location.hash) return;
      let id;
      try {
        id = decodeURIComponent(location.hash.slice(1));
      } catch {
        return;
      }
      if (!id) return;
      const el = document.getElementById(id);
      if (!el) return;
      const det = el.closest("details.wiki-char-msection");
      if (det) det.open = true;
    };

    setAllMsectionsOpenForDesktop();
    if (mqDesktop.addEventListener) {
      mqDesktop.addEventListener("change", setAllMsectionsOpenForDesktop);
    } else if (mqDesktop.addListener) {
      mqDesktop.addListener(setAllMsectionsOpenForDesktop);
    }

    window.addEventListener("hashchange", openOverviewDetailsForHash);
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", () => {
        setAllMsectionsOpenForDesktop();
        openOverviewDetailsForHash();
      });
    } else {
      openOverviewDetailsForHash();
    }
  }

  /** Rewrite Fandom /wiki/… links to /characters/slug when we host that character (same rules as the Python rewriter). */
  const WIKI_SKIP_PREFIXES = [
    "/wiki/special:",
    "/wiki/file:",
    "/wiki/category:",
    "/wiki/template:",
    "/wiki/user:",
    "/wiki/talk:",
    "/wiki/mediawiki:",
    "/wiki/help:",
    "/wiki/ninjago:",
  ];

  const wikiPathToLocalHref = (characters) => {
    const map = new Map();
    const localRe = /^\/characters\/[a-z0-9-]+\/?$/i;
    for (const c of characters || []) {
      const local = String(c.href || "")
        .trim()
        .split("#")[0]
        .split("?")[0];
      if (!localRe.test(local)) continue;
      const wu = String(c.wikiUrl || "").trim();
      if (!wu) continue;
      let path;
      try {
        const u = new URL(wu);
        if (!/ninjago\.fandom\.com$/i.test(u.hostname)) continue;
        path = decodeURIComponent(u.pathname).replace(/\/$/, "").toLowerCase();
      } catch {
        continue;
      }
      if (!path.startsWith("/wiki/")) continue;
      if (WIKI_SKIP_PREFIXES.some((p) => path.startsWith(p))) continue;
      const parts = path.split("/").filter(Boolean);
      if (parts.length !== 2 || parts[0] !== "wiki") continue;
      map.set(path, local);
      map.set(path.replace(/ /g, "_"), local);
      map.set(path.replace(/_/g, " "), local);
    }
    return map;
  };

  const fixFandomCharacterAnchors = (root) => {
    if (!root) return;
    fetch("/assets/data/characters.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!data || !Array.isArray(data.characters)) return;
        const pathMap = wikiPathToLocalHref(data.characters);
        root.querySelectorAll('a[href*="ninjago.fandom.com/wiki/"]').forEach((a) => {
          const raw = a.getAttribute("href");
          if (!raw) return;
          let u;
          try {
            u = new URL(raw);
          } catch {
            return;
          }
          if (!/ninjago\.fandom\.com$/i.test(u.hostname)) return;
          let path = decodeURIComponent(u.pathname).replace(/\/$/, "").toLowerCase();
          if (!path.startsWith("/wiki/")) return;
          if (WIKI_SKIP_PREFIXES.some((p) => path.startsWith(p))) return;
          const parts = path.split("/").filter(Boolean);
          if (parts.length !== 2 || parts[0] !== "wiki") return;
          const local =
            pathMap.get(path) || pathMap.get(path.replace(/ /g, "_")) || pathMap.get(path.replace(/_/g, " "));
          if (!local) return;
          const frag = u.hash || "";
          a.setAttribute("href", local + frag);
        });
      })
      .catch(() => {});
  };

  fixFandomCharacterAnchors(document.body);

  function escapeHtml(s) {
    return String(s).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  }
  function escapeAttr(s) {
    return escapeHtml(s).replaceAll("`", "&#096;");
  }
})();

