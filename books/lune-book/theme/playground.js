// 本のコード例に「Playground で開く」を付ける。
//
// リンクには**コードそのもの**が畳み込まれる（Playground の共有リンクと同じ
// `#s=` 形式）。どこかに例をアップロードして同期を保つ必要がないので、本文を
// 直したリンクは次のビルドで自動的に新しくなる — 貼ったきり古くなるリンクが
// 原理的に生まれない。
//
// 対象は `module` で始まる完全なプログラムだけ。断片を送っても Playground は
// 診断を出すだけで、読者には何が起きたのか分からないため。
(function () {
  "use strict";

  var PLAYGROUND = "https://koide55.github.io/lune-lang/playground/";

  // playground/index.html の encodeState と同じ形式。JSON を UTF-8 で base64url。
  // b（評価する束縛）は空にしておく: Playground は本物のパーサで最後の束縛を
  // 選べるので、こちらで推測するより正確になる。
  // l は "ja" — 本書は診断を日本語で掲載しているので、開いた先も揃える。
  function shareUrl(source) {
    var state = { c: source, b: "", t: false, l: "ja" };
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
    link.textContent = "▶ Playground で開く";
    link.title = "このコードを読み込んだ状態でブラウザの Playground を開きます";
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
