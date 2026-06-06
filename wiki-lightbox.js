(() => {
  const largerUrl = (url) => {
    if (!url) return url;
    return url.replace(/\/scale-to-width-down\/\d+/gi, "").replace(/\/scale-to-width\/\d+/gi, "");
  };

  const scaledUrl = (url, width = 2000) => {
    const raw = String(url || "").trim();
    if (!raw) return raw;
    if (!raw.startsWith("http")) return raw;
    if (/\/scale-to-width-down\/\d+/i.test(raw)) {
      return raw.replace(/\/scale-to-width-down\/\d+/gi, `/scale-to-width-down/${width}`);
    }
    if (/\/scale-to-width\/\d+/i.test(raw)) {
      return raw.replace(/\/scale-to-width\/\d+/gi, `/scale-to-width/${width}`);
    }
    const q = raw.indexOf("?");
    if (q === -1) return `${raw}/scale-to-width-down/${width}`;
    return `${raw.slice(0, q)}/scale-to-width-down/${width}${raw.slice(q)}`;
  };

  const lightboxSrc = (el) => {
    const raw = (el?.dataset?.fullSrc || el?.getAttribute("src") || el?.currentSrc || "").trim();
    if (!raw) return "";
    return scaledUrl(raw, 2000);
  };

  const thumbUrl = (url) => {
    if (!url) return url;
    if (/\/scale-to-width-down\/\d+/i.test(url)) {
      return url.replace(/\/scale-to-width-down\/\d+/gi, "/scale-to-width-down/96");
    }
    const q = url.indexOf("?");
    if (q === -1) return `${url}/scale-to-width-down/96`;
    return `${url.slice(0, q)}/scale-to-width-down/96${url.slice(q)}`;
  };

  const defaultResolveImage = (e, pageRoot) => {
    if (e.target.closest("a.info-icon")) return null;
    const t = e.target;
    let a = t.closest("a.image.lightbox");
    if (!a && t.closest("aside.portable-infobox")) {
      a = t.closest("aside.portable-infobox figure.pi-image a.image");
    }
    if (!a) a = t.closest(".wiki-import a.image");
    if (!a) a = t.closest(".wiki-import a.mw-file-description");

    let im = null;
    if (a && pageRoot.contains(a)) {
      im = a.querySelector("img[src]");
    } else {
      im = t.closest(".wiki-import img[src]");
    }
    if (!im || !pageRoot.contains(im)) return null;
    if (im.closest(".wiki-lightbox") || im.closest(".wiki-lightbox-thumbs") || im.closest("noscript")) {
      return null;
    }
    const s = im.getAttribute("src") || "";
    if (!s || s.startsWith("data:")) return null;
    return im;
  };

  const init = (options = {}) => {
    const root = document.getElementById("wiki-lightbox");
    const pageRoot = options.pageRoot || document.querySelector("main.wiki-char-page");
    const resolveImage = options.resolveImage || ((e) => defaultResolveImage(e, pageRoot));
    if (!root || !pageRoot) return null;

    const backdrop = root.querySelector(".wiki-lightbox-backdrop");
    const btnClose = root.querySelector(".wiki-lightbox-close");
    const btnPrev = root.querySelector(".wiki-lightbox-prev");
    const btnNext = root.querySelector(".wiki-lightbox-next");
    const lbImg = root.querySelector(".wiki-lightbox-img");
    const lbVideo = root.querySelector(".wiki-lightbox-video");
    const lbIframe = root.querySelector(".wiki-lightbox-iframe");
    const lbViewport = root.querySelector(".wiki-lightbox-viewport");
    const thumbsEl = root.querySelector(".wiki-lightbox-thumbs");
    if (!lbImg || !lbVideo || !lbIframe || !thumbsEl || !lbViewport) return null;

    let lbLoader = lbViewport.querySelector(".wiki-lightbox-loader");
    if (!lbLoader) {
      lbLoader = document.createElement("div");
      lbLoader.className = "wiki-lightbox-loader";
      lbLoader.setAttribute("aria-hidden", "true");
      lbViewport.appendChild(lbLoader);
    }

    let list = [];
    let idx = 0;
    let lbLoadId = 0;
    let lbScrollY = 0;
    let lbHtmlOverflow = "";
    let lbHtmlMaxWidth = "";

    const gather =
      options.gather ||
      (() =>
        Array.from(pageRoot.querySelectorAll("img[src]"))
          .filter((im) => {
            const s = im.getAttribute("src") || "";
            if (!s || s.startsWith("data:")) return false;
            if (im.closest(".wiki-lightbox")) return false;
            if (im.closest(".wiki-lightbox-thumbs")) return false;
            if (im.closest("noscript")) return false;
            if (im.closest(".trivia-image-wrap.is-loading")) return false;
            return true;
          })
          .map((im) => {
            const a = im.closest("a");
            const yt = (a && a.getAttribute("data-youtube-id")) || "";
            return { img: im, yt: yt || null };
          }));

    const rebuildThumbs = () => {
      thumbsEl.innerHTML = "";
      if (!list.length) return;
      list.forEach((item, i) => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "wiki-lightbox-thumb";
        if (item.yt) b.classList.add("wiki-lightbox-thumb--video");
        b.setAttribute(
          "aria-label",
          `${item.yt ? "Play video " : "Show image "}${i + 1} of ${list.length}`,
        );
        const ti = document.createElement("img");
        ti.alt = "";
        ti.decoding = "async";
        ti.loading = "lazy";
        const u = (
          item.img.dataset?.fullSrc ||
          item.img.currentSrc ||
          item.img.src ||
          ""
        ).trim();
        ti.src = thumbUrl(scaledUrl(u, 96));
        if (u.startsWith("http")) ti.referrerPolicy = "no-referrer";
        b.appendChild(ti);
        b.addEventListener("click", () => {
          idx = i;
          render();
        });
        thumbsEl.appendChild(b);
      });
    };

    const syncThumbStrip = () => {
      const btns = thumbsEl.querySelectorAll(".wiki-lightbox-thumb");
      btns.forEach((btn, i) => {
        const on = i === idx;
        btn.classList.toggle("is-selected", on);
        btn.setAttribute("aria-current", on ? "true" : "false");
        if (on) {
          try {
            btn.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
          } catch {
            btn.scrollIntoView();
          }
        }
      });
    };

    const setLoading = (on) => {
      lbViewport.classList.toggle("is-loading", on);
    };

    const urlKey = (u) =>
      String(u || "")
        .replace(/\/scale-to-width-down\/\d+/gi, "")
        .replace(/\/scale-to-width\/\d+/gi, "");

    const setLbImage = (el) => {
      lbLoadId += 1;
      const currentLoad = lbLoadId;
      const raw = (el.dataset?.fullSrc || el.currentSrc || el.src || "").trim();
      const primary = lightboxSrc(el);
      const fallback = scaledUrl(raw, 1200);
      const preview = (el.currentSrc || el.src || scaledUrl(raw, 480)).trim();
      const candidates = [primary, fallback].filter((u, i, a) => u && a.indexOf(u) === i);
      const upgradeUrls = candidates.filter((u) => urlKey(u) !== urlKey(preview) && u !== preview);

      lbImg.alt = el.getAttribute("alt") || "";
      lbImg.referrerPolicy = "no-referrer";
      lbImg.onload = null;
      lbImg.onerror = null;
      setLoading(false);

      if (preview) {
        lbImg.src = preview;
        lbImg.style.opacity = "";
      } else {
        lbImg.removeAttribute("src");
      }

      if (!upgradeUrls.length) return;

      let attempt = 0;
      const loadFull = () => {
        if (currentLoad !== lbLoadId) return;
        if (attempt >= upgradeUrls.length) {
          setLoading(false);
          return;
        }
        const url = upgradeUrls[attempt++];
        const full = new Image();
        full.referrerPolicy = "no-referrer";

        const apply = () => {
          if (currentLoad !== lbLoadId) return;
          lbImg.src = url;
          setLoading(false);
        };

        full.onload = apply;
        full.onerror = loadFull;
        if (!preview) setLoading(true);
        full.src = url;
        if (full.complete && full.naturalWidth > 0) apply();
      };

      loadFull();
    };

    const render = () => {
      if (!list.length) return;
      idx = (idx + list.length) % list.length;
      const item = list[idx];
      const el = item.img;
      if (item.yt) {
        lbLoadId += 1;
        setLoading(false);
        lbImg.removeAttribute("src");
        lbImg.style.display = "none";
        lbImg.alt = "";
        lbVideo.hidden = false;
        lbIframe.src = `https://www.youtube-nocookie.com/embed/${encodeURIComponent(item.yt)}?autoplay=1&rel=0`;
      } else {
        lbLoadId += 1;
        lbIframe.removeAttribute("src");
        lbVideo.hidden = true;
        lbImg.style.display = "block";
        setLbImage(el);
      }
      const multi = list.length > 1;
      btnPrev.disabled = !multi;
      btnNext.disabled = !multi;
      btnPrev.style.visibility = multi ? "visible" : "hidden";
      btnNext.style.visibility = multi ? "visible" : "hidden";
      btnPrev.setAttribute("aria-hidden", multi ? "false" : "true");
      btnNext.setAttribute("aria-hidden", multi ? "false" : "true");
      syncThumbStrip();
    };

    const openAt = (img) => {
      list = gather();
      idx = list.findIndex((item) => item.img === img);
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
      document.body.style.top = `${-lbScrollY}px`;
      document.body.style.width = "100%";
      document.body.style.maxWidth = "100%";
      document.body.classList.add("wiki-lightbox-open");
      btnClose.focus();
    };

    const closeLb = () => {
      root.hidden = true;
      lbLoadId += 1;
      setLoading(false);
      lbImg.removeAttribute("src");
      lbImg.alt = "";
      lbImg.style.display = "";
      lbImg.style.opacity = "";
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
    };

    pageRoot.addEventListener("click", (e) => {
      const im = resolveImage(e, pageRoot);
      if (!im) return;
      e.preventDefault();
      e.stopPropagation();
      openAt(im);
    });

    btnClose.addEventListener("click", closeLb);
    backdrop.addEventListener("click", closeLb);
    btnPrev.addEventListener("click", () => {
      idx -= 1;
      render();
    });
    btnNext.addEventListener("click", () => {
      idx += 1;
      render();
    });

    document.addEventListener("keydown", (e) => {
      if (root.hidden) return;
      if (e.key === "Escape") {
        e.preventDefault();
        closeLb();
      } else if (e.key === "ArrowLeft" && list.length > 1) {
        e.preventDefault();
        idx -= 1;
        render();
      } else if (e.key === "ArrowRight" && list.length > 1) {
        e.preventDefault();
        idx += 1;
        render();
      }
    });

    return { openAt, close: closeLb };
  };

  window.WikiLightbox = { init, largerUrl, scaledUrl, lightboxSrc };
})();
