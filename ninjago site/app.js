(() => {
  const searchInput = document.getElementById("search-input");
  const searchClear = document.getElementById("search-clear");
  const resultsEl = document.getElementById("search-results");
  const tagButtons = Array.from(document.querySelectorAll(".tag"));
  const trendingLinks = Array.from(document.querySelectorAll(".article-list a[data-tags]"));

  if (searchInput && resultsEl) {
    const domItems = Array.from(document.querySelectorAll('a[data-search], a[data-tags]'))
      .map((a) => {
        const url = a.getAttribute("href") || "";
        const keywords = (a.getAttribute("data-search") || a.getAttribute("data-tags") || "").toLowerCase();
        const label = a.querySelector(".article-name")?.textContent?.trim()
          || a.querySelector(".card-title")?.textContent?.trim()
          || a.textContent?.trim()
          || "Open page";
        return { url, keywords, label };
      })
      .filter((x) => x.url && x.keywords);

    const items = domItems;

    const renderResults = (query) => {
      const q = query.trim().toLowerCase();
      resultsEl.innerHTML = "";
      if (!q) return;

      const scored = items
        .map((it) => {
          // Very lightweight scoring: substring hits score higher.
          const idx = it.keywords.indexOf(q);
          const score = idx === -1 ? 0 : 1000 - idx;
          return { ...it, score };
        })
        .filter((x) => x.score > 0)
        .sort((a, b) => b.score - a.score)
        .slice(0, 3);

      if (scored.length === 0) {
        const empty = document.createElement("div");
        empty.className = "result";
        empty.innerHTML = `<span>Nothing matched.</span><small>Try another name (Lloyd, Nya, Codex...)</small>`;
        resultsEl.appendChild(empty);
        return;
      }

      for (const it of scored) {
        const row = document.createElement("div");
        row.className = "result";
        row.innerHTML = `
          <a href="${escapeAttr(it.url)}">${escapeHtml(it.label)}</a>
          <small>${escapeHtml(it.keywords.slice(0, 60))}${it.keywords.length > 60 ? "..." : ""}</small>
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

  // Characters page filtering.
  const charactersSearch = document.getElementById("characters-search");
  const charactersGrid = document.getElementById("characters-grid");
  if (charactersSearch && charactersGrid) {
    const cards = Array.from(charactersGrid.querySelectorAll(".char-card"));
    const normalize = (s) => String(s || "").toLowerCase().trim();

    const apply = () => {
      const q = normalize(charactersSearch.value);
      for (const card of cards) {
        const hay = normalize(card.getAttribute("data-filter"));
        const ok = !q || hay.includes(q);
        card.style.display = ok ? "" : "none";
      }
    };

    charactersSearch.addEventListener("input", apply, { passive: true });
  }

  // Force placeholder images by device:
  // mobile => hero.png, desktop => hero-mobile.png
  const cardImages = Array.from(document.querySelectorAll(".simple-card-img, .char-img"));
  if (cardImages.length) {
    const media = window.matchMedia("(max-width: 859px)");
    const applyCardImages = () => {
      const src = media.matches ? "./assets/hero.png" : "./assets/hero-mobile.png";
      for (const img of cardImages) img.src = src;
    };
    applyCardImages();
    media.addEventListener?.("change", applyCardImages);
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

  function escapeHtml(s) {
    return String(s).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  }
  function escapeAttr(s) {
    return escapeHtml(s).replaceAll("`", "&#096;");
  }
})();

