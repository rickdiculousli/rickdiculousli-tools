"use strict";
// Optional enhancements: the page is complete without this script.
(function () {
  var main = document.getElementById("report");
  if (!main) return;

  function openAncestors(element) {
    for (var node = element; node; node = node.parentElement) {
      if (node.tagName === "DETAILS") node.open = true;
    }
  }

  var lastTarget = null;
  function reveal() {
    var id = decodeURIComponent(location.hash.slice(1));
    var target = id && document.getElementById(id);
    if (!target) return;
    openAncestors(target);
    if (lastTarget) lastTarget.classList.remove("is-target");
    target.classList.add("is-target");
    lastTarget = target;
    target.scrollIntoView({ block: "start" });
  }
  window.addEventListener("hashchange", reveal);
  // Re-clicking the current anchor does not fire hashchange.
  document.addEventListener("click", function (event) {
    var link = event.target.closest && event.target.closest('a[href^="#"]');
    if (link && link.getAttribute("href") === location.hash) setTimeout(reveal);
  });
  reveal();

  var filters = [["all", "All"], ["attention", "Needs attention"], ["asserted", "Asserted only"]];
  var selectors = { attention: "[data-attention]", asserted: '[data-source="asserted"]' };
  var nav = document.createElement("nav");
  nav.className = "filters";
  nav.setAttribute("aria-label", "Filter report items");
  filters.forEach(function (filter) {
    var button = document.createElement("button");
    button.type = "button";
    button.textContent = filter[1];
    button.setAttribute("aria-pressed", filter[0] === "all" ? "true" : "false");
    button.addEventListener("click", function () {
      nav.querySelectorAll("button").forEach(function (other) {
        other.setAttribute("aria-pressed", other === button ? "true" : "false");
      });
      if (filter[0] === "all") {
        delete main.dataset.filter;
        return;
      }
      main.dataset.filter = filter[0];
      main.querySelectorAll(".module " + selectors[filter[0]]).forEach(openAncestors);
    });
    nav.appendChild(button);
  });
  main.insertBefore(nav, main.firstChild);
})();
