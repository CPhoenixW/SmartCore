# SmartCore Vue workbench

The production SPA is built into `app/server/web/dist` by the multi-stage Docker build and served by FastAPI at `/work`.

```bash
npm install
npm run type-check
npm run test
npm run build
npm run test:e2e
```

The Vue workbench is the only web-panel implementation. When `app/server/web/dist` is absent, `/work` returns HTTP 503 so deployment errors are explicit.
