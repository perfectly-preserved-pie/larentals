(() => {
  const feedbackTimers = new WeakMap();
  const themeKey = "mantine-color-scheme-value";
  const root = document.documentElement;
  let storedTheme;
  try {
    storedTheme = localStorage.getItem(themeKey);
  } catch {
    // The guide can use a temporary theme when browser storage is disabled.
  }
  root.dataset.mantineColorScheme = storedTheme === "dark" || (
    storedTheme !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches
  ) ? "dark" : "light";

  document.addEventListener("DOMContentLoaded", () => {
    const themeSwitch = document.getElementById("color-scheme-switch");
    themeSwitch.checked = root.dataset.mantineColorScheme === "dark";
    themeSwitch.addEventListener("change", () => {
      const theme = themeSwitch.checked ? "dark" : "light";
      root.dataset.mantineColorScheme = theme;
      try {
        localStorage.setItem(themeKey, theme);
      } catch {
        // The current document still uses the selected theme.
      }
    });
  });

  /**
   * Copy an MCP setup snippet and announce the outcome.
   * Read the code's text directly so copied commands and YAML keep their
   * original spacing and line breaks.
   * @param {MouseEvent} event Native click from the pointer or keyboard.
   */
  async function copyMcpSnippet(event) {
    const button = event.target.closest(".mcp-docs button[data-mcp-copy]");
    if (!button) return;

    const code = document.getElementById(button.dataset.mcpCopy);
    const caption = button.firstElementChild;
    const status = button.nextElementSibling;
    try {
      await navigator.clipboard.writeText(code.textContent);
      caption.textContent = "Copied!";
      status.textContent = "Copied to clipboard.";
    } catch {
      caption.textContent = "Copy failed";
      status.textContent = "Copy failed. Select and copy the text.";
    }

    clearTimeout(feedbackTimers.get(button));
    feedbackTimers.set(button, setTimeout(() => {
      caption.textContent = button.getAttribute("aria-label");
      status.textContent = "";
    }, 2200));
  }

  document.addEventListener("click", copyMcpSnippet);
})();
