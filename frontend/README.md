# Frontend

This directory contains the Vue 3 + TypeScript UI for target allocation and signal research/backtest workflows. The app is built with Vite and served by Flask from the compiled `frontend/dist` directory.

## Run

From the project root:

```bash
npm install
npm run frontend:check
npm run frontend:build
uv run -m examples.run_ui_server
```

For local frontend development with Vite:

```bash
npm run frontend:dev
```

The Vite dev server listens on port `5173` and proxies `/api` requests to `http://127.0.0.1:5000`, so run the Flask backend on port `5000` when using dev mode.

The Vite config also enables forwarded-host access for remote IDE previews and port tunnels. Without that setting, preview URLs that rewrite the `Host` header can fail with `403 Forbidden` even when the dev server is running normally.

## Architecture

```text
frontend/
├── index.html          # Vite HTML shell with the #app mount point
├── app.ts              # Vue entrypoint, mounts App.vue
├── App.vue             # Top-level composition wiring and page assembly
├── api.ts              # Typed REST API client
├── components/         # Presentational Vue single-file components
├── composables/        # Feature state and actions
├── types.ts            # Shared frontend data contracts
├── utils.ts            # Formatting and display helpers
├── styles.css          # Shared page styles
└── dist/               # Build output, ignored by git
```

`index.html` should stay thin. Page assembly belongs in `App.vue`, reusable UI markup belongs in `components/`, and reusable state/workflows belong in composables.

## Key Modules

- `App.vue`: Owns tab state and connects composables to the UI modules.
- `app.ts`: Imports global CSS and mounts `App.vue`.
- `api.ts`: Wraps calls to `/api/weights`, `/api/assets`, `/api/signals/*`, and user-signal backtests.
- `components/AppHeader.vue`: Renders the app title, DB connection state, clock, and asset dictionary entry point.
- `components/AppNav.vue`: Renders the top-level navigation tabs.
- `components/AllocationToolbar.vue`: Renders allocation stats, filters, refresh, and add actions.
- `components/AllocationTable.vue`: Renders allocation rows and row actions.
- `components/AllocationModal.vue`: Renders the create/update allocation form.
- `components/AssetDictionaryModal.vue`: Renders the allowed-asset dictionary editor.
- `components/ToastNotice.vue`: Renders request feedback.
- `composables/useAllocations.ts`: Loads and edits target allocation rows, products, allowed assets, and allocation form state.
- `composables/useClock.ts`: Maintains the header clock.
- `composables/useToast.ts`: Provides success/error notifications.
- `types.ts`: Defines the API responses and UI data models used by the modules above.

## UI Features

- **Target allocation table**: Filters by date/product, displays weights with progress bars, and supports edit/delete actions.
- **Allocation modal**: Handles create/update flow, required-field validation, and weight-total warnings.
- **Asset dictionary modal**: Maintains the allowed asset list used by the allocation form.
- **Signal research**: Edits researcher Python signals, includes seeded preset signals, validates the `Signal` contract, runs backtests on mock, Tushare, or local adjusted-main-contract data, and streams live signal events.
- **Status and toast feedback**: Shows DB connection state and request outcomes without blocking the page.

## Build Contract

Flask serves the UI from `frontend/dist`. If `dist/index.html` does not exist, the Flask route returns a setup error telling the developer to run:

```bash
npm install
npm run frontend:build
```

The `/backtest` route redirects to `/signals`, where user-authored and preset-seeded signals share one workflow surface.
