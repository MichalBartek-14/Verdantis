// Verdantis - Open-Meteo weather connector. No API key, no backend: this is
// the ONE place that calls Open-Meteo's forecast endpoint, so every caller
// (today: docs/index.html's per-client weather card grid) shares the same
// request shape and the same short in-memory cache instead of re-deriving
// either. Param names below were checked against https://open-meteo.com/en/docs
// at the time this was written - re-check there if Open-Meteo ever 400s on
// a previously-working query.
//
// UMD-ish export: plain <script> tag in the browser sets window.VerdantisWeather;
// require()'d from weather.test.js under Node it exports the same object.
(function (factory) {
  if (typeof module !== "undefined" && module.exports) {
    module.exports = factory();
  } else {
    window.VerdantisWeather = factory();
  }
})(function () {
  "use strict";

  var FORECAST_URL = "https://api.open-meteo.com/v1/forecast";
  var CACHE_TTL_MS = 30 * 60 * 1000; // 30 minutes, per coordinate pair

  var cache = Object.create(null);

  // WMO weather code -> {label, icon}. Icon is a plain emoji so a card needs
  // no extra image/sprite asset. Table: https://open-meteo.com/en/docs (WMO
  // Weather interpretation codes).
  var WMO_CODES = {
    0: { label: "Clear", icon: "☀️" },
    1: { label: "Mainly clear", icon: "🌤️" },
    2: { label: "Partly cloudy", icon: "⛅" },
    3: { label: "Overcast", icon: "☁️" },
    45: { label: "Fog", icon: "🌫️" },
    48: { label: "Rime fog", icon: "🌫️" },
    51: { label: "Light drizzle", icon: "🌦️" },
    53: { label: "Drizzle", icon: "🌦️" },
    55: { label: "Dense drizzle", icon: "🌦️" },
    56: { label: "Light freezing drizzle", icon: "🌧️" },
    57: { label: "Freezing drizzle", icon: "🌧️" },
    61: { label: "Light rain", icon: "🌧️" },
    63: { label: "Rain", icon: "🌧️" },
    65: { label: "Heavy rain", icon: "🌧️" },
    66: { label: "Light freezing rain", icon: "🌧️" },
    67: { label: "Freezing rain", icon: "🌧️" },
    71: { label: "Light snow", icon: "🌨️" },
    73: { label: "Snow", icon: "🌨️" },
    75: { label: "Heavy snow", icon: "❄️" },
    77: { label: "Snow grains", icon: "❄️" },
    80: { label: "Light showers", icon: "🌦️" },
    81: { label: "Showers", icon: "🌦️" },
    82: { label: "Violent showers", icon: "⛈️" },
    85: { label: "Snow showers", icon: "🌨️" },
    86: { label: "Heavy snow showers", icon: "🌨️" },
    95: { label: "Thunderstorm", icon: "⛈️" },
    96: { label: "Thunderstorm, hail", icon: "⛈️" },
    99: { label: "Severe thunderstorm", icon: "⛈️" },
  };

  function describeWeatherCode(code) {
    return WMO_CODES[code] || { label: "Unknown", icon: "❓" };
  }

  // Rounded to ~100m so float noise in a config-derived lat/lon still hits
  // the same cache entry; coordinates this close together get the same
  // forecast from Open-Meteo anyway.
  function cacheKey(lat, lon) {
    return Number(lat).toFixed(3) + "," + Number(lon).toFixed(3);
  }

  function normalize(raw) {
    var c = raw.current, d = raw.daily;
    var days = (d.time || []).map(function (date, i) {
      return {
        date: date,
        weather: describeWeatherCode(d.weather_code[i]),
        tempMax: d.temperature_2m_max[i],
        tempMin: d.temperature_2m_min[i],
        precipitationChance: d.precipitation_probability_max ? d.precipitation_probability_max[i] : null,
      };
    });
    return {
      timezone: raw.timezone || "UTC",
      current: {
        time: c.time,
        temperature: c.temperature_2m,
        humidity: c.relative_humidity_2m,
        precipitation: c.precipitation,
        windSpeed: c.wind_speed_10m,
        weather: describeWeatherCode(c.weather_code),
      },
      days: days,
    };
  }

  // opts.fetch/opts.now let weather.test.js substitute a fake network call
  // and a fake clock without touching the real network or sleeping 30
  // minutes - production callers never pass opts.
  function getForecast(lat, lon, opts) {
    var fetchImpl = (opts && opts.fetch) || fetch;
    var now = (opts && opts.now) || Date.now;
    var key = cacheKey(lat, lon);
    var hit = cache[key];
    if (hit && (now() - hit.time) < CACHE_TTL_MS) {
      return Promise.resolve(hit.data);
    }

    var url = FORECAST_URL +
      "?latitude=" + encodeURIComponent(lat) +
      "&longitude=" + encodeURIComponent(lon) +
      "&current=temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m" +
      "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max" +
      "&forecast_days=3&timezone=auto";

    return fetchImpl(url).then(function (res) {
      if (!res.ok) throw new Error("Open-Meteo responded " + res.status);
      return res.json();
    }).then(function (raw) {
      if (!raw || !raw.current || !raw.daily) throw new Error("Open-Meteo returned an empty/unexpected response");
      var data = normalize(raw);
      cache[key] = { time: now(), data: data };
      return data;
    });
  }

  return {
    getForecast: getForecast,
    describeWeatherCode: describeWeatherCode,
    _cacheKeyForTests: cacheKey,
    _clearCacheForTests: function () { cache = Object.create(null); },
  };
});
