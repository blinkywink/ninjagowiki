(() => {
  /** Collapse punctuation/spaces so "pixal" matches "P.I.X.A.L." / "p i x a l". */
  const foldSearch = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]/g, "");

  /** Fandom wiki placeholder — same as mirrored article infoboxes when no image exists. */
  const NO_IMAGE_PLACEHOLDER =
    "https://static.wikia.nocookie.net/ninjago/images/8/84/Noimage.jpg/revision/latest/scale-to-width-down/450?cb=20260319010138";
  const SITE_HERO_THUMBS = new Set(["/assets/hero.png", "/assets/hero-mobile.png"]);

  /** Browse-card image: never fall back to site hero art. */
  const cardImageSrc = (raw) => {
    const s = String(raw || "").trim();
    if (!s || SITE_HERO_THUMBS.has(s)) return NO_IMAGE_PLACEHOLDER;
    return s;
  };

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

    const GENERIC_SEARCH_THUMBS = new Set([
      "/assets/hero.png",
      "/assets/hero-mobile.png",
    ]);

    const isRealSearchThumb = (u) => {
      const s = String(u || "").trim();
      if (!s || GENERIC_SEARCH_THUMBS.has(s)) return false;
      if (/noimage/i.test(s)) return false;
      return true;
    };

    const wikiExcludedFromSearch = (p) => {
      const t = String(p.wikiTitle || p.display || "").toLowerCase();
      if (t.includes("disambiguation")) return true;
      const s = String(p.slug || "").toLowerCase();
      if (s.includes("disambiguation")) return true;
      return false;
    };

    const thumbForAnchor = (anchor) => {
      const explicit = anchor.getAttribute("data-search-thumb");
      if (explicit && isRealSearchThumb(explicit)) return explicit;
      const img = anchor.querySelector("img");
      if (img) {
        const s = img.currentSrc || img.src;
        if (s && isRealSearchThumb(s)) return s;
      }
      return "";
    };

    const thumbForItem = (it) => {
      if (isRealSearchThumb(it.searchThumb)) return it.searchThumb;
      if (it.anchor) return thumbForAnchor(it.anchor);
      return "";
    };

    const mergeWikiPagesIntoItems = (baseItems, wikiManifest) => {
      const rows = wikiManifest && Array.isArray(wikiManifest.pages) ? wikiManifest.pages : [];
      const extra = rows
        .filter((p) => !wikiExcludedFromSearch(p))
        .map((p) => {
          const url = String(p.href || "")
            .trim()
            .split("?")[0];
          const label = String(p.display || p.wikiTitle || "").trim() || "Wiki page";
          const keywords = String(p.keywords || label).toLowerCase();
          const subtitle = String(p.searchExcerpt || "").trim();
          const haystack = foldSearch(`${keywords} ${label} ${subtitle}`);
          const st = String(p.thumb || "").trim();
          return {
            url,
            keywords,
            label,
            haystack,
            anchor: null,
            searchThumb: isRealSearchThumb(st) ? st : undefined,
            searchSubtitle: subtitle,
          };
        })
        .filter((x) => x.url && x.haystack);
      return baseItems.concat(extra);
    };

    const mergeCharacterSearchRows = (baseItems, rows) => {
      const list = Array.isArray(rows) ? rows : [];
      const extra = list
        .filter((c) => {
          const slug = String(c.slug || "").toLowerCase();
          const label = String(c.display || c.wikiTitle || "").toLowerCase();
          return !slug.includes("disambiguation") && !label.includes("disambiguation");
        })
        .map((c) => {
          const url = String(c.href || "")
            .trim()
            .split("?")[0];
          const label = String(c.display || c.wikiTitle || "").trim() || "Character";
          const keywords = String(c.keywords || c.filter || label).toLowerCase();
          const subtitle = String(c.searchExcerpt || "").trim();
          const haystack = foldSearch(`${keywords} ${label} ${subtitle}`);
          const st = String(c.thumb || "").trim();
          return {
            url,
            keywords,
            label,
            haystack,
            anchor: null,
            searchThumb: isRealSearchThumb(st) ? st : undefined,
            searchSubtitle: subtitle,
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
      fetch("/assets/data/wiki_search_index.json")
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
      fetch("/assets/data/wiki_pages.json")
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null),
    ])
      .then(([charData, wikiSearch, wikiFull]) => {
        const packPages =
          wikiSearch && Array.isArray(wikiSearch.pages) && wikiSearch.pages.length
            ? wikiSearch.pages
            : wikiFull && Array.isArray(wikiFull.pages)
              ? wikiFull.pages
              : [];
        const charSearchRows =
          wikiSearch && Array.isArray(wikiSearch.characters) ? wikiSearch.characters : [];

        let next = [];
        next = mergeCharacterSearchRows(next, charSearchRows);
        next = mergeWikiPagesIntoItems(next, { pages: packPages });

        if (charData && Array.isArray(charData.characters)) {
          const map = localCharacterHrefMap(charData.characters);
          next = applyLocalCharacterHrefs(next, map);
        }

        const jsonUrls = new Set(next.map((x) => String(x.url || "").split("?")[0]));
        const domExtra = domItems.filter((it) => {
          const u = String(it.url || "").split("?")[0];
          return u && !jsonUrls.has(u);
        });
        items = next.concat(domExtra);

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

      const maxResults = 3;

      const ranked = items
        .map((it) => ({ ...it, rank: computeSearchRank(it, qFold) }))
        .filter((x) => x.rank.tier > 0)
        .sort(compareSearchRank)
        .slice(0, maxResults);

      if (ranked.length === 0) {
        const empty = document.createElement("div");
        empty.className = "result result--empty";
        empty.innerHTML = `<span>Nothing matched.</span><small>Try another name (Lloyd, Nya, Codex...)</small>`;
        resultsEl.appendChild(empty);
        return;
      }

      const subtitleForResult = (it) => {
        const raw =
          String(it.searchSubtitle || "").trim() || String(it.keywords || "").trim();
        return raw.slice(0, 400);
      };

      for (const it of ranked) {
        const thumbRaw = thumbForItem(it);
        const thumbOk = isRealSearchThumb(thumbRaw);
        const thumbSrc = thumbOk ? escapeAttr(thumbRaw) : "";
        const sub = subtitleForResult(it);
        const thumbBlock = thumbOk
          ? `<span class="result-thumb" aria-hidden="true"><img src="${thumbSrc}" alt="" width="48" height="48" decoding="async" loading="lazy" referrerpolicy="no-referrer" /></span>`
          : `<span class="result-thumb result-thumb--empty" aria-hidden="true"></span>`;
        const row = document.createElement("a");
        row.className = "result result-row";
        row.href = it.url;
        row.innerHTML = `
          ${thumbBlock}
          <span class="result-main">
            <span class="result-title">${escapeHtml(it.label)}</span>
            ${sub ? `<small class="result-subtitle">${escapeHtml(sub)}</small>` : ""}
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
      img.src = cardImageSrc(img.getAttribute("data-card-image"));
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

  // Episodes index: seasons from episodes_index.json (see scripts/build_episodes_index.py).
  const episodesSearch = document.getElementById("episodes-search");
  const episodesGrid = document.getElementById("episodes-grid");
  const episodesLoadStatus = document.getElementById("episodes-load-status");
  const episodesBrowseRoot = document.getElementById("episodes-browse-root");
  const episodesSearchPanel = document.getElementById("episodes-search-panel");
  const episodesSearchNote = document.getElementById("episodes-search-note");

  if (episodesSearch && episodesGrid && episodesLoadStatus && episodesBrowseRoot && episodesSearchPanel) {
    /** @type {{ display: string, href: string, slug: string, filter: string, img: string, codes?: string[] }[]} */
    let episodeManifest = [];

    /** Fold search text; normalize s01ep02 → s01e02 for episode-code queries. */
    const foldEpisodeQuery = (raw) => {
      let t = String(raw || "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]/g, "");
      if (!t) return "";
      return t.replace(/^s(\d+)ep(\d+)$/, "s$1e$2");
    };

    const epDisplaySearchRank = (display, qFold) => {
      if (!qFold) return 0;
      const full = foldSearch(display);
      if (full.startsWith(qFold)) return 100;
      const words = String(display)
        .toLowerCase()
        .split(/[^a-z0-9.]+/)
        .filter(Boolean);
      if (!words.length) return 0;
      if (foldSearch(words[0]).startsWith(qFold)) return 90;
      if (words.slice(1).some((w) => foldSearch(w).startsWith(qFold))) return 70;
      return 0;
    };

    const epMatchRank = (ep, qFold) => {
      const r = epDisplaySearchRank(ep.display, qFold);
      if (r) return r;
      const hay = foldSearch(`${ep.filter || ""} ${ep.display}`);
      if (hay.includes(qFold)) return 25;
      return 0;
    };

    const applyEpisodeImgSrc = (img) => {
      img.src = cardImageSrc(img.getAttribute("data-card-image"));
    };

    const makeEpisodeCard = (ep) => {
      const a = document.createElement("a");
      a.className = "char-card char-card--episode";
      if (ep.slug) a.id = ep.slug;
      a.href = ep.href;
      a.setAttribute("data-filter", ep.filter || ep.display);
      const img = document.createElement("img");
      img.className = "char-img";
      img.alt = "";
      img.decoding = "async";
      img.loading = "lazy";
      const im = (ep.img || "").trim();
      if (im.startsWith("http://") || im.startsWith("https://")) {
        img.referrerPolicy = "no-referrer";
      }
      img.setAttribute("data-card-image", im);
      applyEpisodeImgSrc(img);
      const nm = document.createElement("div");
      nm.className = "char-name";
      nm.textContent = ep.display;
      a.appendChild(img);
      a.appendChild(nm);
      return a;
    };

    const removeEpisodeSearchCards = () => {
      episodesGrid.querySelectorAll(".char-card").forEach((el) => el.remove());
    };

    const exitEpisodesSearchToBrowse = () => {
      removeEpisodeSearchCards();
      episodesSearchPanel.hidden = true;
      episodesBrowseRoot.hidden = false;
      episodesLoadStatus.textContent = "";
      if (episodesSearchNote) {
        episodesSearchNote.hidden = true;
        episodesSearchNote.textContent = "";
      }
    };

    const runEpisodeSearch = (qFold) => {
      episodesBrowseRoot.hidden = true;
      episodesSearchPanel.hidden = false;
      if (episodesSearchNote) {
        episodesSearchNote.hidden = true;
        episodesSearchNote.textContent = "";
      }
      removeEpisodeSearchCards();
      const matches = episodeManifest.filter((ep) => epMatchRank(ep, qFold) > 0);
      matches.sort((a, b) => {
        const ra = epMatchRank(a, qFold);
        const rb = epMatchRank(b, qFold);
        if (rb !== ra) return rb - ra;
        return a.display.localeCompare(b.display, undefined, { sensitivity: "base" });
      });
      const frag = document.createDocumentFragment();
      for (const ep of matches) {
        frag.appendChild(makeEpisodeCard(ep));
      }
      episodesGrid.appendChild(frag);
      episodesLoadStatus.textContent = "";
    };

    const scrollEpisodeHash = () => {
      const h = decodeURIComponent((location.hash || "").slice(1));
      if (!h) return;
      document.getElementById(h)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    };

    const buildEpisodesBrowse = (data) => {
      episodesBrowseRoot.innerHTML = "";
      const seasons = data && Array.isArray(data.seasons) ? data.seasons : [];
      if (!seasons.length) {
        episodesBrowseRoot.innerHTML =
          '<p class="characters-browse-empty">No episode data. Run scripts/build_episodes_index.py and refresh.</p>';
        return;
      }

      episodeManifest = [];
      for (const s of seasons) {
        for (const ep of s.episodes || []) {
          episodeManifest.push(ep);
        }
      }

      for (const s of seasons) {
        const eps = s.episodes || [];
        if (!eps.length) continue;

        const section = document.createElement("section");
        section.className = "char-group";

        const h2 = document.createElement("h2");
        h2.className = "char-group-title";
        const href = (s.seasonHref || "").trim();
        if (href) {
          const link = document.createElement("a");
          link.className = "char-group-title-link";
          link.href = href;
          link.textContent = s.title || "Season";
          h2.appendChild(link);
        } else {
          h2.textContent = s.title || "Season";
        }

        const grid = document.createElement("div");
        grid.className = "characters-grid characters-grid--group";
        grid.setAttribute("aria-label", s.title || "Episodes");

        for (const ep of eps) {
          grid.appendChild(makeEpisodeCard(ep));
        }

        section.appendChild(h2);
        section.appendChild(grid);
        episodesBrowseRoot.appendChild(section);
      }
    };

    episodesSearch.addEventListener(
      "input",
      () => {
        const raw = String(episodesSearch.value || "").trim();
        if (!raw) {
          exitEpisodesSearchToBrowse();
          return;
        }
        const qFold = foldEpisodeQuery(raw);
        if (!qFold) {
          exitEpisodesSearchToBrowse();
          if (episodesSearchNote) {
            episodesSearchNote.hidden = false;
            episodesSearchNote.textContent = "Use letters or numbers in your search.";
          }
          return;
        }
        if (episodesSearchNote) {
          episodesSearchNote.hidden = true;
          episodesSearchNote.textContent = "";
        }
        runEpisodeSearch(qFold);
      },
      { passive: true },
    );

    fetch("/assets/data/episodes_index.json")
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((data) => {
        buildEpisodesBrowse(data);
        episodesBrowseRoot.hidden = false;
        episodesSearchPanel.hidden = true;
        scrollEpisodeHash();
        window.addEventListener("hashchange", () => {
          if (!String(episodesSearch.value || "").trim()) scrollEpisodeHash();
        });
      })
      .catch(() => {
        episodesBrowseRoot.innerHTML =
          '<p class="characters-browse-empty">Could not load episodes. Try refreshing.</p>';
      });
  }

  // Weapons index: groups from weapons_index.json (see scripts/build_weapons_index.py).
  const weaponsSearch = document.getElementById("weapons-search");
  const weaponsGrid = document.getElementById("weapons-grid");
  const weaponsLoadStatus = document.getElementById("weapons-load-status");
  const weaponsBrowseRoot = document.getElementById("weapons-browse-root");
  const weaponsSearchPanel = document.getElementById("weapons-search-panel");
  const weaponsSearchNote = document.getElementById("weapons-search-note");

  if (
    weaponsSearch &&
    weaponsGrid &&
    weaponsLoadStatus &&
    weaponsBrowseRoot &&
    weaponsSearchPanel
  ) {
    /** @type {{ display: string, href: string, slug: string, filter: string, img: string, codes?: string[] }[]} */
    let weaponManifest = [];

    const foldWeaponQuery = (raw) =>
      String(raw || "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]/g, "");

    const weaponDisplaySearchRank = (display, qFold) => {
      if (!qFold) return 0;
      const full = foldSearch(display);
      if (full.startsWith(qFold)) return 100;
      const words = String(display)
        .toLowerCase()
        .split(/[^a-z0-9.]+/)
        .filter(Boolean);
      if (!words.length) return 0;
      if (foldSearch(words[0]).startsWith(qFold)) return 90;
      if (words.slice(1).some((w) => foldSearch(w).startsWith(qFold))) return 70;
      return 0;
    };

    const weaponMatchRank = (row, qFold) => {
      const r = weaponDisplaySearchRank(row.display, qFold);
      if (r) return r;
      const hay = foldSearch(`${row.filter || ""} ${row.display}`);
      if (hay.includes(qFold)) return 25;
      return 0;
    };

    const applyWeaponImgSrc = (img) => {
      img.src = cardImageSrc(img.getAttribute("data-card-image"));
    };

    const makeWeaponCard = (row) => {
      const a = document.createElement("a");
      a.className = "char-card char-card--episode";
      if (row.slug) a.id = row.slug;
      a.href = row.href;
      a.setAttribute("data-filter", row.filter || row.display);
      const img = document.createElement("img");
      img.className = "char-img";
      img.alt = "";
      img.decoding = "async";
      img.loading = "lazy";
      const im = (row.img || "").trim();
      if (im.startsWith("http://") || im.startsWith("https://")) {
        img.referrerPolicy = "no-referrer";
      }
      img.setAttribute("data-card-image", im);
      applyWeaponImgSrc(img);
      const nm = document.createElement("div");
      nm.className = "char-name";
      nm.textContent = row.display;
      a.appendChild(img);
      a.appendChild(nm);
      return a;
    };

    const removeWeaponSearchCards = () => {
      weaponsGrid.querySelectorAll(".char-card").forEach((el) => el.remove());
    };

    const exitWeaponsSearchToBrowse = () => {
      removeWeaponSearchCards();
      weaponsSearchPanel.hidden = true;
      weaponsBrowseRoot.hidden = false;
      weaponsLoadStatus.textContent = "";
      if (weaponsSearchNote) {
        weaponsSearchNote.hidden = true;
        weaponsSearchNote.textContent = "";
      }
    };

    const runWeaponSearch = (qFold) => {
      weaponsBrowseRoot.hidden = true;
      weaponsSearchPanel.hidden = false;
      if (weaponsSearchNote) {
        weaponsSearchNote.hidden = true;
        weaponsSearchNote.textContent = "";
      }
      removeWeaponSearchCards();
      const matches = weaponManifest.filter((row) => weaponMatchRank(row, qFold) > 0);
      matches.sort((a, b) => {
        const ra = weaponMatchRank(a, qFold);
        const rb = weaponMatchRank(b, qFold);
        if (rb !== ra) return rb - ra;
        return a.display.localeCompare(b.display, undefined, { sensitivity: "base" });
      });
      const frag = document.createDocumentFragment();
      for (const row of matches) {
        frag.appendChild(makeWeaponCard(row));
      }
      weaponsGrid.appendChild(frag);
      weaponsLoadStatus.textContent = "";
    };

    const scrollWeaponHash = () => {
      const h = decodeURIComponent((location.hash || "").slice(1));
      if (!h) return;
      document.getElementById(h)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    };

    const buildWeaponsBrowse = (data) => {
      weaponsBrowseRoot.innerHTML = "";
      const groups = data && Array.isArray(data.groups) ? data.groups : [];
      if (!groups.length) {
        weaponsBrowseRoot.innerHTML =
          '<p class="characters-browse-empty">No weapon data. Run scripts/build_weapons_index.py and refresh.</p>';
        return;
      }

      weaponManifest = [];
      for (const g of groups) {
        for (const row of g.sets || []) {
          weaponManifest.push(row);
        }
      }

      for (const g of groups) {
        const rows = g.sets || [];
        if (!rows.length) continue;

        const section = document.createElement("section");
        section.className = "char-group";

        const h2 = document.createElement("h2");
        h2.className = "char-group-title";
        const href = (g.groupHref || "").trim();
        if (href) {
          const link = document.createElement("a");
          link.className = "char-group-title-link";
          link.href = href;
          link.textContent = g.title || "Weapons";
          h2.appendChild(link);
        } else {
          h2.textContent = g.title || "Weapons";
        }

        const grid = document.createElement("div");
        grid.className = "characters-grid characters-grid--group";
        grid.setAttribute("aria-label", g.title || "Weapons");

        for (const row of rows) {
          grid.appendChild(makeWeaponCard(row));
        }

        section.appendChild(h2);
        section.appendChild(grid);
        weaponsBrowseRoot.appendChild(section);
      }
    };

    weaponsSearch.addEventListener(
      "input",
      () => {
        const raw = String(weaponsSearch.value || "").trim();
        if (!raw) {
          exitWeaponsSearchToBrowse();
          return;
        }
        const qFold = foldWeaponQuery(raw);
        if (!qFold) {
          exitWeaponsSearchToBrowse();
          if (weaponsSearchNote) {
            weaponsSearchNote.hidden = false;
            weaponsSearchNote.textContent = "Use letters or numbers in your search.";
          }
          return;
        }
        if (weaponsSearchNote) {
          weaponsSearchNote.hidden = true;
          weaponsSearchNote.textContent = "";
        }
        runWeaponSearch(qFold);
      },
      { passive: true },
    );

    fetch("/assets/data/weapons_index.json")
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((data) => {
        buildWeaponsBrowse(data);
        weaponsBrowseRoot.hidden = false;
        weaponsSearchPanel.hidden = true;
        scrollWeaponHash();
        window.addEventListener("hashchange", () => {
          if (!String(weaponsSearch.value || "").trim()) scrollWeaponHash();
        });
      })
      .catch(() => {
        weaponsBrowseRoot.innerHTML =
          '<p class="characters-browse-empty">Could not load weapons. Try refreshing.</p>';
      });
  }

  // Sets index: groups from sets_index.json (see scripts/build_sets_index.py).
  const setsSearch = document.getElementById("sets-search");
  const setsGrid = document.getElementById("sets-grid");
  const setsLoadStatus = document.getElementById("sets-load-status");
  const setsBrowseRoot = document.getElementById("sets-browse-root");
  const setsSearchPanel = document.getElementById("sets-search-panel");
  const setsSearchNote = document.getElementById("sets-search-note");

  if (setsSearch && setsGrid && setsLoadStatus && setsBrowseRoot && setsSearchPanel) {
    /** @type {{ display: string, href: string, slug: string, filter: string, img: string, codes?: string[] }[]} */
    let setManifest = [];

    const foldSetQuery = (raw) =>
      String(raw || "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]/g, "");

    const setDisplaySearchRank = (display, qFold) => {
      if (!qFold) return 0;
      const full = foldSearch(display);
      if (full.startsWith(qFold)) return 100;
      const words = String(display)
        .toLowerCase()
        .split(/[^a-z0-9.]+/)
        .filter(Boolean);
      if (!words.length) return 0;
      if (foldSearch(words[0]).startsWith(qFold)) return 90;
      if (words.slice(1).some((w) => foldSearch(w).startsWith(qFold))) return 70;
      return 0;
    };

    const setMatchRank = (row, qFold) => {
      const r = setDisplaySearchRank(row.display, qFold);
      if (r) return r;
      const hay = foldSearch(`${row.filter || ""} ${row.display}`);
      if (hay.includes(qFold)) return 25;
      return 0;
    };

    const dedupeSetRows = (rows) => {
      const seen = new Set();
      const out = [];
      for (const row of rows) {
        const key =
          String(row.href || "").trim().toLowerCase() ||
          String(row.slug || "").trim().toLowerCase() ||
          foldSearch(String(row.display || ""));
        if (!key || seen.has(key)) continue;
        seen.add(key);
        out.push(row);
      }
      return out;
    };

    const applySetImgSrc = (img) => {
      img.src = cardImageSrc(img.getAttribute("data-card-image"));
    };

    const makeSetCard = (row) => {
      const a = document.createElement("a");
      a.className = "char-card char-card--episode";
      if (row.slug) a.id = row.slug;
      a.href = row.href;
      a.setAttribute("data-filter", row.filter || row.display);
      const img = document.createElement("img");
      img.className = "char-img";
      img.alt = "";
      img.decoding = "async";
      img.loading = "lazy";
      const im = (row.img || "").trim();
      if (im.startsWith("http://") || im.startsWith("https://")) {
        img.referrerPolicy = "no-referrer";
      }
      img.setAttribute("data-card-image", im);
      applySetImgSrc(img);
      const nm = document.createElement("div");
      nm.className = "char-name";
      nm.textContent = row.display;
      a.appendChild(img);
      a.appendChild(nm);
      return a;
    };

    const removeSetSearchCards = () => {
      setsGrid.querySelectorAll(".char-card").forEach((el) => el.remove());
    };

    const exitSetsSearchToBrowse = () => {
      removeSetSearchCards();
      setsSearchPanel.hidden = true;
      setsBrowseRoot.hidden = false;
      setsLoadStatus.textContent = "";
      if (setsSearchNote) {
        setsSearchNote.hidden = true;
        setsSearchNote.textContent = "";
      }
    };

    const runSetSearch = (qFold) => {
      setsBrowseRoot.hidden = true;
      setsSearchPanel.hidden = false;
      if (setsSearchNote) {
        setsSearchNote.hidden = true;
        setsSearchNote.textContent = "";
      }
      removeSetSearchCards();
      const matches = dedupeSetRows(setManifest.filter((row) => setMatchRank(row, qFold) > 0));
      matches.sort((a, b) => {
        const ra = setMatchRank(a, qFold);
        const rb = setMatchRank(b, qFold);
        if (rb !== ra) return rb - ra;
        return a.display.localeCompare(b.display, undefined, { sensitivity: "base" });
      });
      const frag = document.createDocumentFragment();
      for (const row of matches) {
        frag.appendChild(makeSetCard(row));
      }
      setsGrid.appendChild(frag);
      setsLoadStatus.textContent = "";
    };

    const scrollSetHash = () => {
      const h = decodeURIComponent((location.hash || "").slice(1));
      if (!h) return;
      document.getElementById(h)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    };

    const buildSetsBrowse = (data) => {
      setsBrowseRoot.innerHTML = "";
      const groups = data && Array.isArray(data.groups) ? data.groups : [];
      if (!groups.length) {
        setsBrowseRoot.innerHTML =
          '<p class="characters-browse-empty">No set data. Run scripts/build_sets_index.py and refresh.</p>';
        return;
      }

      setManifest = [];
      for (const g of groups) {
        for (const row of g.sets || []) {
          setManifest.push(row);
        }
      }

      for (const g of groups) {
        const rows = g.sets || [];
        if (!rows.length) continue;

        const section = document.createElement("section");
        section.className = "char-group";

        const h2 = document.createElement("h2");
        h2.className = "char-group-title";
        const href = (g.groupHref || "").trim();
        if (href) {
          const link = document.createElement("a");
          link.className = "char-group-title-link";
          link.href = href;
          link.textContent = g.title || "Sets";
          h2.appendChild(link);
        } else {
          h2.textContent = g.title || "Sets";
        }

        const grid = document.createElement("div");
        grid.className = "characters-grid characters-grid--group";
        grid.setAttribute("aria-label", g.title || "Sets");

        for (const row of rows) {
          grid.appendChild(makeSetCard(row));
        }

        section.appendChild(h2);
        section.appendChild(grid);
        setsBrowseRoot.appendChild(section);
      }
    };

    setsSearch.addEventListener(
      "input",
      () => {
        const raw = String(setsSearch.value || "").trim();
        if (!raw) {
          exitSetsSearchToBrowse();
          return;
        }
        const qFold = foldSetQuery(raw);
        if (!qFold) {
          exitSetsSearchToBrowse();
          if (setsSearchNote) {
            setsSearchNote.hidden = false;
            setsSearchNote.textContent = "Use letters or numbers in your search.";
          }
          return;
        }
        if (setsSearchNote) {
          setsSearchNote.hidden = true;
          setsSearchNote.textContent = "";
        }
        runSetSearch(qFold);
      },
      { passive: true },
    );

    fetch("/assets/data/sets_index.json")
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((data) => {
        buildSetsBrowse(data);
        setsBrowseRoot.hidden = false;
        setsSearchPanel.hidden = true;
        scrollSetHash();
        window.addEventListener("hashchange", () => {
          if (!String(setsSearch.value || "").trim()) scrollSetHash();
        });
      })
      .catch(() => {
        setsBrowseRoot.innerHTML =
          '<p class="characters-browse-empty">Could not load sets. Try refreshing.</p>';
      });
  }

  // Media index: magazines + albums + songs from media_index.json (see scripts/build_media_index.py).
  const mediaSearch = document.getElementById("media-search");
  const mediaGrid = document.getElementById("media-grid");
  const mediaLoadStatus = document.getElementById("media-load-status");
  const mediaBrowseRoot = document.getElementById("media-browse-root");
  const mediaSearchPanel = document.getElementById("media-search-panel");
  const mediaSearchNote = document.getElementById("media-search-note");

  if (mediaSearch && mediaGrid && mediaLoadStatus && mediaBrowseRoot && mediaSearchPanel) {
    /** @type {{ display: string, href: string, slug: string, filter: string, img: string }[]} */
    let mediaManifest = [];

    const foldMediaQuery = (raw) =>
      String(raw || "")
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9]/g, "");

    const mediaDisplaySearchRank = (display, qFold) => {
      if (!qFold) return 0;
      const full = foldSearch(display);
      if (full.startsWith(qFold)) return 100;
      const words = String(display)
        .toLowerCase()
        .split(/[^a-z0-9.]+/)
        .filter(Boolean);
      if (!words.length) return 0;
      if (foldSearch(words[0]).startsWith(qFold)) return 90;
      if (words.slice(1).some((w) => foldSearch(w).startsWith(qFold))) return 70;
      return 0;
    };

    const mediaMatchRank = (row, qFold) => {
      const r = mediaDisplaySearchRank(row.display, qFold);
      if (r) return r;
      const hay = foldSearch(`${row.filter || ""} ${row.display}`);
      if (hay.includes(qFold)) return 25;
      return 0;
    };

    const applyMediaImgSrc = (img) => {
      img.src = cardImageSrc(img.getAttribute("data-card-image"));
    };

    const makeMediaCard = (row) => {
      const a = document.createElement("a");
      a.className = "char-card char-card--episode";
      if (row.slug) a.id = row.slug;
      a.href = row.href;
      a.setAttribute("data-filter", row.filter || row.display);
      const img = document.createElement("img");
      img.className = "char-img";
      img.alt = "";
      img.decoding = "async";
      img.loading = "lazy";
      const im = (row.img || "").trim();
      if (im.startsWith("http://") || im.startsWith("https://")) {
        img.referrerPolicy = "no-referrer";
      }
      img.setAttribute("data-card-image", im);
      applyMediaImgSrc(img);
      const nm = document.createElement("div");
      nm.className = "char-name";
      nm.textContent = row.display;
      a.appendChild(img);
      a.appendChild(nm);
      return a;
    };

    const removeMediaSearchCards = () => {
      mediaGrid.querySelectorAll(".char-card").forEach((el) => el.remove());
    };

    const exitMediaSearchToBrowse = () => {
      removeMediaSearchCards();
      mediaSearchPanel.hidden = true;
      mediaBrowseRoot.hidden = false;
      mediaLoadStatus.textContent = "";
      if (mediaSearchNote) {
        mediaSearchNote.hidden = true;
        mediaSearchNote.textContent = "";
      }
    };

    const runMediaSearch = (qFold) => {
      mediaBrowseRoot.hidden = true;
      mediaSearchPanel.hidden = false;
      if (mediaSearchNote) {
        mediaSearchNote.hidden = true;
        mediaSearchNote.textContent = "";
      }
      removeMediaSearchCards();
      const matches = mediaManifest.filter((row) => mediaMatchRank(row, qFold) > 0);
      matches.sort((a, b) => {
        const ra = mediaMatchRank(a, qFold);
        const rb = mediaMatchRank(b, qFold);
        if (rb !== ra) return rb - ra;
        return a.display.localeCompare(b.display, undefined, { sensitivity: "base" });
      });
      const frag = document.createDocumentFragment();
      for (const row of matches) {
        frag.appendChild(makeMediaCard(row));
      }
      mediaGrid.appendChild(frag);
      mediaLoadStatus.textContent = "";
    };

    const scrollMediaHash = () => {
      const h = decodeURIComponent((location.hash || "").slice(1));
      if (!h) return;
      document.getElementById(h)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    };

    const buildMediaBrowse = (data) => {
      mediaBrowseRoot.innerHTML = "";
      const groups = data && Array.isArray(data.groups) ? data.groups : [];
      if (!groups.length) {
        mediaBrowseRoot.innerHTML =
          '<p class="characters-browse-empty">No media data. Run scripts/build_media_index.py and refresh.</p>';
        return;
      }

      mediaManifest = [];
      for (const g of groups) {
        for (const row of g.sets || []) {
          mediaManifest.push(row);
        }
      }

      for (const g of groups) {
        const rows = g.sets || [];
        if (!rows.length) continue;

        const section = document.createElement("section");
        section.className = "char-group";

        const h2 = document.createElement("h2");
        h2.className = "char-group-title";
        const href = (g.groupHref || "").trim();
        if (href) {
          const link = document.createElement("a");
          link.className = "char-group-title-link";
          link.href = href;
          link.textContent = g.title || "Media";
          h2.appendChild(link);
        } else {
          h2.textContent = g.title || "Media";
        }

        const grid = document.createElement("div");
        grid.className = "characters-grid characters-grid--group";
        grid.setAttribute("aria-label", g.title || "Media");

        for (const row of rows) {
          grid.appendChild(makeMediaCard(row));
        }

        section.appendChild(h2);
        section.appendChild(grid);
        mediaBrowseRoot.appendChild(section);
      }
    };

    mediaSearch.addEventListener(
      "input",
      () => {
        const raw = String(mediaSearch.value || "").trim();
        if (!raw) {
          exitMediaSearchToBrowse();
          return;
        }
        const qFold = foldMediaQuery(raw);
        if (!qFold) {
          exitMediaSearchToBrowse();
          if (mediaSearchNote) {
            mediaSearchNote.hidden = false;
            mediaSearchNote.textContent = "Use letters or numbers in your search.";
          }
          return;
        }
        if (mediaSearchNote) {
          mediaSearchNote.hidden = true;
          mediaSearchNote.textContent = "";
        }
        runMediaSearch(qFold);
      },
      { passive: true },
    );

    fetch("/assets/data/media_index.json")
      .then((r) => {
        if (!r.ok) throw new Error(String(r.status));
        return r.json();
      })
      .then((data) => {
        buildMediaBrowse(data);
        mediaBrowseRoot.hidden = false;
        mediaSearchPanel.hidden = true;
        scrollMediaHash();
        window.addEventListener("hashchange", () => {
          if (!String(mediaSearch.value || "").trim()) scrollMediaHash();
        });
      })
      .catch(() => {
        mediaBrowseRoot.innerHTML =
          '<p class="characters-browse-empty">Could not load media. Try refreshing.</p>';
      });
  }

  // Homepage simple cards: use wiki no-image placeholder instead of hero art.
  const simpleCardImages = Array.from(document.querySelectorAll(".simple-card-img"));
  if (simpleCardImages.length) {
    for (const img of simpleCardImages) {
      img.src = cardImageSrc(img.getAttribute("data-card-image"));
    }
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

