// Umbra site: before/after slider, cover-style tabs, screenshot lightbox, manual TOC highlight.
(() => {
  // Before / after comparison
  const compare = document.getElementById("compare");
  if (compare) {
    const range = compare.querySelector(".compare-range");
    const set = (v) => compare.style.setProperty("--pos", `${v}%`);
    range.addEventListener("input", () => set(range.value));
    set(range.value);
  }

  // Cover-style tabs
  const tabs = document.querySelectorAll(".modes [role=tab]");
  const modeImg = document.getElementById("mode-img");
  tabs.forEach((tab) =>
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.setAttribute("aria-selected", String(t === tab)));
      modeImg.src = tab.dataset.src;
      modeImg.alt = tab.dataset.alt;
    })
  );

  // Lightbox for gallery shots
  const box = document.getElementById("lightbox");
  if (box && typeof box.showModal === "function") {
    const img = box.querySelector("img");
    const caption = box.querySelector(".lightbox-caption");
    document.querySelectorAll(".shot").forEach((shot) =>
      shot.addEventListener("click", (e) => {
        e.preventDefault();
        img.src = shot.getAttribute("href");
        img.alt = shot.querySelector("img").alt;
        caption.textContent = shot.querySelector("span").textContent;
        box.showModal();
      })
    );
    box.addEventListener("click", (e) => { if (e.target === box) box.close(); });
  }

  // Highlight the manual section in view
  const links = [...document.querySelectorAll(".toc a")];
  const targets = links.map((a) => document.querySelector(a.getAttribute("href"))).filter(Boolean);
  if ("IntersectionObserver" in window && targets.length) {
    const io = new IntersectionObserver(
      (entries) => entries.forEach((en) => {
        if (en.isIntersecting) {
          links.forEach((a) => a.classList.toggle("active", a.getAttribute("href") === `#${en.target.id}`));
        }
      }),
      { rootMargin: "-20% 0px -70% 0px" }
    );
    targets.forEach((t) => io.observe(t));
  }
})();
