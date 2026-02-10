window.dash_clientside = Object.assign({}, window.dash_clientside, {
  clientside: Object.assign({}, window.dash_clientside && window.dash_clientside.clientside, {
    themeSwitch: function(switchOn) {
      document.documentElement.setAttribute('data-mantine-color-scheme', switchOn ? 'dark' : 'light');
      document.documentElement.setAttribute('data-bs-theme', switchOn ? 'dark' : 'light');
      return switchOn;
    }
  })
});