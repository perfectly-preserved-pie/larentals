(function () {
  "use strict";
  const WRAP = ".range-filter__hybrid-slider-wrap";

  function update(strip, x) {
    const rect = strip.getBoundingClientRect();
    if (!rect.width) return;
    const min = Number(strip.dataset.min), max = Number(strip.dataset.max);
    const ratio = Math.max(0, Math.min(1, (x - rect.left) / rect.width));
    const value = Math.round(min + ratio * (max - min));
    const line = strip.querySelector(".dist__cursor");
    const label = strip.querySelector(".dist__readout");
    line.style.left = ratio * 100 + "%";
    label.style.left = ratio * 100 + "%";
    label.style.transform = ratio < .12 ? "translateX(0)" : ratio > .88 ? "translateX(-100%)" : "translateX(-50%)";
    label.textContent = (strip.dataset.prefix || "") + value.toLocaleString("en-US") + (strip.dataset.suffix || "");
    strip.classList.add("dist--hovered");
  }

  function stripFor(target) {
    const wrap = target && target.closest ? target.closest(WRAP) : null;
    return wrap && wrap.querySelector(".dist");
  }

  document.addEventListener("pointermove", function (event) {
    const strip = stripFor(event.target);
    if (strip) update(strip, event.clientX);
  }, true);
  document.addEventListener("pointerout", function (event) {
    const wrap = event.target.closest && event.target.closest(WRAP);
    if (!wrap || wrap.contains(event.relatedTarget)) return;
    const strip = wrap.querySelector(".dist");
    if (strip) strip.classList.remove("dist--hovered");
  }, true);
})();
