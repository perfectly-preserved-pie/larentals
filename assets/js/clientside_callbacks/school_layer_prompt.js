window.dash_clientside = Object.assign({}, window.dash_clientside, {
  clientside: Object.assign(
    {},
    window.dash_clientside && window.dash_clientside.clientside,
    {
      /**
       * Scroll the school-layer controls into view and briefly spotlight them.
       *
       * @param {number | null | undefined} nClicks
       * @param {string | null | undefined} targetId
       * @returns {Object | undefined}
       */
      focusSchoolLayerControls: function(nClicks, targetId) {
        if (!nClicks || !targetId || typeof document === "undefined") {
          return window.dash_clientside.no_update;
        }

        const target = document.getElementById(targetId);
        if (!target) {
          return window.dash_clientside.no_update;
        }

        target.scrollIntoView({
          behavior: "smooth",
          block: "start",
          inline: "nearest",
        });

        target.classList.remove("school-layer-panel-card--spotlight");
        void target.offsetWidth;
        target.classList.add("school-layer-panel-card--spotlight");

        window.setTimeout(function removeSpotlight() {
          target.classList.remove("school-layer-panel-card--spotlight");
        }, 2200);

        return {
          targetId,
          focusedAt: Date.now(),
        };
      },
    }
  ),
});
