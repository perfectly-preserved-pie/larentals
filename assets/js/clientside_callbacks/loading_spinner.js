// Shared map-loading overlay logic for both initial data load and filter-driven refreshes.
window.dash_clientside = Object.assign({}, window.dash_clientside, {
  clientside: Object.assign({}, window.dash_clientside && window.dash_clientside.clientside, {
    showMapSpinner: function() {
      return {
        position: "absolute",
        inset: "0",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: "rgba(0, 0, 0, 0.25)",
        zIndex: "10000",
      };
    },
    loadingMapSpinner: function(geojsonData, layerData, layerLoadingState) {
      const base = {
        position: "absolute",
        inset: "0",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: "rgba(0, 0, 0, 0.25)",
        zIndex: "10000",
      };

      const layerLoading = Boolean(layerLoadingState && layerLoadingState.is_loading);
      if (layerLoading) {
        base.display = "flex";
        return base;
      }

      const hasSourceData = geojsonData != null && geojsonData.features != null;
      const hasLayerData = layerData != null && layerData.features != null;
      base.display = hasSourceData && hasLayerData ? "none" : "flex";
      return base;
    },

  })
});
