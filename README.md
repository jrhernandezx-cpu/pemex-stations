# Pemex Station Tracker → "Pemex Stations" page

- **Google Sheet:** "Pemex Station Tracker" (tab `Stations`, gid 872432372)
  - Sheet ID: `150ARQcdCe1xlSrNgmFDeTExUBgRmcbjRCUX1Xn3TZfI`
  - URL: https://docs.google.com/spreadsheets/d/150ARQcdCe1xlSrNgmFDeTExUBgRmcbjRCUX1Xn3TZfI/edit
  - Private to J.R. (not shared). Status dropdown: Lead / Planned / Converting / Open / Lost (Lead = possible new station).
  - Owner: jr.hernandezx@gmail.com (JR Hernandez), not shared. Share it from the Sheet's Share button.
  - Stations tab columns (since Nov 19 2026, 3:50 PM): ID, Name, State, City, Address, Status (dropdown, col F),
    Operator or owner contact, Date branded, Date debranded, Cost estimate, Fuel volume or sales, Last updated,
    Notes, Latitude, Longitude (lat/long moved to the far right and narrowed; the connector can't hide columns).
  - Review tab (PRIVATE, never published): Station, Issue, Proposed correction, Source. Remove a row once resolved;
    keep the history in /workspace/pemex-private/changelog.md.
  - Public output: only ID, Name, State, City, Address, Status, Operator, Date branded, Date debranded,
    Cost estimate, Last updated, Latitude, Longitude. Notes and fuel volume never leave the Sheet.
- **Public repo:** https://github.com/jrhernandezx-cpu/pemex-stations
- **Public page:** https://jrhernandezx-cpu.github.io/pemex-stations/ (GitHub Pages, served from the `gh-pages` branch root)

## Files
- `build.py` – reads the Sheet data and writes `index.html` (dark Esri map, red drop pins, counts, All / California / Texas / Leads buttons, sortable table) and refreshes `data/stations.csv`. No dependencies beyond Python 3. It asserts the output has no Lost rows, no inner scroll box, no Leaflet prefix, and none of the strings `Example lead`, `Example data`, or `DEMO`.
- `assets/pemex-logo.png` – PEMEX lockup from the photo J.R. provided (red eagle-in-drop with white outline, white PEMEX wordmark on black). Tight crop; near-black background remapped to #0b0b0b to sit on the black header. Brand red sampled from the mark is #d12203. `build.py` embeds it in the header on every build and stops if it's missing. Publishing pushes `assets/` too.
- `data/stations.csv` – the last Sheet snapshot used for the build.
- `index.html` – the generated page (do not hand-edit; re-run the build).

## Rebuild after editing the Sheet
1. Get the Sheet rows as CSV. Because the Sheet is private, the agent reads it with the
   Google Sheets connector: `read_range` on spreadsheet `150ARQcdCe1xlSrNgmFDeTExUBgRmcbjRCUX1Xn3TZfI`
   with `ranges: [{"sheet": "Stations", "cells": "A1:O500"}]` and `write_to_file: true`.
   (Top-level `sheet`/`cells` args are ignored by the tool and it falls back to the first tab.)
   NEVER read or pass the `Review` tab to the build; build.py only uses the `Stations` range anyway.
   (Or in Sheets: File → Download → CSV, save as `data/stations.csv`.)
2. Build:
   ```bash
   cd /workspace/pemex-tracker
   python3 build.py <connector-output-file-or-csv>   # connector JSON output or a CSV both work
   # or: python3 build.py              # uses data/stations.csv
   # or (only if the Sheet were link-readable): PEMEX_SHEET_ID=150ARQcdCe1xlSrNgmFDeTExUBgRmcbjRCUX1Xn3TZfI python3 build.py --url
   ```
3. Publish: push the new `index.html`, `data/stations.csv`, `build.py` and `README.md` to `main` of
   `jrhernandezx-cpu/pemex-stations` (GitHub connector `push_files`, owner `jrhernandezx-cpu`,
   repo `pemex-stations`, branch `main`) AND the same files to branch `gh-pages` (the branch Pages serves).
   Never push mockup files, `index-leads-demo.html`, or any "Example lead" / "Example data" demo rows.
   GitHub Pages redeploys in about a minute; check https://jrhernandezx-cpu.github.io/pemex-stations/.
   Why gh-pages: the connectors have no Pages-settings API, so Pages was switched on by creating a
   `gh-pages` branch. To serve from `main` instead, J.R. can set Settings → Pages → Branch: main / (root)
   once, after which only `main` needs pushing.

## Page behaviour
- Full-width dark Esri canvas map under a black header with J.R.'s PEMEX logo and a thin condensed Open-stations count (Open only; e.g. "26" with "20 California · 6 Texas").
- Open stations use solid red PEMEX drop pins. Lead, Planned and Converting rows (if any) appear only when the Leads button is selected, as hollow red drop pins, and in the list with a status label.
- Buttons under the map: All (default, Open stations in both states), California, Texas, Leads. Each state and Leads button shows a quiet count. All / California / Texas never include pipeline rows. With no leads, the list shows: "No leads yet. Add a row with Status Lead in the Sheet." Search is kept. Default sort is state, then city. The list is grouped under "California" and "Texas" headings. On a phone the table becomes a stacked list and the four buttons stay on one row.
- Table columns: Station, City, Address, Status. Pin popup: name, address, status, plus operator, dates and cost estimate only when filled.
- Lost rows are excluded from the page and from `data/stations.csv` entirely (no Lost toggle or legend). US Petro stays in the Sheet as Lost.
- Stations without coordinates are listed in the table and named under it ("Not on map yet").
- Map credit is a small "© OpenStreetMap © Esri" line (no Leaflet prefix or leafletjs.com link). Footer: "Updated … CT" in America/Chicago.

## Rules for the data
- Never invent Status, contact, dates, cost estimates or volumes; leave blank until J.R. confirms.
- Only fill Address/Lat/Long when confident; partial matches go in Notes with the reason.
- US Petro (Kingsburg) stays in the Sheet as Lost and is never published on the page or in the public CSV.
