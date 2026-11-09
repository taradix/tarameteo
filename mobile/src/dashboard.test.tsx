import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react-native";
import { default as i18n } from "i18next";
import type { ReactNode } from "react";

import Dashboard from "./app/index";
import "./i18n";

// Lives outside src/app/ because Expo Router treats every file there as a route.

const BASE = "https://meteo.taram.ca";
const hoursAgo = (hours: number) => new Date(Date.now() - hours * 3600_000).toISOString();

function reading(hours: number, temperature: number, pressure: number) {
  return { sensor: "s1", timestamp: hoursAgo(hours), temperature, humidity: 55.4, pressure, latitude: 0, longitude: 0 };
}

// The trend compares the latest reading with the one at least 3 h before it: reading(4).
const readings = [reading(4, 18, 1020), reading(3, 25, 1019), reading(0.7, 21.46, 1013.2)];
const aggregate = {
  sensor: "agg",
  timestamp: "2026-11-08T05:00:00Z",
  temperature_min: -1,
  temperature_avg: 3.5,
  temperature_max: 8.1,
  rain: 4.2,
  snow: null,
};

// Routes match the path only, since start depends on the clock; unlisted paths answer 404.
function stubFetch(routes: Record<string, unknown>) {
  globalThis.fetch = jest.fn(async (url: string) => {
    const body = routes[url.split("?")[0]];
    if (body === undefined) return new Response("", { status: 404, statusText: "Not Found" });
    return body instanceof Response ? body : new Response(JSON.stringify(body));
  }) as typeof fetch;
}

function wrapper({ children }: { children: ReactNode }) {
  // gcTime: Infinity skips the 5-minute cache cleanup timer that would keep Jest alive.
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(async () => {
  await i18n.changeLanguage("en");
});

test("shows a card per known sensor kind, skipping unknown ones", async () => {
  stubFetch({
    [`${BASE}/api/sensors`]: {
      sensors: [
        { name: "s1", kind: "timeseries" },
        { name: "s2", kind: "timeseries" },
        { name: "agg", kind: "aggregate" },
        { name: "future", kind: "forecast" },
      ],
    },
    [`${BASE}/api/sensors/s1/weather`]: readings,
    [`${BASE}/api/sensors/s2/weather`]: [],
    [`${BASE}/api/sensors/agg/weather/aggregate`]: [aggregate],
  });
  await render(<Dashboard />, { wrapper });

  // Temperature 18 → 21.5 is rising; pressure 1020 → 1013 is falling.
  expect(await screen.findByText("21.5 °C")).toBeOnTheScreen();
  expect(screen.getByText(/min 18\.0 · max 25\.0/)).toBeOnTheScreen();
  expect(screen.getByLabelText("rising")).toBeOnTheScreen();
  expect(screen.getByLabelText("falling")).toBeOnTheScreen();
  expect(screen.getByText("42 min ago")).toBeOnTheScreen();
  expect(screen.getByText("No data in the last 24 h.")).toBeOnTheScreen();
  expect(await screen.findByText("min -1.0 · avg 3.5 · max 8.1 °C")).toBeOnTheScreen();
  expect(screen.getByText("rain 4.2 mm · snow – mm")).toBeOnTheScreen();
  expect(screen.queryByText("future")).not.toBeOnTheScreen();
});

test("formats numbers for the app language", async () => {
  await i18n.changeLanguage("fr");
  stubFetch({
    [`${BASE}/api/sensors`]: { sensors: [{ name: "s1", kind: "timeseries" }] },
    [`${BASE}/api/sensors/s1/weather`]: readings,
  });
  await render(<Dashboard />, { wrapper });

  expect(await screen.findByText("21,5 °C")).toBeOnTheScreen();
  expect(screen.getByText("il y a 42 min")).toBeOnTheScreen();
});

test("pull to refresh refetches the sensors and their readings", async () => {
  stubFetch({
    [`${BASE}/api/sensors`]: { sensors: [{ name: "s1", kind: "timeseries" }] },
    [`${BASE}/api/sensors/s1/weather`]: readings,
  });
  await render(<Dashboard />, { wrapper });
  await screen.findByText("21.5 °C");
  jest.mocked(globalThis.fetch).mockClear();

  // The RefreshControl is a prop of the scroll view, not an ancestor, so fireEvent can't reach it.
  let list = screen.getByText("s1");
  while (!list.props.refreshControl) list = list.parent!;
  await act(() => list.props.refreshControl.props.onRefresh());

  await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(2));
  expect(globalThis.fetch).toHaveBeenCalledWith(`${BASE}/api/sensors`);
  expect(globalThis.fetch).toHaveBeenCalledWith(expect.stringMatching(`^${BASE}/api/sensors/s1/weather\\?start=`));
});

test("shows an empty state without sensors", async () => {
  stubFetch({ [`${BASE}/api/sensors`]: { sensors: [] } });
  await render(<Dashboard />, { wrapper });

  expect(await screen.findByText("No sensors.")).toBeOnTheScreen();
});

test("shows the error when the sensor list fails", async () => {
  stubFetch({ [`${BASE}/api/sensors`]: new Response("", { status: 500, statusText: "Server Error" }) });
  await render(<Dashboard />, { wrapper });

  expect(await screen.findByText("ApiError: 500 Server Error")).toBeOnTheScreen();
});
