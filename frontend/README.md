# PUGA Navigator

Offline camera-trap triage and individual tiger movement intelligence
front end for Pench Tiger Reserve, built with TanStack Start + React.

This talks to the PUGA FastAPI backend (see the `backend/` project) over
`http://localhost:8000` by default — no internet connection is required at
runtime; everything (fonts, icons, map tiles config, styling) is bundled
locally.

## Setup

```bash
bun install   # or: npm install
```

## Run

```bash
bun run dev   # or: npm run dev
```

Opens on http://localhost:5173. Set the backend URL from the in-app
Settings page (stored in `localStorage`); it defaults to
`http://localhost:8000`.

## Build

```bash
bun run build
bun run preview
```

## Layout

- `src/routes/` — pages (dashboard, tiger catalogue, map/occupancy, ingest, review queue, settings)
- `src/lib/puga/` — API client, occupancy math, alert/deviation logic, CSV/GeoJSON export
- `src/components/` — UI (shadcn/radix-based) + map components
