# AquaSignal

AquaSignal is a standalone React application for demonstrating short-horizon
waterlogging intelligence across scoped Mumbai and Pune monitoring areas. It
includes an OpenStreetMap/Leaflet workspace, forecast exploration, response
intelligence, demo authentication, and browser-persistent citizen reports.

The application has **no Figma Make runtime dependency**. The `.figma/`
directory is retained only as optional design/workspace tooling and is not
imported by the application or production build.

## Requirements

- Node.js 22 or later
- npm 10+ or pnpm 10+

## Install and run

Using npm:

```bash
npm install
npm run dev
```

Using the repository's pnpm lockfile:

```bash
pnpm install
pnpm dev
```

Vite defaults to `http://localhost:5173`. Set `PORT` to use another port.

## Quality checks

```bash
npm run typecheck
npm run build
npm run preview
```

Equivalent `pnpm` commands are supported.

## Configuration

Copy the example file for local overrides:

```bash
cp .env.example .env.local
```

All variables are optional in the current local demo:

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_URL` | empty | Future backend API base URL |
| `VITE_AUTH_MODE` | `demo` | Authentication adapter selection |
| `VITE_REPORT_STORAGE` | `local` | Report persistence adapter selection |
| `VITE_MAP_TILE_URL` | OpenStreetMap | Browser-safe public tile template |
| `VITE_MAP_ATTRIBUTION` | OSM attribution | Required map attribution |

`VITE_*` values are exposed to browser code. Never put database passwords,
private provider credentials, or service-role keys in them.

## Architecture

- `src/App.tsx` — current UI composition and application navigation
- `src/config.ts` — environment-derived public runtime configuration
- `src/data/geography.ts` — Mumbai/Pune areas and map centres
- `src/services/auth.ts` — replaceable demo authentication adapter
- `src/services/reports.ts` — replaceable citizen-report persistence adapter
- `src/index.css` — AquaSignal design system and responsive layouts
- `vite.config.ts` — standard React/Tailwind Vite configuration

### Authentication

The default adapter is explicitly a **local demo session**, not production
security. It validates forms but stores only session metadata (name/email and
timestamp); passwords are never persisted. Replace `authService` with a real
OIDC, hosted authentication, or backend session adapter before production use.

### Citizen reports

The default report adapter stores reports in `localStorage`. Reports survive
refreshes and logout in the same browser but are not shared across users or
devices. The report schema includes city, area, coordinates, severity,
description, timestamps, status, and an optional evidence reference.

For shared production storage, implement an API adapter backed by PostgreSQL
and PostGIS and set `VITE_API_URL`. Server credentials must remain server-side.

### Maps and forecasts

Leaflet consumes an authorised OpenStreetMap-compatible tile endpoint.
Forecasts, risk overlays, analytics, and model explanations are illustrative
demonstration data and are labelled accordingly. No live ML model, rainfall
feed, geocoder, routing engine, or validated model-performance API is connected.

## Deployment

Build static assets with:

```bash
npm run build
```

Deploy the generated `dist/` directory to any static host. Client-side routes
such as `/signin`, `/signup`, and `/app` require an SPA fallback to
`/index.html`.

- Netlify-compatible fallback: `public/_redirects`
- Vercel rewrite configuration: `vercel.json`
- Nginx: use `try_files $uri $uri/ /index.html;`

Configure environment variables in the chosen host before building. Confirm
that its Content Security Policy permits the configured map tile provider.

## Migration notes

Removed from the runtime:

- Figma-generated HTML comment slots
- `.figma/make/site.json` build-time import
- Figma site configuration, error-overlay replay, refresh fallback, and Make
  Kit Vite plugins
- `FIGMA_PUBLIC_URL` and `FIGMA_DEV_SERVER_HOST` assumptions

Retained:

- React 19, TypeScript, Vite, and Tailwind CSS
- Leaflet and OpenStreetMap-compatible map tiles
- Existing AquaSignal interface and workflows
- `.figma/` design tooling files, which are now optional and runtime-independent

## Known limitations

- Demo authentication is not secure production authentication.
- Reports are local to one browser until an API adapter is implemented.
- Forecasts and risk geometry are illustrative rather than live model output.
- Geocoding, shared evidence uploads, real routing, and backend review auditing
  require external services.
