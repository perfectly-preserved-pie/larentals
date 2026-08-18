(function () {
  "use strict";

  /**
   * Replace the maximum handle's internal sentinel value with its user-facing
   * meaning. Dash tooltip transforms receive only the number, so this small DOM
   * adapter supplies the missing per-slider context.
   * @returns {void}
   */
  function syncOpenEndedTooltips() {
    document.querySelectorAll(".range-filter__open-ended-slider").forEach(function (slider) {
      const maximumThumb = slider.querySelector(
        '.dash-slider-thumb[aria-label="Maximum"]',
      );
      if (!maximumThumb) return;

      const selected = Number(maximumThumb.getAttribute("aria-valuenow"));
      const maximum = Number(maximumThumb.getAttribute("aria-valuemax"));
      if (!Number.isFinite(selected) || !Number.isFinite(maximum)) return;

      if (selected >= maximum) {
        maximumThumb.setAttribute("aria-valuetext", "Unlimited maximum");
        maximumThumb.setAttribute("data-unlimited", "true");
        const content = maximumThumb.querySelector(".dash-slider-tooltip > div");
        if (content && content.textContent !== "Unlimited") content.textContent = "Unlimited";
      } else {
        maximumThumb.removeAttribute("aria-valuetext");
        maximumThumb.removeAttribute("data-unlimited");
      }
    });
  }

  const observer = new MutationObserver(syncOpenEndedTooltips);
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["aria-valuenow"],
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", syncOpenEndedTooltips, { once: true });
  } else {
    syncOpenEndedTooltips();
  }
}());
