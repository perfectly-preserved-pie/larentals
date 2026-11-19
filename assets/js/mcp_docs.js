(() => {
  const feedbackTimers = new WeakMap();

  /**
   * Copy an MCP setup snippet and announce the outcome.
   * Dash mounts the guide after navigation, so listen on the document and read
   * the code's text directly to preserve the original command and YAML lines.
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
