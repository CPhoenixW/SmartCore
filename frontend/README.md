# SmartCore Frontend

This directory contains the incremental Vue 3 SPA migration for the SmartCore work panel.

## Development

Run FastAPI on port 8000, then start Vite:

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` and `/agent` requests to `http://127.0.0.1:8000`.

## Validation

```bash
npm run type-check
npm run test
npm run build
```

## Production

The Docker multi-stage build compiles this project and copies `dist/` into `app/web/dist`. FastAPI serves the SPA at `/work-v2`, while the existing `/work` panel remains available during migration.
