(() => {
  const statusEl = document.getElementById("category-tree-status");
  const breadcrumbEl = document.getElementById("category-tree-breadcrumb");
  const rootEl = document.getElementById("category-tree-root");
  if (!statusEl || !breadcrumbEl || !rootEl) return;

  let rootNode = null;
  /** @type {Record<string, unknown> | null} */
  let siteRoutes = null;
  /** @type {{ pages?: { wikiTitle?: string, display?: string, categoryPath?: string }[] } | null} */
  let wikiPages = null;

  const wikiTitleUrl = (title) => {
    const t = String(title || "").trim();
    if (!t) return "https://ninjago.fandom.com/wiki/";
    const path = t.replace(/ /g, "_");
    return `https://ninjago.fandom.com/wiki/${encodeURIComponent(path).replace(/%2F/g, "/")}`;
  };

  const pathToHash = (segments) => {
    if (!segments.length) return "";
    return "#" + segments.map((s) => encodeURIComponent(s)).join("/");
  };

  const hashToSegments = () => {
    const h = (location.hash || "").replace(/^#/, "").trim();
    if (!h) return [];
    return h.split("/").map((s) => decodeURIComponent(s));
  };

  const localHrefForWikiTitle = (title) => {
    if (!siteRoutes || !title) return null;
    const r = siteRoutes;
    const byTitle = /** @type {Record<string, string>} */ (r.wikiTitleKeyToHref || {});
    const byPath = /** @type {Record<string, string>} */ (r.wikiPathToHref || {});
    const key = String(title)
      .trim()
      .toLowerCase()
      .replace(/\s+/g, " ");
    if (byTitle[key]) return byTitle[key];
    const raw = String(title).trim();
    if (!raw) return null;
    const pUnder = `/wiki/${raw.replace(/ /g, "_").toLowerCase()}`;
    if (byPath[pUnder]) return byPath[pUnder];
    const pSpace = `/wiki/${raw.toLowerCase()}`;
    if (byPath[pSpace]) return byPath[pSpace];
    return null;
  };

  const findNode = (segments) => {
    if (!rootNode) return null;
    const rootSlug = (rootNode.slug || "").trim();
    let segs = segments.slice();
    /* Breadcrumb links used to send #content/…; tree links use #characters/… (root omitted). */
    while (segs.length && rootSlug && segs[0] === rootSlug) {
      segs.shift();
    }
    if (segs.length === 0) return rootNode;
    let cur = rootNode;
    for (const seg of segs) {
      const children = cur.children || [];
      const next = children.find((c) => (c.slug || "") === seg);
      if (!next) return null;
      cur = next;
    }
    return cur;
  };

  const renderBreadcrumb = (segments, node) => {
    breadcrumbEl.innerHTML = "";
    breadcrumbEl.hidden = false;

    const ol = document.createElement("ol");
    ol.className = "category-tree-breadcrumb-list";

    if (segments.length === 0) {
      const curLi = document.createElement("li");
      curLi.className = "category-tree-breadcrumb-current";
      curLi.setAttribute("aria-current", "page");
      curLi.textContent = node.displayName || node.title || "Content";
      ol.appendChild(curLi);
      breadcrumbEl.appendChild(ol);
      return;
    }

    const rootLi = document.createElement("li");
    const rootA = document.createElement("a");
    rootA.href = "/all-pages";
    rootA.textContent = rootNode.displayName || rootNode.title || "Content";
    rootLi.appendChild(rootA);
    ol.appendChild(rootLi);

    for (let i = 0; i < segments.length; i++) {
      const prefix = segments.slice(0, i + 1);
      const n = findNode(prefix);
      const label = n ? n.displayName || n.title || segments[i] : segments[i];
      const li = document.createElement("li");
      if (i === segments.length - 1) {
        li.className = "category-tree-breadcrumb-current";
        li.setAttribute("aria-current", "page");
        li.textContent = label;
      } else {
        const a = document.createElement("a");
        a.href = "/all-pages" + pathToHash(prefix);
        a.textContent = label;
        li.appendChild(a);
      }
      ol.appendChild(li);
    }

    breadcrumbEl.appendChild(ol);
  };

  const renderView = () => {
    if (!rootNode) return;

    const segments = hashToSegments();
    const node = findNode(segments);

    rootEl.innerHTML = "";
    rootEl.hidden = false;

    if (!node) {
      breadcrumbEl.hidden = true;
      const err = document.createElement("p");
      err.className = "category-tree-miss";
      err.textContent = "That category path is not in the tree. ";
      const back = document.createElement("a");
      back.href = "/all-pages#";
      back.textContent = "Back to root";
      err.appendChild(back);
      rootEl.appendChild(err);
      document.title = "Not found • All pages • Ninjago Wiki Project";
      return;
    }

    renderBreadcrumb(segments, node);
    document.title = `${node.displayName || node.title || "Category"} • All pages • Ninjago Wiki Project`;

    const head = document.createElement("div");
    head.className = "category-tree-heading";

    const h2 = document.createElement("h2");
    h2.className = "category-tree-title";

    if (node.localOnly) {
      const sp = document.createElement("span");
      sp.className = "category-tree-wiki-link";
      sp.textContent = node.displayName || node.title || "Category";
      h2.appendChild(sp);
    } else {
      const wikiA = document.createElement("a");
      wikiA.className = "category-tree-wiki-link";
      wikiA.href = node.wikiUrl || wikiTitleUrl(node.title);
      wikiA.target = "_blank";
      wikiA.rel = "noopener noreferrer";
      wikiA.textContent = node.displayName || node.title || "Category";
      h2.appendChild(wikiA);
    }

    if (node.duplicate) {
      const sp = document.createElement("span");
      sp.className = "category-tree-dup";
      sp.textContent = " (also linked elsewhere in tree)";
      h2.appendChild(sp);
    }
    if (node.truncated) {
      const sp = document.createElement("span");
      sp.className = "category-tree-trunc";
      sp.textContent = " (branch may be cut off at export depth)";
      h2.appendChild(sp);
    }
    if (node.error) {
      const sp = document.createElement("span");
      sp.className = "category-tree-error";
      sp.textContent = ` — ${node.error}`;
      h2.appendChild(sp);
    }

    head.appendChild(h2);
    rootEl.appendChild(head);

    const children = Array.isArray(node.children) ? node.children : [];
    const pages = Array.isArray(node.directPages) ? node.directPages : [];

    if (children.length) {
      const sec = document.createElement("section");
      sec.className = "category-tree-section";
      const h3 = document.createElement("h3");
      h3.className = "category-tree-section-title";
      h3.textContent = `Subcategories (${children.length})`;
      const ul = document.createElement("ul");
      ul.className = "category-tree-dir-list";
      for (const ch of children) {
        const li = document.createElement("li");
        const a = document.createElement("a");
        a.className = "category-tree-dir-link";
        const nextSegs = [...segments, ch.slug].filter(Boolean);
        if (!ch.slug) {
          a.href = "#";
          a.setAttribute("aria-disabled", "true");
          a.classList.add("is-disabled");
        } else {
          a.href = "/all-pages" + pathToHash(nextSegs);
        }
        a.textContent = ch.displayName || ch.title || ch.slug;
        if (ch.duplicate) {
          a.appendChild(document.createTextNode(" "));
          const d = document.createElement("span");
          d.className = "category-tree-dup";
          d.textContent = "(see tree)";
          a.appendChild(d);
        }
        li.appendChild(a);
        const meta = document.createElement("span");
        meta.className = "category-tree-dir-meta";
        const cc = (ch.children || []).length;
        const pp = (ch.directPages || []).length;
        const bits = [];
        if (cc) bits.push(`${cc} sub`);
        if (pp) bits.push(`${pp} pg`);
        meta.textContent = bits.join(" · ");
        li.appendChild(meta);
        ul.appendChild(li);
      }
      sec.appendChild(h3);
      sec.appendChild(ul);
      rootEl.appendChild(sec);
    } else {
      const empty = document.createElement("p");
      empty.className = "category-tree-empty";
      empty.textContent = "No subcategories in this branch.";
      rootEl.appendChild(empty);
    }

    if (pages.length) {
      const sec = document.createElement("section");
      sec.className = "category-tree-section";
      const h3 = document.createElement("h3");
      h3.className = "category-tree-section-title";
      h3.textContent = `Pages in this category (${pages.length})`;
      const ul = document.createElement("ul");
      ul.className = "category-tree-pages-list category-tree-pages-list--block";
      for (const p of pages) {
        const li = document.createElement("li");
        const pa = document.createElement("a");
        const local = localHrefForWikiTitle(p);
        if (local) {
          pa.href = local;
          pa.className = "category-tree-pages-local";
          pa.textContent = p;
        } else {
          pa.href = wikiTitleUrl(p);
          pa.target = "_blank";
          pa.rel = "noopener noreferrer";
          pa.className = "category-tree-pages-external";
          pa.textContent = p;
        }
        li.appendChild(pa);
        ul.appendChild(li);
      }
      sec.appendChild(h3);
      sec.appendChild(ul);
      rootEl.appendChild(sec);
    }
  };

  window.addEventListener("hashchange", renderView);

  Promise.all([
    fetch("/assets/data/fandom_content_category_tree.json").then((r) => {
      if (!r.ok) throw new Error(`Tree HTTP ${r.status}`);
      return r.json();
    }),
    fetch("/assets/data/site_routes.json").then((r) => (r.ok ? r.json() : null)),
    fetch("/assets/data/wiki_pages.json").then((r) => (r.ok ? r.json() : null)),
  ])
    .then(([data, routes, wiki]) => {
      const tree = data && data.tree;
      const stats = data && data.stats;
      if (!tree) throw new Error("Missing tree in JSON");

      rootNode = tree;
      siteRoutes = routes;
      wikiPages = wiki;

      // Local-only bucket for pages that aren't mapped into the Fandom category tree export.
      const unsortedTitles = Array.isArray(wikiPages && wikiPages.pages)
        ? wikiPages.pages
            .filter((p) => String(p.categoryPath || "").toLowerCase() === "_unsorted")
            .map((p) => String(p.wikiTitle || p.display || "").trim())
            .filter(Boolean)
        : [];
      if (unsortedTitles.length) {
        const seen = new Set();
        const unique = [];
        for (const t of unsortedTitles) {
          const k = t.toLowerCase().replace(/\s+/g, " ");
          if (seen.has(k)) continue;
          seen.add(k);
          unique.push(t);
        }
        unique.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
        const unsortedNode = {
          title: "Unsorted",
          displayName: "Unsorted",
          slug: "_unsorted",
          wikiUrl: "",
          depth: 1,
          children: [],
          directPages: unique,
          localOnly: true,
        };
        rootNode.children = Array.isArray(rootNode.children) ? rootNode.children : [];
        const already = rootNode.children.some((c) => (c && c.slug) === "_unsorted");
        if (!already) rootNode.children = rootNode.children.concat([unsortedNode]);
      }

      const parts = [];
      if (stats && typeof stats.uniqueCategoriesVisited === "number") {
        parts.push(`${stats.uniqueCategoriesVisited} categories`);
      }
      if (stats && typeof stats.treeNodes === "number") {
        parts.push(`${stats.treeNodes} nodes`);
      }
      if (data.generatedAt) {
        parts.push(`updated ${data.generatedAt.slice(0, 10)}`);
      }
      if (routes && routes.stats && typeof routes.stats.wikiTitlesMapped === "number") {
        parts.push(`${routes.stats.wikiTitlesMapped} local page routes`);
      }
      statusEl.textContent = parts.length ? parts.join(" · ") : "Tree loaded.";

      renderView();
    })
    .catch((err) => {
      statusEl.textContent = `Could not load the category tree (${err.message || "error"}). Run scripts/fetch_fandom_content_category_tree.py and refresh.`;
      breadcrumbEl.hidden = true;
      rootEl.hidden = true;
    });
})();
