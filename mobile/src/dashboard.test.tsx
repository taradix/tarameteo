import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react-native";
import { default as i18n } from "i18next";
import type { ReactNode } from "react";

import Dashboard from "./app/index";
import "./i18n";

// Lives outside src/app/ because Expo Router treats every file there as a route.

const BASE = "https://meteo.taram.ca";
const reading = {
  sensor: "s1",
  timestamp: "2026-01-02T03:04:05Z",
  temperature: 21.46,
  humidity: 55.4,
  pressure: 1013.2,
  latitude: 0,
  longitude: 0,
};

// Unlisted URLs answer 404.
function stubFetch(routes: Record<string, unknown>) {
  globalThis.fetch = jest.fn(async (url: string) => {
    const body = routes[url];
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

test("shows the latest reading of each timeseries sensor, skipping aggregate ones", async () => {
  stubFetch({
    [`${BASE}/api/sensors`]: {
      sensors: [
        { name: "s1", kind: "timeseries" },
        { name: "s2", kind: "timeseries" },
        { name: "agg", kind: "aggregate" },
      ],
    },
    [`${BASE}/api/sensors/s1/weather/latest`]: reading,
  });
  await render(<Dashboard />, { wrapper });

  expect(await screen.findByText("21.5 °C · 55 % · 1013 hPa")).toBeOnTheScreen();
  expect(screen.getByText(new Date(reading.timestamp).toLocaleString("en"))).toBeOnTheScreen();
  // s2 has no reading.
  expect(screen.getByText("s2")).toBeOnTheScreen();
  expect(screen.getByText("…")).toBeOnTheScreen();
  expect(screen.queryByText("agg")).not.toBeOnTheScreen();
  expect(globalThis.fetch).not.toHaveBeenCalledWith(`${BASE}/api/sensors/agg/weather/latest`);
});

test("pull to refresh refetches the sensors and their readings", async () => {
  stubFetch({
    [`${BASE}/api/sensors`]: { sensors: [{ name: "s1", kind: "timeseries" }] },
    [`${BASE}/api/sensors/s1/weather/latest`]: reading,
  });
  await render(<Dashboard />, { wrapper });
  await screen.findByText("21.5 °C · 55 % · 1013 hPa");
  jest.mocked(globalThis.fetch).mockClear();

  // The RefreshControl is a prop of the scroll view, not an ancestor, so fireEvent can't reach it.
  let list = screen.getByText("s1");
  while (!list.props.refreshControl) list = list.parent!;
  await act(() => list.props.refreshControl.props.onRefresh());

  await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(2));
  expect(globalThis.fetch).toHaveBeenCalledWith(`${BASE}/api/sensors`);
  expect(globalThis.fetch).toHaveBeenCalledWith(`${BASE}/api/sensors/s1/weather/latest`);
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
