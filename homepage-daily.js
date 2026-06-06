(() => {
  const root = document.getElementById("daily-picks-root");
  if (!root) return;

  const realignHashScroll = () => {
    const id = decodeURIComponent((location.hash || "").slice(1));
    if (!id) return;
    const target = document.getElementById(id);
    if (!target) return;
    requestAnimationFrame(() => {
      target.scrollIntoView({ block: "start" });
    });
  };

  let hashRealignTimer = null;
  const scheduleHashRealign = () => {
    if (!location.hash) return;
    realignHashScroll();
    clearTimeout(hashRealignTimer);
    hashRealignTimer = setTimeout(realignHashScroll, 350);
  };

  const NO_IMAGE =
    "https://static.wikia.nocookie.net/ninjago/images/8/84/Noimage.jpg/revision/latest/scale-to-width-down/450?cb=20260319010138";
  const HERO = new Set(["/assets/hero.png", "/assets/hero-mobile.png"]);

  const cardImg = (raw) => {
    const s = String(raw || "").trim();
    if (!s || HERO.has(s)) return NO_IMAGE;
    return s;
  };

  const dateSeed = () => {
    const d = new Date();
    return d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate();
  };

  const mulberry32 = (seed) => {
    let a = seed >>> 0;
    return () => {
      a |= 0;
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  };

  const shuffleDaily = (items, salt) => {
    const list = items.slice();
    const rng = mulberry32(dateSeed() + salt);
    for (let i = list.length - 1; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1));
      [list[i], list[j]] = [list[j], list[i]];
    }
    return list;
  };

  const pickOne = (items, salt) => shuffleDaily(items, salt)[0] || null;

  const pickN = (items, n, salt) => shuffleDaily(items, salt).slice(0, n);

  const flattenGroups = (data) => {
    const out = [];
    for (const g of data?.groups || []) {
      for (const row of g.sets || []) out.push(row);
    }
    return out;
  };

  const flattenEpisodes = (data) => {
    const out = [];
    for (const s of data?.seasons || []) {
      for (const ep of s.episodes || []) out.push(ep);
    }
    return out;
  };

  const makeCard = (item, label, subtitle) => {
    const a = document.createElement("a");
    a.className = "simple-card daily-card";
    a.href = item.href;

    const img = document.createElement("img");
    img.className = "simple-card-img";
    img.alt = "";
    img.loading = "lazy";
    img.decoding = "async";
    const im = cardImg(item.img);
    if (im.startsWith("http")) img.referrerPolicy = "no-referrer";
    img.src = im;

    const body = document.createElement("div");
    body.className = "simple-card-body";

    const tag = document.createElement("div");
    tag.className = "daily-card-label";
    tag.textContent = label;

    const name = document.createElement("div");
    name.className = "article-name";
    name.textContent = item.display;

    body.appendChild(tag);
    body.appendChild(name);
    if (subtitle) {
      const sub = document.createElement("div");
      sub.className = "simple-card-subtitle";
      sub.textContent = subtitle;
      body.appendChild(sub);
    }

    a.appendChild(img);
    a.appendChild(body);
    return a;
  };

  const addBlock = (parent, title, subtitle, gridClass) => {
    const block = document.createElement("section");
    block.className = "daily-block";

    const head = document.createElement("div");
    head.className = "daily-block-head";

    const h2 = document.createElement("h2");
    h2.className = "section-title daily-block-title";
    h2.textContent = title;
    head.appendChild(h2);

    if (subtitle) {
      const p = document.createElement("p");
      p.className = "daily-block-sub";
      p.textContent = subtitle;
      head.appendChild(p);
    }

    const grid = document.createElement("div");
    grid.className = gridClass;

    block.appendChild(head);
    block.appendChild(grid);
    parent.appendChild(block);
    return grid;
  };

  Promise.all([
    fetch("/assets/data/characters.json").then((r) => (r.ok ? r.json() : null)),
    fetch("/assets/data/sets_index.json").then((r) => (r.ok ? r.json() : null)),
    fetch("/assets/data/episodes_index.json").then((r) => (r.ok ? r.json() : null)),
    fetch("/assets/data/weapons_index.json").then((r) => (r.ok ? r.json() : null)),
  ])
    .then(([charData, setsData, epData, wepData]) => {
      root.innerHTML = "";

      const characters = (charData?.characters || []).filter((c) => c.href && c.display);
      const sets = flattenGroups(setsData);
      const episodes = flattenEpisodes(epData);
      const weapons = flattenGroups(wepData);

      const char = pickOne(characters, 11);
      const set = pickOne(sets, 22);
      const ep = pickOne(episodes, 33);
      const weapon = pickOne(weapons, 44);
      const spotlight = pickN(sets, 3, 55);

      const spinGrid = addBlock(root, "Today's Spin", "", "daily-spin-grid");

      if (char) spinGrid.appendChild(makeCard(char, "Character of the day"));
      if (set) spinGrid.appendChild(makeCard(set, "Set of the day"));
      if (ep) spinGrid.appendChild(makeCard(ep, "Episode of the day"));
      if (weapon) spinGrid.appendChild(makeCard(weapon, "Weapon of the day"));

      if (spotlight.length) {
        const spotGrid = addBlock(root, "Daily Set Spotlight", "", "simple-grid");
        for (const row of spotlight) {
          spotGrid.appendChild(makeCard(row, "Spotlight"));
        }
      }

      scheduleHashRealign();
    })
    .catch(() => {
      root.innerHTML =
        '<p class="characters-browse-empty">Could not load daily picks. Try refreshing.</p>';
      scheduleHashRealign();
    });

  const dailySection = document.getElementById("daily-picks");
  if (dailySection && location.hash && "ResizeObserver" in window) {
    let resizeTimer = null;
    const ro = new ResizeObserver(() => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(scheduleHashRealign, 80);
    });
    ro.observe(dailySection);
    setTimeout(() => ro.disconnect(), 4000);
  }
})();
