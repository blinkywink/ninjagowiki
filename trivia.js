(() => {
  const QUIZ_LENGTH = 10;
  const QUIZ_IMAGE_WIDTH = 480;
  const QUIZ_IMAGE_WIDTH_MOBILE = 960;
  const MOBILE_MQ = window.matchMedia("(max-width: 860px)");

  const NO_IMAGE =
    "https://static.wikia.nocookie.net/ninjago/images/8/84/Noimage.jpg/revision/latest/scale-to-width-down/450?cb=20260319010138";

  const QUIZ_META = {
    episode: {
      title: "Episode Quiz",
      prompt: "Which episode is this?",
    },
    character: {
      title: "Character Quiz",
      prompt: "Who is this character?",
    },
    set: {
      title: "Set Quiz",
      prompt: "What year was this set released?",
    },
  };

  const hub = document.getElementById("trivia-hub");
  const quizEl = document.getElementById("trivia-quiz");
  const resultsEl = document.getElementById("trivia-results");
  const loadStatus = document.getElementById("trivia-load-status");
  const cardsRoot = document.getElementById("trivia-cards");
  const backBtn = document.getElementById("trivia-back");
  const progressBar = document.getElementById("trivia-progress-bar");
  const progressText = document.getElementById("trivia-progress-text");
  const questionShell = document.getElementById("trivia-question-shell");
  const imagesEl = document.getElementById("trivia-images");
  const questionEl = document.getElementById("trivia-question");
  const optionsEl = document.getElementById("trivia-options");
  const feedbackEl = document.getElementById("trivia-feedback");
  const feedbackScrim = document.getElementById("trivia-feedback-scrim");
  const resultsScore = document.getElementById("trivia-results-score");
  const resultsTitle = document.getElementById("trivia-results-title");
  const resultsList = document.getElementById("trivia-results-list");
  const resultsCard = document.getElementById("trivia-results-card");
  const retryBtn = document.getElementById("trivia-retry");
  const homeBtn = document.getElementById("trivia-home");
  const nextBtn = document.getElementById("trivia-next");

  if (!hub || !cardsRoot) return;

  let pool = null;
  let quizType = null;
  let questions = [];
  let qIndex = 0;
  let score = 0;
  let answers = [];
  let locked = false;
  let feedbackTimer = null;
  let scrimFadeTimer = null;
  let nextGlowTimer = null;
  const FEEDBACK_MS = 1800;
  const SCRIM_FADE_MS = 400;

  const hideFeedback = (afterHide) => {
    clearTimeout(feedbackTimer);
    clearTimeout(scrimFadeTimer);
    feedbackTimer = null;
    scrimFadeTimer = null;
    questionShell?.classList.remove("is-feedback-active");
    if (feedbackEl) {
      feedbackEl.classList.remove("is-visible", "is-correct", "is-wrong");
      feedbackEl.textContent = "";
      feedbackEl.className = "trivia-feedback-toast";
      feedbackEl.hidden = true;
    }
    if (feedbackScrim) {
      feedbackScrim.classList.remove("is-visible");
      feedbackScrim.setAttribute("aria-hidden", "true");
      scrimFadeTimer = window.setTimeout(() => {
        scrimFadeTimer = null;
        feedbackScrim.hidden = true;
        if (afterHide) afterHide();
      }, SCRIM_FADE_MS);
      return;
    }
    if (afterHide) afterHide();
  };

  const showFeedback = (correct, afterFeedback) => {
    if (!feedbackEl) return;
    clearTimeout(feedbackTimer);
    clearTimeout(scrimFadeTimer);
    feedbackTimer = null;
    scrimFadeTimer = null;
    feedbackEl.textContent = correct ? "Correct!" : "Incorrect";
    feedbackEl.className = `trivia-feedback-toast ${correct ? "is-correct" : "is-wrong"}`;
    feedbackEl.hidden = false;
    if (feedbackScrim) {
      feedbackScrim.hidden = false;
      feedbackScrim.setAttribute("aria-hidden", "false");
    }
    questionShell?.classList.add("is-feedback-active");
    requestAnimationFrame(() => {
      feedbackEl.classList.add("is-visible");
      feedbackScrim?.classList.add("is-visible");
    });
    feedbackTimer = window.setTimeout(() => hideFeedback(afterFeedback), FEEDBACK_MS);
  };

  const shuffle = (arr) => {
    const list = arr.slice();
    for (let i = list.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [list[i], list[j]] = [list[j], list[i]];
    }
    return list;
  };

  const sample = (arr, n) => shuffle(arr).slice(0, Math.min(n, arr.length));

  const imgUrl = (raw, width = QUIZ_IMAGE_WIDTH) => {
    const s = String(raw || "").trim();
    if (!s) return NO_IMAGE;
    if (!s.startsWith("http")) return s;
    return s
      .replace(/\/scale-to-width-down\/\d+/gi, `/scale-to-width-down/${width}`)
      .replace(/\/scale-to-width\/\d+/gi, `/scale-to-width/${width}`);
  };

  const prefetchImages = (urls) => {
    (urls || []).forEach((raw) => {
      const img = new Image();
      if (String(raw).startsWith("http")) img.referrerPolicy = "no-referrer";
      img.src = imgUrl(raw);
    });
  };

  const mountQuizImage = (wrap, src, width = QUIZ_IMAGE_WIDTH) => {
    wrap.classList.add("is-loading");
    wrap.classList.add("trivia-image-wrap--zoomable");
    wrap.setAttribute("role", "button");
    wrap.setAttribute("tabindex", "-1");
    wrap.setAttribute("aria-label", "View larger image");

    const loader = document.createElement("span");
    loader.className = "trivia-image-loader";
    loader.setAttribute("aria-hidden", "true");

    const img = document.createElement("img");
    img.className = "trivia-image";
    img.alt = "";
    img.decoding = "async";
    img.dataset.fullSrc = String(src || "").trim();

    const finish = () => {
      wrap.classList.remove("is-loading");
      wrap.setAttribute("tabindex", "0");
      loader.remove();
    };

    img.addEventListener("load", finish, { once: true });
    img.addEventListener("error", finish, { once: true });

    wrap.appendChild(loader);
    wrap.appendChild(img);
    img.src = imgUrl(src, width);
    setImgAttrs(img);
  };

  let carouselScrollTimer = null;

  const getCarouselActiveIndex = (track) => {
    const slides = Array.from(track?.querySelectorAll(".trivia-image-wrap") || []);
    if (slides.length < 2) return 0;
    const mid = track.scrollLeft + track.clientWidth / 2;
    let active = 0;
    let best = Infinity;
    slides.forEach((slide, i) => {
      const center = slide.offsetLeft + slide.offsetWidth / 2;
      const dist = Math.abs(center - mid);
      if (dist < best) {
        best = dist;
        active = i;
      }
    });
    return active;
  };

  const scrollCarouselTo = (track, index) => {
    const slide = track?.querySelectorAll(".trivia-image-wrap")[index];
    if (!slide) return;
    slide.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  };

  const syncCarouselControls = (track, dotsEl, prevBtn, nextBtn) => {
    if (!track) return;
    const slides = track.querySelectorAll(".trivia-image-wrap");
    if (slides.length < 2) return;
    const active = getCarouselActiveIndex(track);
    dotsEl?.querySelectorAll(".trivia-carousel-dot").forEach((dot, i) => {
      dot.classList.toggle("is-active", i === active);
      dot.setAttribute("aria-current", i === active ? "true" : "false");
    });
    if (prevBtn) prevBtn.disabled = active <= 0;
    if (nextBtn) nextBtn.disabled = active >= slides.length - 1;
  };

  const teardownCarouselControls = (shell) => {
    if (!shell) return;
    shell.querySelector(".trivia-carousel-dots")?.remove();
    shell.querySelector(".trivia-carousel-prev")?.remove();
    shell.querySelector(".trivia-carousel-next")?.remove();
  };

  const mountCarouselControls = (track, count) => {
    const shell = track.parentElement;
    if (!shell || count < 2) return;

    let dotsEl = shell.querySelector(".trivia-carousel-dots");
    if (!dotsEl) {
      dotsEl = document.createElement("div");
      dotsEl.className = "trivia-carousel-dots";
      dotsEl.setAttribute("aria-hidden", "true");
      shell.appendChild(dotsEl);
    }
    dotsEl.innerHTML = "";
    for (let i = 0; i < count; i++) {
      const dot = document.createElement("span");
      dot.className = `trivia-carousel-dot${i === 0 ? " is-active" : ""}`;
      dotsEl.appendChild(dot);
    }

    let prevBtn = shell.querySelector(".trivia-carousel-prev");
    if (!prevBtn) {
      prevBtn = document.createElement("button");
      prevBtn.type = "button";
      prevBtn.className = "trivia-carousel-nav trivia-carousel-prev";
      prevBtn.setAttribute("aria-label", "Previous image");
      prevBtn.textContent = "‹";
      shell.appendChild(prevBtn);
    }
    let nextBtn = shell.querySelector(".trivia-carousel-next");
    if (!nextBtn) {
      nextBtn = document.createElement("button");
      nextBtn.type = "button";
      nextBtn.className = "trivia-carousel-nav trivia-carousel-next";
      nextBtn.setAttribute("aria-label", "Next image");
      nextBtn.textContent = "›";
      shell.appendChild(nextBtn);
    }

    prevBtn.onclick = () => {
      scrollCarouselTo(track, getCarouselActiveIndex(track) - 1);
    };
    nextBtn.onclick = () => {
      scrollCarouselTo(track, getCarouselActiveIndex(track) + 1);
    };

    track.onscroll = null;
    track.addEventListener(
      "scroll",
      () => {
        clearTimeout(carouselScrollTimer);
        carouselScrollTimer = setTimeout(
          () => syncCarouselControls(track, dotsEl, prevBtn, nextBtn),
          60,
        );
      },
      { passive: true },
    );
    syncCarouselControls(track, dotsEl, prevBtn, nextBtn);
  };

  const setImgAttrs = (img) => {
    const s = img.getAttribute("src") || img.src || "";
    if (String(s).startsWith("http")) img.referrerPolicy = "no-referrer";
  };

  const poolKey = (type) => {
    if (type === "episode") return "episodes";
    if (type === "character") return "characters";
    return "sets";
  };

  const eligiblePool = (type) => {
    const key = poolKey(type);
    const rows = pool?.[key] || [];
    if (type === "character") {
      return rows.filter((r) => (r.images || []).length >= 6);
    }
    if (type === "set") {
      return rows.filter((r) => r.year && (r.images || []).length >= 1);
    }
    return rows.filter((r) => (r.images || []).length >= 1);
  };

  const buildQuestion = (type, row, allRows, allYears) => {
    const imgs = sample(row.images || [], 3);
    if (type === "set") {
      const correct = String(row.year);
      const others = allYears.filter((y) => String(y) !== correct);
      const distractors = sample(others, 3).map(String);
      const options = shuffle([correct, ...distractors]);
      return {
        type,
        correct,
        label: row.display,
        href: row.href || "",
        images: imgs,
        options,
        prompt: QUIZ_META[type].prompt,
      };
    }

    const correct = row.display;
    const others = allRows.filter((r) => r.display !== correct);
    const distractors = sample(others, 3).map((r) => r.display);
    const options = shuffle([correct, ...distractors]);
    return {
      type,
      correct,
      label: row.display,
      href: row.href || "",
      images: imgs,
      options,
      prompt: QUIZ_META[type].prompt,
    };
  };

  const buildQuiz = (type) => {
    const rows = eligiblePool(type);
    if (rows.length < 4) return [];
    const allYears =
      type === "set"
        ? [...new Set(rows.map((r) => r.year).filter(Boolean))]
        : [];
    if (type === "set" && allYears.length < 4) return [];
    const picked = sample(rows, QUIZ_LENGTH);
    return picked.map((row) => buildQuestion(type, row, rows, allYears));
  };

  const hideNext = () => {
    if (!nextBtn) return;
    clearTimeout(nextGlowTimer);
    nextGlowTimer = null;
    nextBtn.hidden = true;
    nextBtn.classList.remove("is-visible", "is-glowing");
  };

  const showNext = () => {
    if (!nextBtn) return;
    nextBtn.textContent = qIndex >= QUIZ_LENGTH - 1 ? "See results" : "Next";
    nextBtn.hidden = false;
    nextBtn.classList.remove("is-glowing");
    requestAnimationFrame(() => {
      nextBtn.classList.add("is-visible");
      requestAnimationFrame(() => nextBtn.classList.add("is-glowing"));
    });
    clearTimeout(nextGlowTimer);
    nextGlowTimer = window.setTimeout(() => {
      nextBtn?.classList.remove("is-glowing");
      nextGlowTimer = null;
    }, 2000);
  };

  const advanceQuestion = () => {
    hideNext();
    qIndex += 1;
    if (qIndex >= QUIZ_LENGTH) {
      renderResults();
    } else {
      renderQuestion();
    }
  };

  const showHub = () => {
    hideNext();
    hub.hidden = false;
    quizEl.hidden = true;
    resultsEl.hidden = true;
    quizType = null;
    questions = [];
    qIndex = 0;
    score = 0;
    answers = [];
    locked = false;
  };

  const showQuiz = () => {
    hub.hidden = true;
    quizEl.hidden = false;
    resultsEl.hidden = true;
  };

  const showResults = () => {
    hub.hidden = true;
    quizEl.hidden = true;
    resultsEl.hidden = false;
  };

  const renderProgress = () => {
    const n = qIndex + 1;
    const pct = (qIndex / QUIZ_LENGTH) * 100;
    progressBar.style.width = `${Math.max(8, pct)}%`;
    progressText.textContent = `${Math.min(n, QUIZ_LENGTH)} / ${QUIZ_LENGTH}`;
  };

  const renderQuestion = () => {
    const q = questions[qIndex];
    if (!q) return;

    locked = false;
    hideNext();
    hideFeedback();
    questionShell.classList.remove("is-correct", "is-wrong");
    questionEl.textContent = q.prompt;

    imagesEl.innerHTML = "";
    imagesEl.hidden = q.images.length === 0;
    imagesEl.className = "trivia-images";
    const isMobile = MOBILE_MQ.matches;
    const imageWidth = isMobile ? QUIZ_IMAGE_WIDTH_MOBILE : QUIZ_IMAGE_WIDTH;
    const imagesShell = questionShell.querySelector(".trivia-images-shell");
    if (imagesShell) imagesShell.hidden = q.images.length === 0;
    if (q.images.length > 0) {
      imagesEl.classList.add(`trivia-images--${Math.min(q.images.length, 3)}`);
      if (isMobile) imagesEl.classList.add("trivia-images--carousel");
    }

    q.images.forEach((src) => {
      const wrap = document.createElement("div");
      wrap.className = "trivia-image-wrap";
      mountQuizImage(wrap, src, imageWidth);
      imagesEl.appendChild(wrap);
    });

    if (isMobile && q.images.length > 1) {
      mountCarouselControls(imagesEl, q.images.length);
    } else if (imagesShell) {
      teardownCarouselControls(imagesShell);
    }

    const nextQ = questions[qIndex + 1];
    if (nextQ) prefetchImages(nextQ.images);

    optionsEl.innerHTML = "";
    q.options.forEach((label) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "trivia-option";
      btn.textContent = label;
      btn.addEventListener("click", () => pickOption(label, btn));
      optionsEl.appendChild(btn);
    });

    renderProgress();

    if (window.matchMedia("(max-width: 860px)").matches) {
      questionShell.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  const pickOption = (label, btn) => {
    if (locked) return;
    locked = true;

    const q = questions[qIndex];
    const correct = label === q.correct;
    if (correct) score += 1;

    answers.push({
      correct: q.correct,
      picked: label,
      ok: correct,
      href: q.href,
      label: q.label || "",
      type: q.type,
      images: q.images || [],
    });

    Array.from(optionsEl.querySelectorAll(".trivia-option")).forEach((el) => {
      el.disabled = true;
      if (el.textContent === q.correct) el.classList.add("is-correct");
      else if (el === btn && !correct) el.classList.add("is-wrong");
    });

    questionShell.classList.add(correct ? "is-correct" : "is-wrong");
    showFeedback(correct, showNext);
  };

  const THUMB_IMAGE_WIDTH = 120;

  const resultIcon = (name) => {
    if (name === "check") {
      return `<svg class="trivia-result-icon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M9.55 17.05 4.5 12l1.41-1.42 3.64 3.64 8.54-8.54L19.5 6.9z"/></svg>`;
    }
    if (name === "wrong") {
      return `<svg class="trivia-result-icon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M18.3 5.71 12 12.01 5.7 5.71 4.29 7.12l6.3 6.29-6.3 6.29 1.41 1.41 6.29-6.3 6.29 6.3 1.41-1.41-6.29-6.29 6.29-6.29z"/></svg>`;
    }
    return `<svg class="trivia-result-icon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/></svg>`;
  };

  const renderResults = () => {
    showResults();
    const pct = Math.round((score / QUIZ_LENGTH) * 100);
    resultsScore.textContent = `${score} / ${QUIZ_LENGTH}`;
    resultsTitle.textContent =
      pct === 100
        ? "Perfect score!"
        : pct >= 70
          ? "Nice work!"
          : pct >= 40
            ? "Not bad — keep studying."
            : "Keep training, ninja.";

    resultsCard.classList.remove("is-great", "is-ok", "is-low");
    if (pct >= 70) resultsCard.classList.add("is-great");
    else if (pct >= 40) resultsCard.classList.add("is-ok");
    else resultsCard.classList.add("is-low");

    resultsList.innerHTML = "";
    answers.forEach((a) => {
      const li = document.createElement("li");
      li.className = `trivia-result-row ${a.ok ? "is-correct" : "is-wrong"}`;

      const thumbs = document.createElement("div");
      thumbs.className = "trivia-result-thumbs";
      (a.images || []).slice(0, 1).forEach((src) => {
        const slot = document.createElement("button");
        slot.type = "button";
        slot.className = "trivia-result-thumb trivia-result-thumb--zoomable";
        slot.setAttribute("aria-label", "View larger image");
        const img = document.createElement("img");
        img.alt = "";
        img.loading = "lazy";
        img.decoding = "async";
        img.dataset.fullSrc = String(src || "").trim();
        img.src = imgUrl(src, THUMB_IMAGE_WIDTH);
        setImgAttrs(img);
        slot.appendChild(img);
        thumbs.appendChild(slot);
      });

      const main = document.createElement("div");
      main.className = "trivia-result-main";

      const answer = document.createElement("div");
      answer.className = "trivia-result-answer";
      if (a.type === "set" && a.label) {
        const setName = document.createElement("span");
        setName.className = "trivia-result-set-name";
        setName.textContent = a.label;
        answer.appendChild(setName);
      }
      if (a.ok) {
        const line = document.createElement("span");
        line.className = "trivia-result-line trivia-result-line--ok";
        line.textContent = a.correct;
        answer.appendChild(line);
      } else {
        const wrong = document.createElement("span");
        wrong.className = "trivia-result-line trivia-result-line--bad";
        wrong.textContent = a.picked;
        const right = document.createElement("span");
        right.className = "trivia-result-line trivia-result-line--ok";
        right.textContent = a.correct;
        answer.appendChild(wrong);
        answer.appendChild(right);
      }
      main.appendChild(answer);

      const status = document.createElement("span");
      status.className = `trivia-result-status ${a.ok ? "is-correct" : "is-wrong"}`;
      status.setAttribute("aria-label", a.ok ? "Correct" : "Wrong");
      status.innerHTML = resultIcon(a.ok ? "check" : "wrong");

      li.appendChild(thumbs);
      li.appendChild(main);
      li.appendChild(status);

      if (a.href) {
        const link = document.createElement("a");
        link.className = "trivia-result-page";
        link.href = a.href;
        link.setAttribute("aria-label", "View page");
        link.innerHTML = resultIcon("link");
        li.appendChild(link);
      }

      resultsList.appendChild(li);
    });
  };

  const startQuiz = (type) => {
    if (!pool) return;
    quizType = type;
    questions = buildQuiz(type);
    if (questions.length < QUIZ_LENGTH) {
      window.alert("Not enough data for this quiz yet. Try another one!");
      return;
    }
    qIndex = 0;
    score = 0;
    answers = [];
    showQuiz();
    prefetchImages(questions[0]?.images);
    renderQuestion();
  };

  cardsRoot.addEventListener("click", (e) => {
    const card = e.target.closest("[data-quiz]");
    if (!card || card.disabled) return;
    startQuiz(card.getAttribute("data-quiz"));
  });

  backBtn?.addEventListener("click", showHub);
  homeBtn?.addEventListener("click", showHub);
  nextBtn?.addEventListener("click", advanceQuestion);
  retryBtn?.addEventListener("click", () => {
    if (quizType) startQuiz(quizType);
  });

  fetch("/assets/data/quiz_pool.json")
    .then((r) => {
      if (!r.ok) throw new Error("load failed");
      return r.json();
    })
    .then((data) => {
      pool = data;
      if (loadStatus) loadStatus.hidden = true;

      cardsRoot.querySelectorAll("[data-quiz]").forEach((card) => {
        const type = card.getAttribute("data-quiz");
        const n = eligiblePool(type).length;
        card.disabled = n < 4;
        if (n < 4) card.classList.add("is-disabled");
      });
    })
    .catch(() => {
      if (loadStatus) {
        loadStatus.textContent = "Could not load quiz data.";
        loadStatus.classList.add("is-error");
      }
      cardsRoot.querySelectorAll("[data-quiz]").forEach((c) => {
        c.disabled = true;
      });
    });

  const triviaPage = document.querySelector(".trivia-page");
  if (triviaPage && window.WikiLightbox) {
    window.WikiLightbox.init({
      pageRoot: triviaPage,
      gather() {
        return Array.from(
          triviaPage.querySelectorAll(
            ".trivia-image-wrap:not(.is-loading) .trivia-image[src], .trivia-result-thumb img[src]",
          ),
        )
          .filter((im) => {
            const s = im.getAttribute("src") || "";
            return s && !s.startsWith("data:");
          })
          .map((im) => ({ img: im, yt: null }));
      },
      resolveImage(e, pageRoot) {
        const wrap = e.target.closest(".trivia-image-wrap:not(.is-loading)");
        if (wrap && pageRoot.contains(wrap)) {
          const im = wrap.querySelector(".trivia-image[src]");
          if (im) return im;
        }
        const thumb = e.target.closest(".trivia-result-thumb--zoomable");
        if (thumb && pageRoot.contains(thumb)) {
          const im = thumb.querySelector("img[src]");
          if (im) return im;
        }
        return null;
      },
    });

    triviaPage.addEventListener("keydown", (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      const wrap = e.target.closest(".trivia-image-wrap:not(.is-loading), .trivia-result-thumb--zoomable");
      if (!wrap) return;
      e.preventDefault();
      wrap.click();
    });
  }
})();
