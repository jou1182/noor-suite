/* أدوات أعلى الصفحة (2026-09-25): جرس الإشعارات + زر الوضع الفاتح/الداكن.
   الفاتح هو الافتراضي دائماً؛ الداكن فقط لمن يختاره (يُحفظ في هذا المتصفح).
   الجرس يظهر لمن سجّل الدخول وتعمل لديه لوحة المهام (/api/notifications)، ويتحدّث كل دقيقة. */
(function () {
  var KEY = "noor-theme", root = document.documentElement;
  var ICON = {rate: "⭐", late: "⏰", today: "⏳"};
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
    return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); }
  function ago(at) {
    var d = new Date(String(at).replace(" ", "T")), m = Math.round((Date.now() - d) / 60000);
    if (isNaN(m)) return "";
    if (m < 1) return "الآن"; if (m < 60) return "منذ " + m + " د";
    var h = Math.round(m / 60); if (h < 24) return "منذ " + h + " س";
    return "منذ " + Math.round(h / 24) + " يوم";
  }
  function themeLabel(t) { return t === "dark" ? "التبديل إلى الوضع الفاتح" : "التبديل إلى الوضع الداكن"; }

  document.addEventListener("DOMContentLoaded", function () {
    var shell = document.createElement("div");
    shell.className = "noor-shell";
    shell.innerHTML =
      '<div class="ns-bell" hidden><button type="button" class="ns-btn" id="nsBell" aria-haspopup="true" aria-expanded="false" aria-label="الإشعارات">' +
      '<span aria-hidden="true">🔔</span><span class="ns-badge" id="nsBadge" hidden></span></button>' +
      '<div class="ns-panel" id="nsPanel" role="dialog" aria-label="الإشعارات" hidden></div></div>' +
      '<button type="button" class="ns-btn theme-toggle" id="nsTheme"></button>';
    document.body.appendChild(shell);

    var themeBtn = document.getElementById("nsTheme");
    function paintTheme() {
      var t = root.getAttribute("data-theme");
      themeBtn.textContent = t === "dark" ? "☀" : "☾";
      themeBtn.title = themeLabel(t); themeBtn.setAttribute("aria-label", themeLabel(t));
    }
    paintTheme();
    themeBtn.addEventListener("click", function () {
      var t = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      try { localStorage.setItem(KEY, t); } catch (e) {}
      root.setAttribute("data-theme", t); paintTheme();
      if (window.Chart) location.reload();        // الرسوم تُرسم بألوان الوضع عند التحميل
    });

    var wrap = shell.querySelector(".ns-bell"), bell = document.getElementById("nsBell"),
        badge = document.getElementById("nsBadge"), panel = document.getElementById("nsPanel"), data = null;
    function render() {
      var req = data.required || [], items = data.items || [];
      panel.innerHTML =
        '<div class="ns-h"><b>الإشعارات</b><button type="button" class="ns-read" id="nsRead">تعليم الكل مقروء</button></div>' +
        (req.length ? '<div class="ns-sec ns-now">● مطلوب منك الآن <span>' + req.length + '</span></div>' +
          req.map(function (r) {
            return '<a class="ns-item ns-req-' + r.kind + '" href="/tasks#task-' + r.task_id + '"><span class="ns-ic">' + (ICON[r.kind] || "•") +
              '</span><span class="ns-tx"><b>' + esc(r.title) + '</b><small>' + esc(r.task) + (r.tender ? " · " + esc(r.tender) : "") + '</small></span></a>';
          }).join("") : "") +
        '<div class="ns-sec">آخر التغييرات</div>' +
        (items.length ? items.map(function (n) {
          return '<a class="ns-item' + (n.unread ? " unread" : "") + '" href="/tasks#task-' + n.task_id + '"><span class="ns-ic">' + esc(n.icon) +
            '</span><span class="ns-tx"><b>' + esc(n.task) + '</b><small>' + esc(n.text) + '</small><small class="ns-meta">' + esc(n.actor) +
            " · " + ago(n.at) + (n.tender ? " · " + esc(n.tender) : "") + '</small></span>' + (n.unread ? '<span class="ns-new">جديد</span>' : "") + '</a>';
        }).join("") : '<div class="ns-empty">لا تغييرات بعد</div>');
      var mark = document.getElementById("nsRead");
      mark.disabled = !data.unread;
      mark.addEventListener("click", function () {
        fetch("/api/notifications/read", {method: "POST"}).then(load);
      });
    }
    function load() {
      fetch("/api/notifications", {headers: {"Accept": "application/json"}}).then(function (r) {
        if (!r.ok) throw 0; return r.json();
      }).then(function (j) {
        if (!j.ok) throw 0;
        data = j; wrap.hidden = false;
        var n = j.unread + 0;
        badge.hidden = !n; badge.textContent = n > 99 ? "99+" : n;
        bell.setAttribute("aria-label", "الإشعارات" + (n ? " — " + n + " غير مقروءة" : ""));
        if (!panel.hidden) render();
      }).catch(function () { wrap.hidden = true; });
    }
    function toggle(open) {
      panel.hidden = !open; bell.setAttribute("aria-expanded", open ? "true" : "false");
      if (open && data) render();
    }
    bell.addEventListener("click", function (e) { e.stopPropagation(); toggle(panel.hidden); });
    document.addEventListener("click", function (e) { if (!e.target.closest(".ns-bell")) toggle(false); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") toggle(false); });
    document.addEventListener("visibilitychange", function () { if (!document.hidden) load(); });
    load(); setInterval(load, 60000);
  });
})();
