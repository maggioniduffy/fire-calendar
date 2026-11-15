# Design

Source: canvas "Clima Ideas — Main page wireframe" (https://claude.ai/artifact/LPUfQ1KS8iZA9rkipwoi3Y),
artboard "Mockup con datos de ejemplo" (mockup with sample data; `project/Mockup.dc.html`); the wireframes are not
the goal. Shared rules with clima-ideas. UI copy quoted below is the Spanish text; English lives in
`web/src/i18n/en.ts`.

## UI rules

- No labels, badges or secondary descriptions: hierarchy, color and shape explain.
- Never pure white or pure black: light themes with a cream tone, dark ones with a blue tone.
- Same layout in both themes: same regions and same boxes; only the tokens change.
- Accent reserved for what matters (current month, anomaly, selection).
- Only what works: no navigation, filters or buttons without an action are shown; whatever is not wired up yet
  stays hidden.
- Minimum WCAG AA contrast.

## Layout

### Top bar

Minimum 56 px, `--surface` with texture. Left to right: 28 px logo mark (rounded square `--ctrl` with one
`--on-ctrl` line and one `--accent` baseline); app name; `h1` with the chosen area ("Córdoba"); "NASA Space Apps
2026 · Desafío CONAE" and the author "Faustino Maggioni Duffy". On the right: data note in 12 px mono
`--text-muted` ("FIRMS hasta <date>", i.e. "FIRMS until <date>"), language selector and a 44 px theme button. No
section navigation.

### Left panel

240 px `aside`, one card:

- **Layers:** 18 px checkboxes in 40 px rows: MODIS hot spots, VIIRS hot spots, selected area, localities.
- **Series:** segmented control (Reported / MODIS-eq / VIIRS-eq) inside a `--raised` container with 10 px radius;
  active button `--ctrl`.
- **ENSO phase:** 2×2 segmented control (All / El Niño / La Niña / Neutral) that filters the active months.
- **Period:** two 44 px mono buttons (2000, 2026).
- At the bottom, pinned, a sources line in 12 px `--text-muted`: "FIRMS MODIS C6.1 y VIIRS 375 m, NASA LANCE; ONI NOAA
  CPC".

### Main column

- **Map:** card with flex 1 and a 400 px minimum height; monochrome base map with the slate relief
  (`--relief-0..3`) and `--water`; hot spots as `--accent` marks with a `--casing` outline. Top right, an overlay
  card with the chosen month in 20 px mono and below it a 12 px `--text-muted` line ("N focos en el área", i.e.
  "N hot spots in the area"). Bottom left, the legend, without a border.
- **Row of cards** below the map:
  - **Inspector** (`1 1 300px`): `h2` "Area · month", date range in `--text-muted`, and 28 px rows with the label on
    the left and the mono value on the right: hot spots of the month, median of the month, anomaly (percentile),
    most active month, ENSO phase · ONI, source, data period. At the bottom, a primary `--ctrl` button.
  - **Calendar** (`1.6 1 420px`): one sentence with the main finding on top; the year × month heatmap; and the
    chart of the series against the climatology: bars in `--text`, p25–p75 band in `--secondary` at 0.55 opacity
    and months above p90 in `--accent` with a `--casing` outline.
  - **Most active months** (`1 1 300px`): the count in mono `--text-muted` in the title; 48 px rows with dot, month
    and place, count and date in mono; the chosen row on `--raised` with the dot in `--accent`.
- **Timeline** at the bottom: previous / play / next 44 px buttons (play on `--ctrl`); 2000–2026 track with one
  ENSO phase band per year (El Niño `--ctrl`, La Niña `--border`, Neutral `--bg`), `--accent` marks on the most
  active months and a 5 px `--accent` playhead. Play advances month by month through the map and the inspector.
  El Niño / La Niña / Neutral legend.

### Dashboard tab

The center card has two tabs, **Map** and **Dashboard** (decided 2026-11-15; the original wireframe had none). The
Dashboard shows the selected area as a grid of chart cards on `--raised`, built only from the `/calendar` and
`/stats` payloads:

- A headline total for the period (`key_figures.total`), the cell count and, when it applies, the note that
  VIIRS-eq / MODIS-eq months are estimated from the other sensor.
- Harmonized monthly series with its uncertainty band (always labelled "unverified" for arbitrary areas) and the
  per-sensor reported series; estimated months are dashed. Total per year (partial years drawn lighter).
  Seasonality: the p10–p90 range (wide, light) and the "normal" band p25–p75 (narrower, on top; `--secondary` at 0.55
  opacity) per calendar month, the median line above them and the latest year on top in `--accent` with a `--casing`
  outline. Monthly anomaly: value minus the median of that calendar month, diverging
  blue (below) / orange (above) around a neutral zero line.
- Each card: title, source and period line (from `meta`), a legend, a one-line readout of the hovered or selected
  month, and `CSV` / `PNG` buttons (the CSV holds exactly the plotted rows).
- Charts are linked: hovering a month highlights it in every chart; clicking sets `selection.month`, which the
  calendar uses too. Seasonality has no year of its own, so a click picks that month of the latest year.
- Not shown, because no payload provides them yet: day/night split, FRP distribution, ENSO phase and drought. They
  stay hidden (see "Only what works").

## Surfaces

- No borders between regions. Page background `--bg`, with 8 px padding and 8 px between regions.
- Each panel is a `--surface` card with 8 px radius and 16 px padding.
- Texture (class `.tx`): in light, dots `radial-gradient(rgba(42,52,59,.09) .9px, transparent 1.3px)` at 5 × 5 px
  plus a diagonal shine `linear-gradient(135deg, rgba(255,255,255,.45) 0%, transparent 55%)`; in dark, none.

## Tokens

The values live in `web/src/theme/tokens.css` and `tokens.ts`; a test checks that they match. The names are those
of clima-ideas.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#F1EEE6` | `#16212A` | Page background |
| `--surface` | `#F9F7F2` | `#1F2D37` | Cards and top bar |
| `--raised` | `#EFECE4` | `#2A3A46` | Neutral buttons, selected row |
| `--border` | `#DDD8CD` | `#3E505B` | Thin strokes inside charts |
| `--text` | `#2A343B` | `#ECE7DC` | Text |
| `--text-muted` | `#5F6468` | `#A3AEB4` | Secondary text |
| `--ctrl` | `#3E505B` | `#4D6372` | Primary control |
| `--on-ctrl` | `#F5F2EA` | `#ECE7DC` | Text on `--ctrl` |
| `--accent` | `#8EB8E5` | `#FDDA0D` | Current month, anomaly, selection, hot spot |
| `--secondary` | `#A4AF69` | `#A4AF69` | "Normal" band, climatology |
| `--casing` | `#2A343B` | `#16212A` | Outline of accent marks |
| `--water` | `#3A6E8F` | `#7FA9C6` | Rivers and lakes on the base map |
| `--relief-0` | `#A7AEAF` | `#4E5F6A` | Relief, low |
| `--relief-1` | `#77848A` | `#7D8D96` | Relief, medium |
| `--relief-2` | `#4A5A64` | `#B3BEC4` | Relief, high |
| `--relief-3` | `#2A343B` | `#ECE7DC` | Relief, peaks |

Spacing `--space-1..6` (4, 8, 12, 16, 24, 32 px); radii 4, 8, 12 px.

## Typography

IBM Plex Sans 400/500/600 for body and headings (14 px / 1.4; card titles 14 px / 600, page titles 16 px / 600);
IBM Plex Mono 400/500 with tabular numerals only for numbers, dates and units (class `.num`). Google Fonts in
`index.html`.

## Controls

- 44 px targets, 8 px radius, no border. Neutrals on `--raised`; primary on `--ctrl` with `--on-ctrl`.
- 18 px checkboxes with `accent-color: var(--ctrl)`; 40 px rows.
- Segmented controls: `--raised` container with 10 px radius, active button `--ctrl` with `--on-ctrl` text.
- Visible focus: 2 px ring in `--accent` with a 2 px offset.
- Accent marks on the map and charts carry a `--casing` outline.

## Drag handles

- There are handles for the left panel width, the card row height and the timeline height, placed in the 8 px gaps
  between regions.
- Dragging below the panel's minimum collapses it to 0: the panel is hidden (`hidden`, out of the tab order) and
  the map takes the space. The handle stays on the edge so it can be dragged back.
- Keyboard: arrows resize (16 px), Home collapses, End maximizes, Enter or double click resets the default size.
  `aria-valuemin` is 0 and `aria-valuenow` is 0 when collapsed. The map keeps at least 320 × 200 px.
- Sizes and collapsed state are stored in `localStorage` (`panel-sizes`); invalid or missing keys fall back to the
  default.

## Narrow screens

On screens up to 800 px the left panel is a drawer. The cards stack below the map and the page scrolls; there are
no handles. 16 px side margin and no horizontal scrolling.

## Ramps

- Calendar (count): single-hue sequential that grows in lightness, validated for color blindness (defined in
  SA0.4).
- Anomaly: diverging blue (less than the median) / orange (more), neutral `--raised` center.
- `--secondary` marks the "normal" band (p25–p75).
- ENSO phase (as in the mockup timeline): El Niño `--ctrl`, La Niña `--border`, Neutral `--bg`.
