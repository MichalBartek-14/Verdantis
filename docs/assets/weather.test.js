// Unit tests for weather.js. The repo has no JS test framework/package.json
// (see CLAUDE.md - "There's no test suite" is about the Python pipeline;
// this is the one JS module worth covering on its own). Uses Node's
// built-in test runner, so no dependency to install.
//
// Run:  node --test docs/assets/weather.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const weather = require("./weather.js");

test("describeWeatherCode maps known WMO codes to a label", () => {
  assert.equal(weather.describeWeatherCode(0).label, "Clear");
  assert.equal(weather.describeWeatherCode(61).label, "Light rain");
  assert.equal(weather.describeWeatherCode(95).label, "Thunderstorm");
});

test("describeWeatherCode falls back to Unknown for an unrecognized code", () => {
  const result = weather.describeWeatherCode(12345);
  assert.equal(result.label, "Unknown");
  assert.ok(result.icon);
});

test("getForecast caches a response for the same coordinate pair", async () => {
  weather._clearCacheForTests();
  let calls = 0;
  const fakeFetch = async () => {
    calls++;
    return {
      ok: true,
      json: async () => ({
        timezone: "Europe/Bratislava",
        current: { time: "2026-01-01T00:00", temperature_2m: 5, relative_humidity_2m: 80, precipitation: 0, weather_code: 2, wind_speed_10m: 10 },
        daily: { time: ["2026-01-01"], weather_code: [2], temperature_2m_max: [6], temperature_2m_min: [1], precipitation_probability_max: [10] },
      }),
    };
  };
  let now = 1000;
  const fakeNow = () => now;

  const first = await weather.getForecast(48.1, 17.1, { fetch: fakeFetch, now: fakeNow });
  const second = await weather.getForecast(48.1, 17.1, { fetch: fakeFetch, now: fakeNow });

  assert.equal(calls, 1, "second call within the cache window should not hit the network");
  assert.equal(second.current.temperature, first.current.temperature);
});

test("getForecast refetches once the 30-minute cache window has passed", async () => {
  weather._clearCacheForTests();
  let calls = 0;
  const fakeFetch = async () => {
    calls++;
    return {
      ok: true,
      json: async () => ({
        timezone: "UTC",
        current: { time: "t", temperature_2m: calls, relative_humidity_2m: 1, precipitation: 0, weather_code: 0, wind_speed_10m: 1 },
        daily: { time: ["d"], weather_code: [0], temperature_2m_max: [1], temperature_2m_min: [1], precipitation_probability_max: [0] },
      }),
    };
  };
  let now = 0;
  const fakeNow = () => now;

  await weather.getForecast(10, 10, { fetch: fakeFetch, now: fakeNow });
  now += 31 * 60 * 1000; // 31 minutes later - past the 30-minute TTL
  await weather.getForecast(10, 10, { fetch: fakeFetch, now: fakeNow });

  assert.equal(calls, 2, "a call after the cache window expires should hit the network again");
});

test("getForecast rejects on a non-ok HTTP response", async () => {
  weather._clearCacheForTests();
  const fakeFetch = async () => ({ ok: false, status: 500, json: async () => ({}) });
  await assert.rejects(() => weather.getForecast(1, 1, { fetch: fakeFetch }));
});

test("getForecast rejects on an empty/unexpected response body", async () => {
  weather._clearCacheForTests();
  const fakeFetch = async () => ({ ok: true, json: async () => ({}) });
  await assert.rejects(() => weather.getForecast(2, 2, { fetch: fakeFetch }));
});
