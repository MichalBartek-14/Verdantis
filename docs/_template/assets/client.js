// Verdantis - per-client personalization + i18n.
// Every page in the site is byte-identical across clients (see
// publish_site.py's publish_client_site()) - the only things that differ
// per client are data/ (this file's one input: client_meta.json) and
// which language dictionary that data points at. Elements opt into
// personalization/translation via data-client-*/data-i18n* attributes
// rather than hardcoded copy, so onboarding client #11 - in whatever
// language they read - never means editing HTML.
//
// Adding new content later: wrap it in a data-i18n="some.key" (or
// data-i18n-html="some.key" if it needs embedded markup) and add
// "some.key" to BOTH assets/i18n/en/<page>.json and .../sk/<page>.json.
// Missing keys fail loudly (console.warn + the raw key shown in the UI)
// rather than silently falling back to English, so a forgotten Slovak
// string is obvious on the page, not just in a log.
//
// This script is loaded WITHOUT `defer`, in <head>, specifically so
// window.VerdantisReady exists (as a pending Promise) before any later
// inline <script> in the body runs - those scripts (monitoring.html,
// explorer.html) do `await window.VerdantisReady` to get `t()` for the
// dynamic text they render themselves.
(function () {
  "use strict";

  var DEFAULT_LANG = "en";

  function darken(hex, amount) {
    // Cheap, dependency-free darken for the accent's "-dark" hover/heading
    // shade - not real color-space math, just scales each channel toward
    // black. Good enough for a UI accent; swap for something fancier if a
    // client's brand color needs perceptual accuracy.
    hex = hex.replace("#", "");
    var r = parseInt(hex.slice(0, 2), 16), g = parseInt(hex.slice(2, 4), 16), b = parseInt(hex.slice(4, 6), 16);
    var f = 1 - amount;
    var toHex = function (v) { return Math.round(v * f).toString(16).padStart(2, "0"); };
    return "#" + toHex(r) + toHex(g) + toHex(b);
  }

  function getPath(obj, path) {
    return path.split(".").reduce(function (o, k) { return (o && o[k] !== undefined) ? o[k] : undefined; }, obj);
  }

  function interpolate(str, vars) {
    if (!vars) return str;
    return str.replace(/\{(\w+)\}/g, function (m, k) { return (vars[k] !== undefined) ? vars[k] : m; });
  }

  function makeT(dict) {
    return function t(key, vars) {
      var val = getPath(dict, key);
      if (val === undefined) {
        console.warn("i18n: missing key \"" + key + "\" for this page/language - add it to both en/ and sk/.");
        return key;
      }
      return typeof val === "string" ? interpolate(val, vars) : val;
    };
  }

  function applyStaticTranslations(t) {
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      el.textContent = t(el.getAttribute("data-i18n"));
    });
    document.querySelectorAll("[data-i18n-html]").forEach(function (el) {
      el.innerHTML = t(el.getAttribute("data-i18n-html"));
    });
  }

  function applyClientPersonalization(meta) {
    var root = document.documentElement.style;
    var accent = meta.accent_color || "#2c7a3c";
    root.setProperty("--green", accent);
    root.setProperty("--green-dark", darken(accent, 0.35));

    document.querySelectorAll("[data-client-name]").forEach(function (el) { el.textContent = meta.client_name; });
    document.querySelectorAll("[data-client-location]").forEach(function (el) { el.textContent = meta.location; });
    document.querySelectorAll("[data-client-display-name]").forEach(function (el) { el.textContent = meta.display_name; });
    document.querySelectorAll("[data-client-area]").forEach(function (el) {
      el.textContent = meta.plot_area_ha ? meta.plot_area_ha + " ha" : "";
    });

    // "Satellite Briefing" nav link (see style.css's .nav-briefing) always
    // points one level up at the shared docs/index.html briefing, but
    // which LANGUAGE of it depends on this client - docs/sk/ is the only
    // non-English briefing today, so this is a plain either/or rather than
    // a lang -> path lookup; extend it if a third briefing language shows up.
    var briefingHref = meta.language === "sk" ? "../../sk/index.html" : "../../index.html";
    document.querySelectorAll("[data-briefing-link]").forEach(function (el) { el.href = briefingHref; });
  }

  function loadDict(lang, page) {
    // common.json (nav/footer/badge, shared by every page) + <page>.json
    // (that page's own strings), merged flat - their top-level key names
    // don't collide (common: nav/badge/footer; pages: hero/js/...), so a
    // shallow merge is enough.
    return Promise.all([
      fetch("assets/i18n/" + lang + "/common.json", { cache: "no-store" }).then(function (r) { return r.json(); }),
      fetch("assets/i18n/" + lang + "/" + page + ".json", { cache: "no-store" }).then(function (r) { return r.json(); }),
    ]).then(function (parts) {
      return Object.assign({}, parts[0], parts[1]);
    });
  }

  var page = document.body.getAttribute("data-page") || "index";

  window.VerdantisReady = fetch("data/client_meta.json", { cache: "no-store" })
    .then(function (r) { return r.json(); })
    .catch(function (err) {
      console.warn("client_meta.json not loaded - using defaults (English, generic branding).", err);
      return {};
    })
    .then(function (meta) {
      var lang = meta.language || DEFAULT_LANG;
      return loadDict(lang, page)
        .catch(function (err) {
          console.warn("i18n dictionary for \"" + lang + "\" failed to load - falling back to English.", err);
          return lang === DEFAULT_LANG ? {} : loadDict(DEFAULT_LANG, page);
        })
        .then(function (dict) {
          var t = makeT(dict);
          document.documentElement.lang = lang;
          // Static translations first, THEN client personalization - some
          // elements (e.g. the header badge) carry both a data-i18n
          // fallback ("Pilot") and a data-client-display-name override;
          // the specific client value must win, so it's applied last.
          applyStaticTranslations(t);
          applyClientPersonalization(meta);
          if (meta.display_name) document.title = meta.display_name + " · " + document.title;
          return { t: t, lang: lang, meta: meta };
        });
    });
})();
