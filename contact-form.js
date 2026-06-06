(() => {
  const form = document.getElementById("contact-form");
  const shell = document.getElementById("contact-form-shell");
  const success = document.getElementById("contact-form-success");
  const errorEl = document.getElementById("contact-form-error");
  const submitBtn = document.getElementById("contact-form-submit");
  if (!form || !shell || !success || !submitBtn) return;

  const scrollToContactHash = () => {
    if (location.hash !== "#contact") return;
    document.getElementById("contact")?.scrollIntoView({ block: "start" });
  };

  window.addEventListener("hashchange", scrollToContactHash);
  window.addEventListener("pageshow", scrollToContactHash);

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const submitLabel = submitBtn.textContent;

  const showError = (msg) => {
    if (!errorEl) return;
    errorEl.textContent = msg;
    errorEl.hidden = false;
  };

  const clearError = () => {
    if (!errorEl) return;
    errorEl.textContent = "";
    errorEl.hidden = true;
  };

  const playSuccess = () => {
    const height = form.offsetHeight;
    shell.style.minHeight = `${height}px`;

    form.classList.add("is-exiting");
    form.setAttribute("aria-hidden", "true");

    const reveal = () => {
      form.hidden = true;
      success.hidden = false;
      success.classList.add("is-visible");
      shell.classList.add("is-sent");
    };

    if (reducedMotion) {
      reveal();
      return;
    }

    form.addEventListener(
      "animationend",
      () => {
        reveal();
      },
      { once: true }
    );
  };

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearError();

    const honeypot = form.querySelector('input[name="botcheck"]');
    if (honeypot && honeypot.checked) return;

    submitBtn.disabled = true;
    submitBtn.classList.add("is-loading");
    submitBtn.textContent = "Sending…";
    form.classList.add("is-sending");

    try {
      const res = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { Accept: "application/json" },
      });
      const data = await res.json().catch(() => ({}));

      if (!res.ok || !data.success) {
        throw new Error(data.message || "Something went wrong. Please try again.");
      }

      playSuccess();
    } catch (err) {
      showError(err.message || "Could not send your message. Please try again.");
      submitBtn.disabled = false;
      submitBtn.classList.remove("is-loading");
      submitBtn.textContent = submitLabel;
      form.classList.remove("is-sending");
    }
  });
})();
