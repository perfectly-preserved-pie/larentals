# CSS conventions

The app uses plain CSS served from `assets/`. Keep component documentation next to the rules it describes. Start each stylesheet with a short comment naming its scope, important state classes, theme behavior, and any load-order dependency. Add a local comment where a selector exists to solve a non-obvious layout or library issue. Avoid comments that merely repeat declarations.

CSS has no docstrings or static type annotations for selectors. Use CSS value syntax in comments to describe custom property contracts. For example:

```css
:root {
  /* <length>: width of the desktop filter column. */
  --filter-panel-width: clamp(320px, 25vw, 400px);
}
```

## Custom property contracts

| Owner | Properties | Expected value | Scope |
| --- | --- | --- | --- |
| `responsive-filters.css` | `--filter-panel-width` | `<length>` | Root; desktop grid and drawer |
| `responsive-filters.css` | `--filter-panel-surface`, `--filter-panel-border`, `--filter-panel-text`, `--filter-panel-accent`, `--filter-panel-accent-hover` | `<color>` | Root; dark mode overrides each color |
| `responsive-filters.css` | `--filter-panel-shadow` | `<shadow>` | Root; drawer shadow |
| `results-panel.css` | `--results-panel-width`, `--results-detail-max-height` | `<length>` | Root; desktop results column and detail cap |
| `results-panel.css` | `--results-row-open-hover` | `<color>` | Root; dark mode override |
| `distribution.css` | `--dist-height`, `--dist-overlap` | `<length>` | Root; histogram and slider alignment |
| `mcp-docs.css` | `--mcp-*` | `<color>` | `.mcp-docs`; dark mode replaces values on that element |
| `dmc-dark-mode.css` | `--wttl-dark-*` | `<color>` | Dark root; shared palette for dark overrides |

`--Dash-*`, `--bs-*`, `--mantine-*`, and `--ag-*` belong to Dash, Bootstrap, Mantine, or AG Grid. Follow those libraries' value contracts when changing them. Keep their declarations close to the relevant integration rules.

`@property` can register a custom property with a browser-enforced syntax, inheritance setting, and initial value. Registration affects runtime behavior, so use it only when a specific property needs that behavior and has been checked in both themes. These comments describe expected values without changing the cascade.

KSS is useful when a project generates a style guide from stylesheet comments. This app has no KSS generator or component examples, so the local comments and this table are the lightweight convention. Atomic CSS describes a class architecture rather than a documentation or type system; the existing component classes remain the source of truth.
