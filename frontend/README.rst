Frontend
========

React 19 + Vite 8 + Tailwind 4 dashboard for TaraMeteo.

Stack
-----

- TanStack Query for server state (polling every 30s).
- nuqs for URL-as-source-of-truth for dashboard state (sensors, date range).
- recharts for charts, with a colorblind-safe palette.
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

Once the backend exposes ``openapi.json``, run:

.. code-block:: shell

   curl -o openapi.json http://localhost/api/openapi.json
   npm run generate:types
