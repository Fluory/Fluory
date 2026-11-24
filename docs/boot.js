// Runs before first paint (render-blocking on purpose, tiny): applies the saved
// colour scheme and enables the hidden start states for the entrance only when
// motion is allowed. If main.js does not take over within 2.5 s, the content is
// shown as is.
(function () {
  var root = document.documentElement;
  try {
    var saved = localStorage.getItem("theme");
    if (saved === "light" || saved === "dark") root.setAttribute("data-theme", saved);
  } catch (e) {}
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reduce) {
    root.classList.add("motion");
    window.setTimeout(function () {
      if (!root.classList.contains("motion-ready")) root.classList.remove("motion");
    }, 2500);
  }
})();
