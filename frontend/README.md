# SmartCore Vue workbench

The production SPA is built into `app/web/dist` by the multi-stage Docker build and served by FastAPI at `/work`.

```bash
npm install
npm run type-check
npm run test
npm run build
npm run test:e2e
```

The legacy workbench remains temporarily available at `/work-legacy` for rollback during the migration release window.
