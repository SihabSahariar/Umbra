// Umbra site: nav state, scroll reveals, the "move your cursor away" demo, cover-style tabs, manual TOC.
(() => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Nav gets a background once you scroll.
  const nav = document.getElementById("nav");
  const onScroll = () => nav && !nav.hasAttribute("data-solid") && nav.classList.toggle("scrolled", scrollY > 12);
  addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  // Reveal sections as they enter the viewport; the final moon eclipses into the crescent.
  const targets = document.querySelectorAll(".stage, .try-grid, .how-grid article, .tile, .facts, .start-steps li, .credit-list, .moon");
  if ("IntersectionObserver" in window && !reduce) {
    targets.forEach((el) => el.classList.add("reveal"));
    const io = new IntersectionObserver((entries) => entries.forEach((e) => {
      if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
    }), { rootMargin: "0px 0px -10% 0px" });
    targets.forEach((el) => io.observe(el));
  } else {
    targets.forEach((el) => el.classList.add("in"));
  }

  // Pause the hero video when it's off screen (saves battery).
  const video = document.getElementById("demo");
  if (video && "IntersectionObserver" in window) {
    new IntersectionObserver(([e]) => { e.isIntersecting ? video.play().catch(() => {}) : video.pause(); }).observe(video);
  }

  // "Look away" demo: blur 0.7 s after the cursor leaves, clear 0.15 s after it returns - like Umbra.
  const tryEl = document.getElementById("try");
  const hint = document.getElementById("try-hint");
  if (tryEl) {
    let timer = null;
    const set = (away) => {
      tryEl.classList.toggle("away", away);
      hint.classList.toggle("away", away);
      hint.textContent = away ? "Looked away - screen hidden." : "Looking - screen visible.";
    };
    const leave = () => { clearTimeout(timer); timer = setTimeout(() => set(true), 700); };
    const enter = () => { clearTimeout(timer); timer = setTimeout(() => set(false), 150); };
    tryEl.addEventListener("mouseleave", leave);
    tryEl.addEventListener("mouseenter", enter);
    tryEl.addEventListener("blur", leave);
    tryEl.addEventListener("focus", enter);
    const touch = document.getElementById("try-touch");
    touch.addEventListener("click", (e) => {
      e.stopPropagation();
      const away = !tryEl.classList.contains("away");
      set(away);
      touch.textContent = away ? "Tap to look back" : "Tap to look away";
    });
    // Leaving the browser tab counts as looking away too.
    document.addEventListener("visibilitychange", () => { if (document.hidden) set(true); });
  }

  // Cover-style tabs in the features grid.
  const tabs = document.querySelectorAll(".seg [role=tab]");
  const modeImg = document.getElementById("mode-img");
  tabs.forEach((tab) => tab.addEventListener("click", () => {
    tabs.forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
    modeImg.src = tab.dataset.src;
    modeImg.alt = `${tab.textContent} cover style`;
  }));

  // Manual: highlight the section in view.
  const links = [...document.querySelectorAll(".toc a")];
  const secs = links.map((a) => document.querySelector(a.getAttribute("href"))).filter(Boolean);
  if ("IntersectionObserver" in window && secs.length) {
    const io = new IntersectionObserver((entries) => entries.forEach((e) => {
      if (e.isIntersecting) links.forEach((a) => a.classList.toggle("active", a.getAttribute("href") === `#${e.target.id}`));
    }), { rootMargin: "-25% 0px -65% 0px" });
    secs.forEach((s) => io.observe(s));
  }
})();
