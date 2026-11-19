# WhereToLive.LA design

WhereToLive.LA should feel like a hand-built Los Angeles housing directory from the early 2010s. Someone should be able to land on a page, recognize the place, and get straight to a listing or a setup instruction. The downtown ASCII illustration on `/mcp` is the visual reference. The maps on `/` and `/buy` apply the same choices to a denser working interface.

## Design decisions

- Start with what the visitor came to do. A renter on a phone should be able to see the map, narrow the search, and open a listing. Someone setting up MCP should be able to find their client and copy the right command. Let that sequence determine what gets space and emphasis.
- Reuse complete flows as well as colors and components. For a new map filter, follow how the existing filters open, preview, apply, and clear on mobile. Keep shared choices in shared styles and components so future changes carry across both maps.
- Look to local references for character. Use actual LA landmarks, street maps, or neighborhood guides when exploring illustrations and layouts. The ASCII skyline earns its place because it depicts downtown LA. Give other flourishes a similarly specific reason to be there.
- Treat the first working version as a draft. Try the task from start to finish with realistic data. For a filter change, try zero results and check how the visitor recovers. For a setup change, use the copy control and check what lands on the clipboard. Tighten awkward transitions and remove elements that add a step or repeat information.

These principles draw on Katie Dill’s Stripe talk *Raise the Ceiling*, especially the sections on point of view (05:45), encoding standards (09:00), reviewing the full experience (12:26), and creative exploration (16:33).

## Color and type

Use the semantic properties in [site-theme.css](assets/css/site-theme.css). Change a shared color there so the maps, setup guide, and menus rendered outside the page tree can follow it in both themes.

| Role | Application |
| --- | --- |
| Masthead | Deep blue-green with near-white lettering and a thin clay-colored rule. Use it for identity and major panel headings. |
| Paper and ink | Cool off-white reading surfaces, pale blue-gray sidebars, and slate text and borders. Dark mode uses deep slate surfaces with cool light text. |
| Links and actions | Underline text links. Use muted clay for the current navigation item and a visible current-page marker. Pair selection color with a check, marker, border, or text change. |
| Type | Georgia for the wordmark and reading headings, Verdana for navigation, instructions, controls, prices, and listing details. Reserve Courier for code and ASCII art. Use the shared system font stacks. |

## Page composition

- On reading pages, use a bounded paper column, a compact masthead, a contents list, and sections separated by rules. A subtle repeating dot pattern belongs in the margins.
- On maps, give the viewport to the map. Put identity and navigation in the desktop filter sidebar. Use the results column like a directory, with aligned prices, fine rules, and a clear selected row. On phones, keep the small map toolbar and move detailed controls into the drawer.
- Use rectangular buttons, thin edges, compact spacing, and a modest bevel where it suggests a pressable control. Reserve rounded shapes for controls or symbols whose shape carries meaning, such as radio buttons and clustered pins.
- Favor a useful link, table, or list over a row of promotional cards. Give each heading, badge, and caption a job. Keep the basemap legible and preserve the relationship between data colors and their legends.

Keep the existing Font Awesome icons alongside navigation and action labels. Hide decorative icons from screen readers so each label is announced once.

## ASCII and accessibility

Use ASCII as a local signature. The original downtown skyline and San Gabriel ridgeline live in [site_identity.py](functions/site_identity.py). Render them as preformatted monospace text with ligatures disabled. Keep the drawing intact across viewport sizes. The large illustration has a single accessible description, while its small decorative repeat beside the wordmark is hidden from assistive technology.

Check a changed screen in light and dark mode, at a phone width and a desktop width. Try the actual interaction, including keyboard focus and selected states. On the maps, pay attention to the filter drawer, controls above the tiles, and listing details. Keep touch targets usable even where the visual treatment is compact.

See [CSS conventions](docs/CSS.md) for stylesheet ownership and framework variables.
