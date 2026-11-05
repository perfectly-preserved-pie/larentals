(function () {
  "use strict";

  /**
   * Label ZIP and place chips while preserving the resolver's original text.
   * React creates text nodes for labels, and removal uses Mantine's supplied handler
   * so custom styling does not change tag values, keyboard deletion or disabled state.
   * @param {object} props Mantine pill value, removal handler and disabled state.
   * @returns {object} React element representing one removable location chip.
   */
  function renderLocationPill(props) {
    const value = String(props.value || "");
    const isZip = /^(?:ZIP(?:\s+code)?\s*)?\d{5}(?:-\d{4})?$/i.test(value.trim());
    const kind = isZip ? "zip" : "place";
    const create = window.React.createElement;
    return create("span", {
      className: `mantine-TagsInput-pill location-pill location-pill--${kind}`,
      "data-location-kind": kind,
      title: `${isZip ? "ZIP code" : "Area"}: ${value}`,
    },
    create("span", { className: "location-pill__kind" }, isZip ? "ZIP " : "Area "),
    create("span", { className: "location-pill__label" }, value),
    create("button", {
      type: "button",
      className: "location-pill__remove",
      "aria-label": `Remove ${value}`,
      disabled: Boolean(props.disabled),
      onMouseDown: event => event.preventDefault(),
      onClick: event => { event.stopPropagation(); props.onRemove(); },
    }, create("span", { "aria-hidden": true }, "×")));
  }

  window.dashMantineFunctions = Object.assign({}, window.dashMantineFunctions, { renderLocationPill });
})();
