window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: {
        toggleVisibility: function(n_clicks, current_style) {
            if (n_clicks === undefined) {
                // PreventUpdate equivalent
                return window.dash_clientside.no_update;
            }

            var displayStyle = (n_clicks % 2 === 0) ? 'block' : 'none';
            var buttonText = (n_clicks % 2 === 0) ? "Hide" : "Show";
            
            return [{display: displayStyle}, buttonText];
        },
        toggleCollapse: function(n_clicks, is_open) {
            if (n_clicks === undefined) {
                return [false, "More Options"];
            }
            return [!is_open, is_open ? "More Options" : "Less Options"];
        }
    }
});