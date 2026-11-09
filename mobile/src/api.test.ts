import { api, ApiError } from "./api";

const fetchMock = jest.fn();
globalThis.fetch = fetchMock;

test("getWeather calls the public API with an encoded sensor name and start", async () => {
  fetchMock.mockResolvedValue(new Response(JSON.stringify([])));

  await expect(api.getWeather("a b", "2026-01-02T00:00:00+00:00")).resolves.toEqual([]);
  expect(fetchMock).toHaveBeenCalledWith(
    "https://meteo.taram.ca/api/sensors/a%20b/weather?start=2026-01-02T00%3A00%3A00%2B00%3A00",
  );
});

test("getWeatherAggregate calls the aggregate endpoint", async () => {
  fetchMock.mockResolvedValue(new Response(JSON.stringify([])));

  await api.getWeatherAggregate("agg", "t");
  expect(fetchMock).toHaveBeenCalledWith("https://meteo.taram.ca/api/sensors/agg/weather/aggregate?start=t");
});

test("listSensors calls the public API", async () => {
  fetchMock.mockResolvedValue(new Response(JSON.stringify({ sensors: [] })));

  await expect(api.listSensors()).resolves.toEqual({ sensors: [] });
  expect(fetchMock).toHaveBeenCalledWith("https://meteo.taram.ca/api/sensors");
});

test("non-OK responses throw ApiError with the status", async () => {
  fetchMock.mockResolvedValue(new Response("", { status: 404, statusText: "Not Found" }));

  await expect(api.listSensors()).rejects.toEqual(new ApiError(404, "404 Not Found"));
});
