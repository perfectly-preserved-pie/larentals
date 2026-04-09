// A clientside callback to hide or show a Loading spinner overlay based on the presence of GeoJSON data in the map layer.
const LAZY_LAYER_NAMES = {
  oil_well: "Oil & Gas Wells",
  crime: "Crime",
  farmers_markets: "Farmers Markets",
  breakfast_burritos: "Breakfast Burritos",
  supermarkets_grocery: "Supermarkets & Grocery Stores",
  parking_tickets_density: "Parking Tickets Heatmap (2025)",
};

function hiddenMapSpinner() {
  return {
    position: "absolute",
    inset: "0",
    display: "none",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(0, 0, 0, 0.25)",
    zIndex: "10000",
  };
}

function hasPendingLazyLayer(selectedOverlays, currentData, layerIds) {
  if (!Array.isArray(selectedOverlays) || !Array.isArray(layerIds)) {
    return false;
  }

  const payloads = Array.isArray(currentData) ? currentData : [];
  for (let index = 0; index < layerIds.length; index += 1) {
    const layerKey = layerIds[index] && layerIds[index].layer;
    const overlayName = LAZY_LAYER_NAMES[layerKey];
    if (!overlayName) {
      continue;
    }

    if (selectedOverlays.includes(overlayName) && payloads[index] == null) {
      return true;
    }
  }

  return false;
}

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
    showLazyLayerSpinnerOnToggle: function(selectedOverlays, layerIds, currentData) {
      if (hasPendingLazyLayer(selectedOverlays, currentData, layerIds)) {
        return window.dash_clientside.clientside.showMapSpinner();
      }

      return window.dash_clientside.no_update;
    },
    syncLazyLayerSpinner: function(currentData, selectedOverlays, layerIds) {
      if (!Array.isArray(layerIds)) {
        return window.dash_clientside.no_update;
      }

      if (hasPendingLazyLayer(selectedOverlays, currentData, layerIds)) {
        return window.dash_clientside.clientside.showMapSpinner();
      }

      return hiddenMapSpinner();
    },
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
