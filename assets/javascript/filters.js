// assets/javascript/filters.js

window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
      // Filter for list price
      listPriceFilter: function (feature, filters) {
        const listPrice = feature.properties.data?.list_price;
        if (listPrice === null || listPrice === undefined) {
          return false; // Exclude properties with missing list price
        }
        return listPrice >= filters.list_price_slider[0] && listPrice <= filters.list_price_slider[1];
      },
  
      // Main GeoJSON filter function
      geojsonFilter: function (feature, context) {
        const filters = context.props.hideout;
        return this.listPriceFilter(feature, filters);
      },
    },
  });