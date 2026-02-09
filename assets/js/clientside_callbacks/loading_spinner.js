// A clientside callback to hide or show a Loading spinner overlay based on the presence of GeoJSON data in the map layer.
window.dash_clientside = Object.assign({}, window.dash_clientside, {
  clientside: Object.assign({}, window.dash_clientside && window.dash_clientside.clientside, {
    loadingMapSpinner: function(geojsonData, layerData) {
      const base = {
        position: "absolute",
        inset: "0",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: "rgba(0, 0, 0, 0.25)",
        zIndex: "10000",
      };

      const triggered = dash_clientside.callback_context.triggered;
      const triggerId = triggered && triggered.length > 0
        ? triggered[0].prop_id.split('.')[0]
        : null;

      if (triggerId === "buy_geojson" || triggerId === "lease_geojson") {
        const hasFeatures = layerData != null && layerData.features != null;
        base.display = hasFeatures ? "none" : "flex";
        return base;
      }

      const hasFeatures = geojsonData != null && geojsonData.features != null;
      base.display = hasFeatures ? "none" : "flex";
      return base;
    }
  })
});