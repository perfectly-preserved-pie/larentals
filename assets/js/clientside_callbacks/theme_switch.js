window.dash_clientside = Object.assign({}, window.dash_clientside, {
  clientside: Object.assign({}, window.dash_clientside && window.dash_clientside.clientside, {
    initializeThemeSwitch: function() {
      const storedScheme = localStorage.getItem("mantine-color-scheme-value") || "auto";
      const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
      return storedScheme === "dark" || (storedScheme === "auto" && prefersDark);
    },

    themeSwitch: function(switchOn) {
      const scheme = switchOn ? "dark" : "light";
      document.documentElement.setAttribute("data-mantine-color-scheme", scheme);
      document.documentElement.classList.remove("auto", "dark", "light");
      document.documentElement.classList.add(scheme);
      localStorage.setItem("mantine-color-scheme-value", scheme);
      return { checked: Boolean(switchOn), colorScheme: scheme };
    }
  })
});
