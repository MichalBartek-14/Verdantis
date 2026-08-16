// Verdantis - per-client personalization.
// Every page in the site is byte-identical across clients (see
// publish_site.py's publish_client_site()) - the only thing that differs
// per client is data/, including this file's one input: client_meta.json.
// Elements opt into personalization via data-client-* attributes rather
// than hardcoded copy, so onboarding client #11 never means editing HTML.
(function () {
  "use strict";

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

  fetch("data/client_meta.json", { cache: "no-store" })
    .then(function (r) { return r.json(); })
    .then(function (meta) {
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

      if (meta.display_name) document.title = meta.display_name + " · " + document.title;
    })
    .catch(function (err) {
      // Falls back to whatever static copy is already in the HTML (e.g.
      // "Valice, Slovakia" as literal text) - degraded but not broken.
      console.warn("client_meta.json not loaded - showing generic/static copy.", err);
    });
})();
