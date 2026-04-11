# Frontend

This directory contains the Vue 3 + TypeScript UI for the target allocation and strategy backtest page. The app is built with Vite and served by Flask from the compiled `frontend/dist` directory.

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

The Vite dev server proxies `/api` requests to `http://127.0.0.1:5000`, so run the Flask backend on port `5000` when using dev mode.

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
- `api.ts`: Wraps calls to `/api/weights`, `/api/assets`, `/api/backtests/*`, and `/api/stocks/search`.
- `components/AppHeader.vue`: Renders the app title, DB connection state, clock, and asset dictionary entry point.
- `components/AppNav.vue`: Renders the top-level allocation/backtest tabs.
- `components/AllocationToolbar.vue`: Renders allocation stats, filters, refresh, and add actions.
- `components/AllocationTable.vue`: Renders allocation rows and row actions.
- `components/AllocationModal.vue`: Renders the create/update allocation form.
- `components/AssetDictionaryModal.vue`: Renders the allowed-asset dictionary editor.
- `components/BacktestPanel.vue`: Renders preset selection, Tushare search inputs, metrics, chart, and signal table.
- `components/ToastNotice.vue`: Renders request feedback.
- `composables/useAllocations.ts`: Loads and edits target allocation rows, products, allowed assets, and allocation form state.
- `composables/useBacktest.ts`: Loads preset strategies, runs backtests, manages Tushare stock autocomplete, and shapes chart data.
- `composables/useClock.ts`: Maintains the header clock.
- `composables/useToast.ts`: Provides success/error notifications.
- `types.ts`: Defines the API responses and UI data models used by the modules above.

## UI Features

- **Target allocation table**: Filters by date/product, displays weights with progress bars, and supports edit/delete actions.
- **Allocation modal**: Handles create/update flow, required-field validation, and weight-total warnings.
- **Asset dictionary modal**: Maintains the allowed asset list used by the allocation form.
- **Backtest panel**: Runs preset strategies on mock or Tushare data, displays metrics, signal rows, and a compact equity chart.
- **Stock autocomplete**: Searches the local A-share stock index and normalizes selected symbols to Tushare `ts_code`.
- **Status and toast feedback**: Shows DB connection state and request outcomes without blocking the page.

## Build Contract

Flask serves the UI from `frontend/dist`. If `dist/index.html` does not exist, the Flask route returns a setup error telling the developer to run:

```bash
npm install
npm run frontend:build
```
