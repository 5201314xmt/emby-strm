/* ============================================================
   首次安装向导
   流程：设置密码 → 连接 MoviePilot → 媒体目录 → 保存并开始扫描
   全部网页完成，不需要懂任何命令
   ============================================================ */

(function () {
  const $ = id => document.getElementById(id);
  let step = 1;

  function showStep(n) {
    step = n;
    [1, 2, 3, 4].forEach(i => {
      $("page" + i).classList.toggle("active", i === n);
      $("stepBar" + i).classList.toggle("active", i <= n);
    });
  }

  function showErr(id, msg) { $(id).textContent = msg; }
  function collectBody() {
    return {
      mp_url: ($("mp_url").value || "").trim(),
      mp_token: ($("mp_token").value || "").trim(),
      scan_paths: JSON.stringify($("scan_paths").value.split("\n")
        .map(s => s.trim()).filter(Boolean)),
      emby_url: ($("emby_url").value || "").trim(),
      emby_api_key: ($("emby_key").value || "").trim(),
    };
  }
  async function post(path, body) {
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    return r.json();
  }

  async function init() {
    // 已登录 → 直接进主页；已初始化 → 去登录页
    try {
      const r = await fetch("/api/auth/status");
      const auth = (await r.json()).data || {};
      if (auth.logged_in) { location.href = "/"; return; }
      if (auth.initialized) { location.href = "/login.html"; return; }
    } catch (e) {
      showErr("err1", "无法连接服务器，请确认服务已启动");
      return;
    }

    // ---------- 步骤1：设置密码 ----------
    $("btn1").onclick = async () => {
      showErr("err1", "");
      const pwd = ($("pwd").value || "").trim();
      if (pwd.length < 6) { showErr("err1", "密码至少 6 位"); return; }
      if (pwd !== ($("pwd2").value || "").trim()) { showErr("err1", "两次输入的密码不一致"); return; }
      const d = await post("/api/auth/setup", { password: pwd });
      if (!d.success) { showErr("err1", d.message || "设置失败"); return; }
      showStep(2);
    };

    // ---------- 步骤2：MoviePilot ----------
    $("btnTest2").onclick = async () => {
      $("testResult2").innerHTML = "";
      const d = await post("/api/settings/test", collectBody());
      if (!d.success) { return; }
      $("testResult2").innerHTML = d.data.map(r => `
        <div class="test-item ${r.ok === true ? "ok" : r.ok === false ? "fail" : "none"}">
          <b>${esc(r.name)}</b>：${esc(r.detail)}
        </div>`).join("");
    };
    $("btn2").onclick = () => {
      const url = ($("mp_url").value || "").trim();
      const token = ($("mp_token").value || "").trim();
      if (!url || !token) { $("testResult2").innerHTML =
        `<div class="test-item fail"><b>提示</b>：地址和 Token 都要填（MoviePilot 设置 → 安全 里找）</div>`; return; }
      showStep(3);
    };

    // ---------- 步骤3：媒体目录 ----------
    $("btnCheckPath").onclick = async () => {
      $("testResult3").innerHTML = "";
      const paths = $("scan_paths").value.split("\n").map(s => s.trim()).filter(Boolean);
      if (!paths.length) { $("testResult3").innerHTML =
        `<div class="test-item fail"><b>提示</b>：请先填写目录（或下面填 Emby 信息）</div>`; return; }
      for (const p of paths) {
        const d = await post("/api/settings/check-path", { path: p });
        $("testResult3").innerHTML +=
          `<div class="test-item ${d.success ? "ok" : "fail"}"><b>${esc(p)}</b>：${esc(d.message || (d.success ? "存在" : "不存在"))}</div>`;
      }
    };
    $("btn3").onclick = () => {
      const paths = $("scan_paths").value.split("\n").map(s => s.trim()).filter(Boolean);
      const emby = ($("emby_url").value || "").trim() && ($("emby_key").value || "").trim();
      if (!paths.length && !emby) {
        $("testResult3").innerHTML =
          `<div class="test-item fail"><b>提示</b>：需要填 strm 目录（推荐）或 Emby 信息，二选一</div>`;
        return;
      }
      showStep(4);
    };

    // ---------- 步骤4：保存并开始扫描 ----------
    $("btnFinish").onclick = async () => {
      $("btnFinish").disabled = true;
      $("btnFinish").textContent = "正在保存...";
      const d = await post("/api/settings", collectBody());
      if (!d.success) {
        $("btnFinish").disabled = false;
        $("btnFinish").textContent = "保存并开始扫描";
        return;
      }
      await post("/api/scan", {});
      location.href = "/";
    };
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  init();
})();
