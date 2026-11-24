/**
 * 服务状态与演示数据按钮（导航由服务端 Jinja 渲染）。
 */
(function () {
  function loadHealth() {
    var box = document.getElementById("health-status");
    if (!box || box.dataset.booted === "1") return;
    fetch("/api/v1/health", { credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        box.textContent =
          data.status === "ok"
            ? "运行正常 (status: ok)"
            : JSON.stringify(data);
        box.classList.add("health-ok");
        box.dataset.booted = "1";
      })
      .catch(function () {
        box.textContent = "无法连接后端，请确认已启动 uvicorn :8000";
      });
  }

  function bindSeedButtons() {
    document.querySelectorAll("[data-seed-demo]").forEach(function (btn) {
      if (btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";
      btn.addEventListener("click", function () {
        btn.disabled = true;
        var old = btn.textContent;
        btn.textContent = "导入中…";
        fetch("/api/v1/dev/seed", { method: "POST", credentials: "same-origin" })
          .then(function (r) {
            if (!r.ok) throw new Error("HTTP " + r.status);
            return r.json();
          })
          .then(function () {
            alert(
              "示例资料已导入，请打开知识库等待文档变为「已索引」后体验问答与视频。"
            );
          })
          .catch(function (e) {
            alert("导入失败：" + e.message);
          })
          .finally(function () {
            btn.disabled = false;
            btn.textContent = old;
          });
      });
    });
  }

  function boot() {
    loadHealth();
    bindSeedButtons();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
