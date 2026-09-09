// Adds "Open in the Playground" to the book's code examples.
//
// The link carries **the code itself** (the same `#s=` format the Playground's
// share button writes), so nothing has to be uploaded anywhere and kept in
// step: edit the text and the next build produces a new link. A link that has
// gone stale cannot exist here by construction.
//
// Only complete programs — the ones starting with `module` — get a link. A
// fragment would just produce a diagnostic the reader cannot place.
//
// This is the English edition's copy of books/lune-book/theme/playground.js;
// the one thing that differs is the language the Playground opens in.
(function () {
  "use strict";

  var PLAYGROUND = "https://koide55.github.io/lune-lang/playground/";

  // Same shape as encodeState() in playground/index.html: JSON, UTF-8, base64url.
  // `b` (the binding to evaluate) is left empty on purpose — the Playground
  // picks it with the real parser, which beats guessing from here.
  // `l` is "en": this edition prints English diagnostics, so the Playground
  // should answer in English too.
  function shareUrl(source) {
    var state = { c: source, b: "", t: false, l: "en" };
    var utf8 = unescape(encodeURIComponent(JSON.stringify(state)));
    var b64 = btoa(utf8).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    return PLAYGROUND + "#s=" + b64;
  }

  function decorate(code) {
    var source = code.textContent;
    if (!/^\s*module\s/.test(source)) return;

    var pre = code.closest("pre");
    if (!pre || pre.nextElementSibling && pre.nextElementSibling.classList.contains("playground-open")) return;

    var link = document.createElement("a");
    link.className = "playground-open";
    link.href = shareUrl(source);
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "▶ Open in the Playground";
    link.title = "Opens the browser Playground with this code already loaded";
    pre.parentNode.insertBefore(link, pre.nextSibling);
  }

  function run() {
    var blocks = document.querySelectorAll("pre code.language-lune");
    for (var i = 0; i < blocks.length; i++) decorate(blocks[i]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
