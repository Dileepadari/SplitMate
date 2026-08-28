/* SplitMate progressive enhancement.
   Everything here is optional: every page works with JavaScript disabled. */
(function () {
  "use strict";

  var root = document.documentElement;

  /* --- Theme toggle ------------------------------------------------------ */

  function currentTheme() {
    return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function paintThemeIcons() {
    var dark = currentTheme() === "dark";
    document.querySelectorAll("[data-theme-icon]").forEach(function (el) {
      el.hidden = el.getAttribute("data-theme-icon") !== (dark ? "dark" : "light");
    });
  }

  var themeToggle = document.getElementById("theme-toggle");
  if (themeToggle) {
    paintThemeIcons();
    themeToggle.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      paintThemeIcons();
      try {
        localStorage.setItem("splitmate-theme", next);
      } catch (e) {
        /* storage unavailable: the preference still round-trips via the server */
      }
      var url = themeToggle.getAttribute("data-theme-url");
      if (url) {
        fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": themeToggle.getAttribute("data-csrf") || ""
          },
          body: JSON.stringify({ theme: next })
        }).catch(function () {
          /* the local preference is enough; nothing to recover */
        });
      }
    });
  }

  /* --- Mobile navigation ------------------------------------------------- */

  var navToggle = document.getElementById("nav-toggle");
  var scrim = document.getElementById("scrim");

  function closeNav() {
    document.body.classList.remove("nav-open");
    if (navToggle) navToggle.setAttribute("aria-expanded", "false");
  }

  if (navToggle) {
    navToggle.addEventListener("click", function () {
      var open = document.body.classList.toggle("nav-open");
      navToggle.setAttribute("aria-expanded", String(open));
    });
  }
  if (scrim) scrim.addEventListener("click", closeNav);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeNav();
  });

  /* --- Flash messages ---------------------------------------------------- */

  document.querySelectorAll("[data-dismiss]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var flash = btn.closest(".flash");
      if (flash) flash.remove();
    });
  });

  window.setTimeout(function () {
    document.querySelectorAll(".flash-success, .flash-info").forEach(function (f) {
      f.remove();
    });
  }, 6000);

  /* --- Confirmation before destructive posts ----------------------------- */

  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm(form.getAttribute("data-confirm"))) e.preventDefault();
    });
  });

  /* --- Expense split editor ---------------------------------------------- */

  var splitEditor = document.getElementById("split-editor");
  if (splitEditor) {
    var amountInput = document.getElementById("amount-input");
    var summary = document.getElementById("split-summary");
    var allocatedOut = document.getElementById("split-allocated");
    var remainderOut = document.getElementById("split-remainder");
    var currency = splitEditor.getAttribute("data-currency-symbol") || "";

    function mode() {
      var checked = splitEditor.querySelector("input[name='split_type']:checked");
      return checked ? checked.value : "equal";
    }

    function rows() {
      return Array.prototype.slice.call(splitEditor.querySelectorAll(".participant"));
    }

    function money(n) {
      return currency + n.toFixed(2);
    }

    function recalc() {
      var current = mode();
      var total = parseFloat(amountInput && amountInput.value) || 0;
      var active = [];

      rows().forEach(function (row) {
        var check = row.querySelector("input[name='participant']");
        var on = check.checked;
        row.classList.toggle("off", !on);

        row.querySelectorAll("[data-split-mode]").forEach(function (el) {
          var visible = el.getAttribute("data-split-mode") === current;
          el.hidden = !visible;
          var input = el.querySelector("input");
          if (input) input.disabled = !visible || !on;
        });

        if (on) {
          active.push(row);
        } else {
          // Clear the computed amounts on a row nobody is splitting with, so a
          // stale figure from before the untick cannot be misread.
          row.querySelectorAll("[data-equal-share], [data-share-amount]").forEach(
            function (out) {
              out.textContent = "";
            }
          );
        }
      });

      var allocated = 0;
      if (current === "equal") {
        // Mirror the server: even split, leftover cents to the first rows.
        var cents = Math.round(total * 100);
        var n = active.length;
        active.forEach(function (row, i) {
          var out = row.querySelector("[data-equal-share]");
          if (!out) return;
          if (!n) {
            out.textContent = "";
            return;
          }
          var base = Math.floor(cents / n);
          var extra = i < cents - base * n ? 1 : 0;
          out.textContent = money((base + extra) / 100);
        });
        allocated = total;
      } else if (current === "exact") {
        active.forEach(function (row) {
          var input = row.querySelector("input[name^='exact-']");
          allocated += parseFloat(input && input.value) || 0;
        });
      } else {
        var weights = active.map(function (row) {
          var input = row.querySelector("input[name^='weight-']");
          return Math.max(0, parseInt((input && input.value) || "0", 10) || 0);
        });
        var sum = weights.reduce(function (a, b) {
          return a + b;
        }, 0);
        active.forEach(function (row, i) {
          var out = row.querySelector("[data-share-amount]");
          if (out) out.textContent = sum ? money((total * weights[i]) / sum) : money(0);
        });
        allocated = total;
      }

      if (summary) {
        var remainder = total - allocated;
        var off = current === "exact" && Math.abs(remainder) > 0.004;
        summary.classList.toggle("mismatch", off);
        if (allocatedOut) allocatedOut.textContent = money(allocated);
        if (remainderOut) {
          remainderOut.textContent = off
            ? money(remainder) + " left to allocate"
            : active.length + (active.length === 1 ? " person" : " people");
        }
      }
    }

    splitEditor.addEventListener("change", recalc);
    splitEditor.addEventListener("input", recalc);
    if (amountInput) amountInput.addEventListener("input", recalc);

    var selectAll = document.getElementById("select-all");
    if (selectAll) {
      selectAll.addEventListener("click", function () {
        var anyOff = rows().some(function (row) {
          return !row.querySelector("input[name='participant']").checked;
        });
        rows().forEach(function (row) {
          row.querySelector("input[name='participant']").checked = anyOff;
        });
        recalc();
      });
    }

    recalc();
  }
})();
