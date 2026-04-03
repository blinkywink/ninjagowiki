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

    fetch("/assets/data/characters.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!data || !Array.isArray(data.characters)) return;
        const map = localCharacterHrefMap(data.characters);
        items = applyLocalCharacterHrefs(domItems, map);
        if (searchInput.value.trim()) renderResults(searchInput.value);
      })
      .catch(() => {});

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

      const scored = items
        .map((it) => {
          const idx = it.haystack.indexOf(qFold);
          const score = idx === -1 ? 0 : 1000 - idx;
          return { ...it, score };
        })
        .filter((x) => x.score > 0)
        .sort((a, b) => b.score - a.score)
        .slice(0, 3);

      if (scored.length === 0) {
        const empty = document.createElement("div");
        empty.className = "result result--empty";
        empty.innerHTML = `<span>Nothing matched.</span><small>Try another name (Lloyd, Nya, Codex...)</small>`;
        resultsEl.appendChild(empty);
        return;
      }

      for (const it of scored) {
        const thumbSrc = escapeAttr(thumbForAnchor(it.anchor));
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

    /** Match query against display name: full string prefix, or any word prefix (e.g. "wu" → Master Wu). */
    const nameMatchesPrefix = (c, qFold) => {
      if (!qFold) return false;
      const full = foldSearch(c.display);
      if (full.startsWith(qFold)) return true;
      const words = String(c.display)
        .toLowerCase()
        .split(/[^a-z0-9.]+/)
        .filter(Boolean);
      return words.some((w) => foldSearch(w).startsWith(qFold));
    };

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
      matches.sort((a, b) => a.display.localeCompare(b.display, undefined, { sensitivity: "base" }));
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

  function escapeHtml(s) {
    return String(s).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  }
  function escapeAttr(s) {
    return escapeHtml(s).replaceAll("`", "&#096;");
  }
})();

