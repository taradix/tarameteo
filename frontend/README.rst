Frontend
========

React 19 + Vite 8 + Tailwind 4 dashboard for TaraMeteo.

Stack
-----

- TanStack Query for server state; live ranges stream readings over SSE.
- nuqs for URL-as-source-of-truth for dashboard state (sensors, date range).
- chart.js (react-chartjs-2, chartjs-plugin-zoom) for charts, with a colorblind-safe palette.
- openapi-typescript for generated API types.
- Vitest + happy-dom + @testing-library/react for tests.

Local development
-----------------

.. code-block:: shell

   make setup        # install deps
   make test         # run vitest
   npm run dev       # start dev server on :5173 (proxies /api to localhost:80)

Type generation
---------------

``src/api-types.ts`` is generated from ``../backend/openapi.json``; after the
backend schema changes, run:

.. code-block:: shell

   npm run openapi
