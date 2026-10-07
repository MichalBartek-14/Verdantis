// Swaps the CSS gradient-box ".mark" + "Verdantis" text brand lockup (the
// built-in fallback, defined in style.css/every page's markup) for a real
// logo image once one exists at <prefix>logo-full.png. Shared by both
// asset trees in this repo - docs/_template/assets/ (copied verbatim into
// every docs/c/<slug>/assets/ by publish_site.py) AND the standalone
// briefing pages under docs/ (docs/index.html etc. already reference
// _template/assets/style.css the same cross-tree way - see README/
// CLAUDE.md). The actual image file is NOT shared the same way: each
// tree keeps its own docs/<...>/assets/img/brand/logo-full.png copy, so
// that a published docs/c/<slug>/ stays fully self-contained if it's ever
// deployed independently of the rest of the site (see CLAUDE.md's "Data
// isolation" note) - only this script is safe to reach into cross-tree.
//
// Probe-then-swap rather than just pointing an <img src> at the file
// directly: a missing image would show a broken-image icon even with the
// fallback hidden, so this loads into a throwaway Image() first and only
// touches the real DOM once the file is confirmed to exist. Safe to call
// on every page before logo-full.png has been added at all - the CSS
// mark + text just stays as they are.
//
// Usage - right after the page's own <script src=".../brand-logo.js">:
//   <script>initBrandLogo('assets/img/brand/');</script>
// `prefix` must resolve to wherever THIS page's own assets/img/brand/
// lives (e.g. 'assets/img/brand/' from docs/_template/*.html or
// docs/index.html, '../assets/img/brand/' from docs/sk/*.html).
function initBrandLogo(prefix) {
  document.querySelectorAll('.brand').forEach(function (brand) {
    var mark = brand.querySelector('.mark');
    if (!mark) return; // already swapped, or not the expected markup
    var probe = new Image();
    probe.onload = function () {
      var img = document.createElement('img');
      img.className = 'brand-logo';
      img.src = prefix + 'logo-full.png';
      img.alt = 'Verdantis';
      brand.replaceChildren(img);
    };
    probe.onerror = function () {}; // no logo yet - CSS mark + text stays
    probe.src = prefix + 'logo-full.png';
  });
}
