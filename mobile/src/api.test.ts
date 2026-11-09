import { api, ApiError } from "./api";

const fetchMock = jest.fn();
globalThis.fetch = fetchMock;

test("getLatest calls the public API with an encoded sensor name", async () => {
  fetchMock.mockResolvedValue(new Response(JSON.stringify({ sensor: "a b" })));

  await expect(api.getLatest("a b")).resolves.toEqual({ sensor: "a b" });
  expect(fetchMock).toHaveBeenCalledWith("https://meteo.taram.ca/api/sensors/a%20b/weather/latest");
});

test("non-OK responses throw ApiError with the status", async () => {
  fetchMock.mockResolvedValue(new Response("", { status: 404, statusText: "Not Found" }));

  await expect(api.getLatest("x")).rejects.toEqual(new ApiError(404, "404 Not Found"));
});
