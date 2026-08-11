/* ============================================================
   登录页逻辑
   两种模式（自动判断）：
     1. 首次使用（还没设置过密码）→ 显示"设置管理员密码"
     2. 已经设置过 → 显示"登录"
   ============================================================ */

(function () {
  const $ = id => document.getElementById(id);
  const errEl = $("errMsg");
  const btn = $("btnSubmit");

  function showErr(msg) { errEl.textContent = msg; }

  async function init() {
    let auth = null;
    try {
      const r = await fetch("/api/auth/status");
      auth = (await r.json()).data || {};
    } catch (e) {
      showErr("无法连接服务器，请确认服务已启动");
      return;
    }

    // 已经登录 → 直接进主页
    if (auth.logged_in) { location.href = "/"; return; }

    const isSetup = !auth.initialized;
    $("modeTitle").textContent = isSetup ? "首次使用：设置管理员密码" : "登录";
    $("confirmRow").style.display = isSetup ? "block" : "none";
    btn.textContent = isSetup ? "设置密码并开始使用" : "登录";
    $("hint").textContent = isSetup
      ? "密码至少 6 位，请牢记，以后登录都要用它"
      : "请输入管理员密码";

    btn.onclick = async () => {
      errEl.textContent = "";
      const pwd = ($("pwd").value || "").trim();
      if (pwd.length < 6) { showErr("密码至少 6 位"); return; }
      if (isSetup && pwd !== ($("pwd2").value || "").trim()) {
        showErr("两次输入的密码不一致");
        return;
      }
      btn.disabled = true;
      try {
        const r = await fetch(isSetup ? "/api/auth/setup" : "/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password: pwd }),
        });
        const d = await r.json();
        if (d.success) { location.href = "/"; return; }
        showErr(d.message || "操作失败");
      } catch (e) {
        showErr("网络出错：" + e.message);
      }
      btn.disabled = false;
    };
  }

  init();
})();
