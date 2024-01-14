window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(feature, latlng) {
            const customIcon = L.icon({
                iconUrl: '/assets/oil_derrick_icon.png', // URL to your custom icon in assets folder
                iconSize: [20, 20] // Adjust the size as needed
            });
            return L.marker(latlng, {
                icon: customIcon
            });
        }
    }
});