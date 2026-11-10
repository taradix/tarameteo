import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import { default as i18n } from "i18next";
import type { ReactNode } from "react";

import { Storage } from "expo-sqlite/kv-store";

import Dashboard from "./app/index";
import SensorScreen from "./app/sensor/[name]";
import SensorsScreen from "./app/sensors";
import "./i18n";
import { toggleShown } from "./shown";

// Lives outside src/app/ because Expo Router treats every file there as a route.

// expo-router/testing-library would replace our reanimated mock with an empty one, so the detail screen
// renders without a router: Link is declarative, and the route params are stubbed.
let mockParams: { name: string; kind: string };
jest.mock("expo-router", () => ({
  ...jest.requireActual("expo-router"),
  Stack: { Screen: () => null },
  useLocalSearchParams: () => mockParams,
}));

let mockGranted: boolean;
jest.mock("expo-location", () => ({
  Accuracy: { Balanced: 3 },
  requestForegroundPermissionsAsync: async () => ({ granted: mockGranted }),
  getCurrentPositionAsync: async () => ({ coords: { latitude: 45.50412, longitude: -73.61749 } }),
}));

const show = (...names: string[]) => names.forEach(toggleShown);

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
  mockParams = { name: "s1", kind: "timeseries" };
  mockGranted = true;
  show(...JSON.parse(Storage.getItemSync("shown") ?? "[]"));
  await i18n.changeLanguage("en");
});

test("shows a card per shown sensor of a known kind", async () => {
  show("s1", "s2", "agg", "future");
  stubFetch({
    [`${BASE}/api/sensors`]: {
      sensors: [
        { name: "s1", kind: "timeseries" },
        { name: "s2", kind: "timeseries" },
        { name: "agg", kind: "aggregate" },
        { name: "future", kind: "forecast" },
        { name: "hidden", kind: "timeseries" },
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
  expect(screen.queryByText("hidden")).not.toBeOnTheScreen();
});

test("asks to choose sensors until some are shown", async () => {
  stubFetch({ [`${BASE}/api/sensors`]: { sensors: [{ name: "s1", kind: "timeseries" }] } });
  await render(<Dashboard />, { wrapper });

  expect(await screen.findByRole("link", { name: "Choose sensors" })).toBeOnTheScreen();
  expect(globalThis.fetch).toHaveBeenCalledTimes(1);
});

test("the picker lists sensors near the rounded position and toggles them", async () => {
  stubFetch({
    [`${BASE}/api/sensors`]: {
      sensors: [
        { name: "near", kind: "timeseries", latitude: 45.5, longitude: -73.6, distance_km: 1.43 },
        { name: "far", kind: "aggregate", latitude: 46.8, longitude: -71.2, distance_km: 42.4 },
      ],
    },
  });
  await render(<SensorsScreen />, { wrapper });

  expect(await screen.findByText("1.4 km")).toBeOnTheScreen();
  expect(screen.getByText("42 km")).toBeOnTheScreen();
  expect(globalThis.fetch).toHaveBeenCalledWith(`${BASE}/api/sensors?latitude=45.5&longitude=-73.62&radius=50`);

  await act(() => fireEvent(screen.getByLabelText("Toggle far"), "valueChange", true));
  expect(screen.getByLabelText("Toggle far").props.value).toBe(true);
  expect(Storage.getItemSync("shown")).toBe('["far"]');

  await act(() => fireEvent.changeText(screen.getByPlaceholderText("Search by name…"), " NE "));
  expect(screen.queryByText("far")).not.toBeOnTheScreen();

  await act(() => fireEvent.press(screen.getByRole("tab", { name: "All" })));
  await waitFor(() =>
    expect(globalThis.fetch).toHaveBeenLastCalledWith(`${BASE}/api/sensors?latitude=45.5&longitude=-73.62`),
  );
});

test("the picker lists every sensor by name without location", async () => {
  mockGranted = false;
  stubFetch({
    [`${BASE}/api/sensors`]: {
      sensors: [
        { name: "b", kind: "timeseries", latitude: 0, longitude: 0 },
        { name: "a", kind: "aggregate", latitude: 0, longitude: 0 },
        { name: "future", kind: "forecast", latitude: 0, longitude: 0 },
      ],
    },
  });
  await render(<SensorsScreen />, { wrapper });

  expect(await screen.findByText("Location unavailable: all sensors, by name.")).toBeOnTheScreen();
  await screen.findByText("a");
  expect(screen.getAllByLabelText(/^Toggle /).map((s) => s.props.accessibilityLabel)).toEqual(["Toggle a", "Toggle b"]);
  expect(screen.queryByRole("tab")).not.toBeOnTheScreen();
  expect(globalThis.fetch).toHaveBeenCalledWith(`${BASE}/api/sensors`);
});

test("the picker says when nothing matches, and shows list errors", async () => {
  stubFetch({ [`${BASE}/api/sensors`]: { sensors: [] } });
  await render(<SensorsScreen />, { wrapper });
  expect(await screen.findByText("No sensors.")).toBeOnTheScreen();

  stubFetch({});
  await act(() => fireEvent.press(screen.getByRole("tab", { name: "10 km" })));
  expect(await screen.findByText("ApiError: 404 Not Found")).toBeOnTheScreen();
});

test("formats numbers for the app language", async () => {
  show("s1");
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
  show("s1");
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

test("the detail screen charts the latest values, and switching range refetches", async () => {
  stubFetch({ [`${BASE}/api/sensors/s1/weather`]: readings });
  await render(<SensorScreen />, { wrapper });

  expect(await screen.findByText(/^21\.5 °C · /)).toBeOnTheScreen();
  expect(screen.getByText("Temperature")).toBeOnTheScreen();
  expect(screen.getByText(/^1,013 hPa · /)).toBeOnTheScreen();
  jest.mocked(globalThis.fetch).mockClear();

  await act(() => fireEvent.press(screen.getByRole("tab", { name: "7 d" })));
  await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(1));
  const start = new URL(jest.mocked(globalThis.fetch).mock.calls[0][0] as string).searchParams.get("start")!;
  expect(Date.now() - Date.parse(start)).toBeGreaterThan(6 * 24 * 3600_000);
});

test("the aggregate detail screen charts daily temperature and precipitation over longer ranges", async () => {
  mockParams = { name: "agg", kind: "aggregate" };
  stubFetch({ [`${BASE}/api/sensors/agg/weather/aggregate`]: [aggregate] });
  await render(<SensorScreen />, { wrapper });

  expect(await screen.findByText(/^min -1\.0 · avg 3\.5 · max 8\.1 °C · /)).toBeOnTheScreen();
  expect(screen.getByText(/^rain 4\.2 mm · snow – mm · /)).toBeOnTheScreen();
  expect(screen.getByText("Precipitation")).toBeOnTheScreen();
  expect(screen.getAllByRole("tab").map((tab) => tab.props.accessibilityState.selected)).toEqual([true, false, false]);
  expect(screen.getByRole("tab", { name: "90 d" })).toBeOnTheScreen();
  expect(screen.queryByRole("tab", { name: "24 h" })).not.toBeOnTheScreen();
});

test("the detail screen says when a range is empty", async () => {
  stubFetch({ [`${BASE}/api/sensors/s1/weather`]: [] });
  await render(<SensorScreen />, { wrapper });

  expect(await screen.findByText("No data in range.")).toBeOnTheScreen();
  jest.mocked(globalThis.fetch).mockClear();

  await act(() => screen.getByTestId("sensor-scroll").props.refreshControl.props.onRefresh());
  await waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(1));
});

test("the detail screen shows fetch errors", async () => {
  stubFetch({});
  await render(<SensorScreen />, { wrapper });

  expect(await screen.findByText("ApiError: 404 Not Found")).toBeOnTheScreen();
});

test("shows an empty state when no shown sensor exists", async () => {
  show("gone");
  stubFetch({ [`${BASE}/api/sensors`]: { sensors: [] } });
  await render(<Dashboard />, { wrapper });

  expect(await screen.findByText("No sensors.")).toBeOnTheScreen();
});

test("shows the error when the sensor list fails", async () => {
  stubFetch({ [`${BASE}/api/sensors`]: new Response("", { status: 500, statusText: "Server Error" }) });
  await render(<Dashboard />, { wrapper });

  expect(await screen.findByText("ApiError: 500 Server Error")).toBeOnTheScreen();
});
