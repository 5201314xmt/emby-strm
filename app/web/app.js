/* ============================================================
   缺集管家 - 前端逻辑
   说明：原生 JavaScript，不需要任何框架，打开页面就能用
   ============================================================ */

/* ---------- 全局状态 ---------- */
const state = {
  tab: "home",          // 当前页面
  filter: "all",        // 缺集列表的筛选
  shows: [],            // 缺集列表数据
  settings: [],         // 设置数据
  scanTimer: null,      // 扫描进度轮询定时器
  showsOffset: 0,       // 缺集列表分页偏移
  showsTotal: 0,        // 缺集总数
  uniOffset: 0,         // 未识别列表分页偏移
  uniTotal: 0,          // 未识别总数
};

/* ============================================================
   小工具函数
   ============================================================ */

// 转义 HTML，防止剧名里的特殊字符破坏页面
function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// 请求后端接口，统一处理成功/失败
async function api(path, options) {
  const opts = options || {};
  opts.headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
  try {
    const resp = await fetch(path, opts);
    // 未登录：跳转到登录页
    if (resp.status === 401) {
      location.href = "/login.html";
      return null;
    }
    const data = await resp.json();
    if (!data.success) {
      toast(data.message || "操作失败", "error");
      return null;
    }
    return data.data;
  } catch (e) {
    toast("网络出错：" + e.message, "error");
    return null;
  }
}

// 页面顶部的提示消息（2.5 秒后自动消失）
function toast(msg, type) {
  const box = document.getElementById("toast");
  const item = document.createElement("div");
  item.className = "toast-item " + (type || "");
  item.textContent = msg;
  box.appendChild(item);
  setTimeout(() => item.remove(), 2500);
}

// 把连续集号合并成好读的形式，如 [1,2,3,5,8] → "1-3, 5, 8"
function formatEps(eps) {
  if (!eps || !eps.length) return "";
  const nums = [...eps].sort((a, b) => a - b);
  const parts = [];
  let start = nums[0], prev = nums[0];
  for (let i = 1; i <= nums.length; i++) {
    const n = nums[i];
    if (n === prev + 1) { prev = n; continue; }
    parts.push(start === prev ? start : start + "-" + prev);
    start = prev = n;
  }
  return parts.join(", ");
}

// 把秒数转成好读的剩余时间：90 → "1分钟半" / 3600 → "1小时"
function formatETA(sec) {
  if (!sec || sec <= 0) return "";
  if (sec < 60) return "预计剩余 " + Math.round(sec) + " 秒";
  const min = Math.round(sec / 60);
  if (min < 60) return "预计剩余 " + min + " 分钟";
  const h = Math.floor(min / 60), m = min % 60;
  return "预计剩余 " + h + " 小时" + (m ? " " + m + " 分" : "");
}

// 订阅状态的中文翻译（MoviePilot 的状态码）
function subStateText(code) {
  return { R: "等待搜索", S: "搜索中", P: "已完成" }[code] || "未知";
}
function subStateTag(code) {
  const map = { R: "info", S: "search", P: "done" };
  return `<span class="tag ${map[code] || "info"}">${esc(subStateText(code))}</span>`;
}

/* ============================================================
   页面切换
   ============================================================ */

document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

function switchTab(tab) {
  state.tab = tab;
  document.querySelectorAll(".tab").forEach(b =>
    b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".page").forEach(p =>
    p.classList.toggle("active", p.id === "page-" + tab));
  // 进入对应页面时刷新数据
  if (tab === "home") loadHome();
  if (tab === "missing") loadShows();
  if (tab === "subs") loadSubs();
  if (tab === "settings") loadSettings();
  if (tab === "logs") loadLogs();
}

/* ============================================================
   概览页
   ============================================================ */

async function loadHome() {
  // 1. 状态（首次使用引导）
  const status = await api("/api/status");
  if (status) {
    document.getElementById("banner").style.display = status.config_ok ? "none" : "block";
    // 开关状态
    setSwitch("swAutoScan", status.auto_scan, () => saveQuickSetting("auto_scan"));
    setSwitch("swAutoSub", status.auto_subscribe, () => saveQuickSetting("auto_subscribe"));
  }

  // 2. 统计数字
  const ov = await api("/api/overview");
  if (ov) {
    document.getElementById("stats").innerHTML = `
      <div class="stat blue"><div class="num">${ov.show_count}</div><div class="label">剧集数</div></div>
      <div class="stat warn"><div class="num">${ov.missing_count}</div><div class="label">缺集总数</div></div>
      <div class="stat danger"><div class="num">${ov.full_missing_seasons}</div><div class="label">整季缺失（季）</div></div>
      <div class="stat good"><div class="num">${ov.subscribed_count}</div><div class="label">已订阅</div></div>
      <div class="stat"><div class="num">${ov.error_count}</div><div class="label">识别异常</div></div>
      <div class="stat"><div class="num">${ov.unrecognized_count}</div><div class="label">未识别文件</div></div>
    `;
    // 顶栏"缺集"标签上的红点数字
    const badge = document.getElementById("badgeMissing");
    if (ov.missing_count > 0) { badge.textContent = ov.missing_count; badge.classList.remove("hide"); }
    else badge.classList.add("hide");
  }

  // 3. 上次扫描时间
  if (status) {
    document.getElementById("scanInfo").textContent =
      status.last_scan ? "上次扫描：" + status.last_scan : "还没有扫描过，点上面的按钮开始吧";
  }

  // 4. 扫描进度（如果正在扫就显示）
  checkScanStatus();
}

// 快速保存开关（自动扫描/自动订阅）
async function saveQuickSetting(key) {
  const body = {};
  const el = document.getElementById(key === "auto_scan" ? "swAutoScan" : "swAutoSub");
  body[key] = el.classList.contains("on") ? "1" : "0";
  await api("/api/settings", { method: "POST", body: JSON.stringify(body) });
}

// 开关组件：点一下切换状态
function setSwitch(id, on, onChange) {
  const el = document.getElementById(id);
  el.classList.toggle("on", !!on);
  el.onclick = () => {
    el.classList.toggle("on");
    if (onChange) onChange();
  };
}

// 开始扫描按钮
document.getElementById("btnScan").addEventListener("click", async () => {
  const data = await api("/api/scan", { method: "POST" });
  if (data !== null) {
    toast("扫描已开始，请稍等...", "success");
    checkScanStatus(true);
  }
});

// 轮询扫描进度（每 2 秒查一次）
let wasRunning = false;   // 记录上一次轮询时是否在扫描（用于扫描结束后的刷新）
async function checkScanStatus(force) {
  const status = await api("/api/scan/status");
  if (!status) return;
  const wrap = document.getElementById("scanProgress");
  if (status.running) {
    wasRunning = true;
    wrap.style.display = "block";
    const pct = status.total ? Math.round(status.done / status.total * 100) : 0;
    document.getElementById("scanFill").style.width = pct + "%";
    let text = `${status.phase}（${status.done}/${status.total}）`;
    const eta = formatETA(status.eta_seconds);
    if (eta) text += " · " + eta;
    if (status.current) text += ` · 当前：${status.current}`;
    document.getElementById("scanText").textContent = text;
    document.getElementById("btnScan").disabled = true;
    clearTimeout(state.scanTimer);
    state.scanTimer = setTimeout(checkScanStatus, 2000);
  } else {
    wrap.style.display = "none";
    document.getElementById("btnScan").disabled = false;
    // 扫描刚结束（之前还在跑）→ 刷新一次统计和列表
    if (force || wasRunning) {
      wasRunning = false;
      setTimeout(() => { loadHome(); loadShows(); }, 800);
    }
  }
}

// 一键订阅所有缺集
document.getElementById("btnSubAll").addEventListener("click", async () => {
  if (!confirm("确定要把所有缺的集都提交给 MoviePilot 订阅吗？\n（已订阅、已忽略、数据不准的会自动跳过）")) return;
  const data = await api("/api/subscribe/all", { method: "POST" });
  if (data) {
    toast(data.ok != null
      ? `完成！成功订阅 ${data.ok} 个季${data.fail ? `，${data.fail} 个失败` : ""}`
      : "完成", "success");
    loadHome();
  }
});

// 订阅预览（模拟订阅）：先看清单，确认后才真正提交
let previewItems = [];
document.getElementById("btnSubPreview").addEventListener("click", async () => {
  const data = await api("/api/subscribe/preview");
  if (!data) return;
  previewItems = data.items;
  const box = document.getElementById("modalBody");
  if (!data.total) {
    box.innerHTML = `<div class="empty">当前没有可订阅的缺集 🎉</div>`;
    document.getElementById("modalConfirm").style.display = "none";
  } else {
    let html = `<div class="muted" style="margin-bottom:10px">共 ${data.total} 个季要订阅，确认后一次性提交给 MoviePilot：</div>`;
    html += data.items.slice(0, 100).map(i =>
      `<div class="preview-item">${esc(i.name)} ${i.year ? `(${esc(i.year)})` : ""} — 第 ${i.season} 季（缺 ${i.missing_count} 集）</div>`).join("");
    if (data.total > 100) html += `<div class="muted" style="margin-top:8px">…还有 ${data.total - 100} 个季</div>`;
    if (data.degraded_count) html += `<div class="test-item fail" style="margin-top:10px">另有 ${data.degraded_count} 个季数据可能不准（TMDB 旧数据），已自动跳过</div>`;
    box.innerHTML = html;
    document.getElementById("modalConfirm").style.display = "block";
  }
  document.getElementById("modalTitle").textContent = "订阅预览";
  document.getElementById("modalMask").style.display = "flex";
});

document.getElementById("modalCancel").addEventListener("click", () => {
  document.getElementById("modalMask").style.display = "none";
});

document.getElementById("modalConfirm").addEventListener("click", async () => {
  document.getElementById("modalMask").style.display = "none";
  if (!previewItems.length) return;
  const data = await api("/api/subscribe/batch", {
    method: "POST",
    body: JSON.stringify({ items: previewItems.map(i => ({ tmdb_id: i.tmdb_id, season: i.season })) }),
  });
  if (data) {
    toast(`完成！成功订阅 ${data.ok} 个季${data.fail ? `，${data.fail} 个失败` : ""}`, "success");
    loadHome();
    loadShows();
  }
});

/* ============================================================
   缺集列表页
   ============================================================ */

// 筛选按钮
document.querySelectorAll("#filterChips .chip").forEach(chip => {
  chip.addEventListener("click", () => {
    document.querySelectorAll("#filterChips .chip").forEach(c => c.classList.remove("active"));
    chip.classList.add("active");
    state.filter = chip.dataset.filter;
    loadShows(true);
  });
});

// 搜索框（输入停顿 300ms 后自动搜索）
let searchTimer = null;
document.getElementById("searchInput").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadShows(true), 300);
});

// "加载更多"按钮（分页）
document.getElementById("btnLoadMore").addEventListener("click", () => {
  if (state.filter === "unrecognized") {
    state.uniOffset += 100;
    renderUnrecognized(true);
  } else {
    state.showsOffset += 50;
    loadShows(false, true);
  }
});

async function loadShows(reset, append) {
  if (reset) state.showsOffset = 0;
  const q = document.getElementById("searchInput").value.trim();
  const offset = append ? state.showsOffset : 0;
  const data = await api(`/api/shows?filter=${state.filter}&q=${encodeURIComponent(q)}&limit=50&offset=${offset}`);
  if (!data) return;
  state.showsTotal = data.total;
  state.showsOffset = offset + (data.shows || []).length;
  state.shows = append ? state.shows.concat(data.shows || []) : (data.shows || []);
  renderShows();
}

function renderShows() {
  const box = document.getElementById("missingList");
  // 未识别文件走单独的接口
  if (state.filter === "unrecognized") { renderUnrecognized(); return; }

  if (!state.shows.length) {
    box.innerHTML = `<div class="empty"><div class="big">🎉</div>当前条件下没有内容</div>`;
    document.getElementById("btnLoadMore").style.display = "none";
    document.getElementById("loadMoreInfo").textContent = "";
    return;
  }

  // 拼 HTML：一部剧一张卡片
  box.innerHTML = state.shows.map(show => {
    const seasons = (show.seasons || []).map(s => renderSeasonRow(show, s)).join("");
    const ignoredTag = show.ignore ? `<span class="tag ignored">已忽略整部</span>` : "";
    const errorTag = show.status === "error" ? `<span class="tag error">TMDB 查询失败</span>` : "";
    return `
      <div class="card show-card">
        <div class="show-head">
          <div class="show-poster">${show.poster
            ? `<img src="https://image.tmdb.org/t/p/w92${esc(show.poster)}" alt="">`
            : "暂无<br>海报"}</div>
          <div class="show-info">
            <div class="show-name">${esc(show.name)} ${show.year ? `<span class="muted">(${esc(show.year)})</span>` : ""}</div>
            <div class="show-meta">TMDB: ${show.tmdb_id} ${ignoredTag} ${errorTag}</div>
            ${seasons}
          </div>
          <div class="show-actions">
            <button class="btn ghost small" onclick="ignoreShow(${show.tmdb_id}, -1, ${show.ignore ? 1 : 0})">
              ${show.ignore ? "取消忽略" : "忽略整部"}
            </button>
          </div>
        </div>
      </div>`;
  }).join("");

  // 分页按钮：还有更多时显示
  const loaded = state.shows.length;
  const btn = document.getElementById("btnLoadMore");
  const info = document.getElementById("loadMoreInfo");
  if (loaded < state.showsTotal) {
    btn.style.display = "inline-block";
    info.textContent = `已显示 ${loaded} / ${state.showsTotal} 部`;
  } else {
    btn.style.display = "none";
    info.textContent = loaded ? `共 ${state.showsTotal} 部` : "";
  }
}

// 渲染一季的行（缺集信息 + 操作按钮）
function renderSeasonRow(show, s) {
  const tags = [];
  if (s.status === "partial") tags.push(`<span class="tag partial">缺部分集</span>`);
  if (s.status === "full_missing") tags.push(`<span class="tag full_missing">整季缺失</span>`);
  if (s.status === "complete") tags.push(`<span class="tag complete">已完整</span>`);
  if (s.subscribed) tags.push(`<span class="tag subscribed">已订阅 ${subStateTag(s.mp_state)}</span>`);
  if (s.ignored) tags.push(`<span class="tag ignored">已忽略</span>`);
  if (s.data_quality === "degraded") tags.push(`<span class="tag degraded" title="TMDB 数据可能不是最新的，自动订阅会跳过这一季">数据可能不准</span>`);

  // 详情文字
  let detail = "";
  if (s.status === "complete") {
    detail = `已有全部 ${s.aired_episodes} 集`;
  } else if (s.status === "full_missing") {
    detail = `整季缺失（应播出 ${s.aired_episodes} 集）`;
  } else {
    detail = `已有 ${s.present_episodes.length}/${s.aired_episodes} 集，` +
             `<span class="missing-eps">缺: ${esc(formatEps(s.missing_episodes))}</span>`;
  }

  // 操作按钮
  let actions = "";
  if (s.ignored) {
    actions = `<button class="btn ghost small" onclick="unignoreSeason(${show.tmdb_id}, ${s.season_number})">取消忽略</button>`;
  } else if (!s.subscribed && s.status !== "complete") {
    const label = s.status === "full_missing" ? "订阅整季" : "订阅缺集";
    actions = `<button class="btn small" onclick="subscribeSeason(${show.tmdb_id}, ${s.season_number})">${label}</button>`;
    actions += `<button class="btn ghost small" onclick="ignoreSeason(${show.tmdb_id}, ${s.season_number})">忽略这季</button>`;
  } else if (s.subscribed) {
    actions = `<span class="muted">已交给 MoviePilot，等待下载</span>`;
  }

  return `
    <div class="season-row">
      <div class="season-label">第${s.season_number}季</div>
      <div class="season-detail">${detail}</div>
      <div>${tags.join("")}</div>
      <div class="season-actions">${actions}</div>
    </div>`;
}

async function renderUnrecognized(append) {
  const offset = append ? state.uniOffset : 0;
  const data = await api(`/api/unrecognized?limit=100&offset=${offset}`);
  const box = document.getElementById("missingList");
  if (!data) return;
  state.uniTotal = data.total;
  state.uniOffset = offset + (data.items || []).length;

  if (!data.total) {
    box.innerHTML = `<div class="empty"><div class="big">👍</div>没有未识别的文件</div>`;
    document.getElementById("btnLoadMore").style.display = "none";
    document.getElementById("loadMoreInfo").textContent = "";
    return;
  }
  const html = (data.items || []).map(u => `
    <div class="card">
      <div><b>${esc(u.path)}</b></div>
      <div class="muted">原因：${esc(u.reason)}</div>
    </div>`).join("");
  box.innerHTML = append ? box.innerHTML + html : html;

  const btn = document.getElementById("btnLoadMore");
  const info = document.getElementById("loadMoreInfo");
  if (state.uniOffset < state.uniTotal) {
    btn.style.display = "inline-block";
    info.textContent = `已显示 ${state.uniOffset} / ${state.uniTotal} 条`;
  } else {
    btn.style.display = "none";
    info.textContent = `共 ${state.uniTotal} 条`;
  }
}

// 订阅某一季（网页上的按钮，带二次确认）
async function subscribeSeason(tmdbId, season) {
  if (!confirm(`确定把这季（第 ${season} 季）缺的集提交给 MoviePilot 下载吗？`)) return;
  const data = await api(`/api/shows/${tmdbId}/subscribe`, {
    method: "POST", body: JSON.stringify({ season }),
  });
  if (data) { toast("已提交订阅，MoviePilot 会自动搜索下载", "success"); loadShows(); loadHome(); }
}

// 忽略 / 取消忽略（带二次确认）
async function ignoreSeason(tmdbId, season) {
  if (!confirm(`确定忽略第 ${season} 季吗？忽略后不再提醒这一季。`)) return;
  await api(`/api/shows/${tmdbId}/ignore`, { method: "POST", body: JSON.stringify({ season }) });
  loadShows();
}
async function unignoreSeason(tmdbId, season) {
  await api(`/api/shows/${tmdbId}/unignore`, { method: "POST", body: JSON.stringify({ season }) });
  loadShows();
}
async function ignoreShow(tmdbId, season, currentlyIgnored) {
  if (!currentlyIgnored) {
    if (!confirm("确定忽略整部剧吗？忽略后这部剧不再出现在缺集列表里。")) return;
    await api(`/api/shows/${tmdbId}/ignore`, { method: "POST", body: JSON.stringify({ season }) });
  } else {
    await api(`/api/shows/${tmdbId}/unignore`, { method: "POST", body: JSON.stringify({ season }) });
  }
  loadShows();
}

/* ============================================================
   订阅管理页
   ============================================================ */

async function loadSubs() {
  const data = await api("/api/subscriptions");
  if (!data) return;
  document.getElementById("subsInfo").textContent =
    `共 ${data.total} 条` + (data.warning ? `（注意：${data.warning}）` : "");
  const body = document.getElementById("subsBody");
  if (!data.subscriptions.length) {
    body.innerHTML = `<tr><td colspan="4" class="empty">还没有任何订阅</td></tr>`;
    return;
  }
  body.innerHTML = data.subscriptions.map(s => `
    <tr>
      <td>${esc(s.name)}</td>
      <td>${s.season != null ? "第 " + s.season + " 季" : "-"}</td>
      <td>${subStateTag(s.state)}</td>
      <td><button class="btn red small" onclick="deleteSub(${s.mp_id})">删除</button></td>
    </tr>`).join("");
}

async function deleteSub(mpId) {
  if (!confirm("确定要删除这个订阅吗？")) return;
  const data = await api(`/api/subscriptions/${mpId}`, { method: "DELETE" });
  if (data) { toast("已删除", "success"); loadSubs(); }
}

document.getElementById("btnSubsRefresh").addEventListener("click", async () => {
  const data = await api("/api/subscriptions/refresh", { method: "POST" });
  if (data) { toast("订阅状态已刷新", "success"); loadSubs(); }
});

/* ============================================================
   设置页
   ============================================================ */

async function loadSettings() {
  const items = await api("/api/settings");
  if (!items) return;
  state.settings = items;
  const map = {};
  items.forEach(it => map[it.key] = it);
  // 表单填入当前值
  setVal("set_mp_url", map.mp_url);
  setVal("set_mp_token", map.mp_token);
  setVal("set_scan_paths", parsePaths(map.scan_paths.value).join("\n"));
  setVal("set_emby_url", map.emby_url);
  setVal("set_emby_api_key", map.emby_api_key);
  setVal("set_scan_interval", map.scan_interval);
  setVal("set_tmdb_key", map.tmdb_key);
  setVal("set_tmdb_lang", map.tmdb_lang);
  setSwitch("swAutoScanSet", map.auto_scan.value === "1");
  setSwitch("swAutoSubSet", map.auto_subscribe.value === "1");
  setSwitch("swSpecials", map.include_specials.value === "1");
}

// strm 目录列表：后端存的是 JSON 数组字符串，这里解析成数组（容错处理）
function parsePaths(v) {
  try {
    const arr = JSON.parse(v || "[]");
    if (Array.isArray(arr)) return arr;
  } catch (e) { /* 格式不对就走下面的兜底 */ }
  return String(v || "").split(",").map(s => s.trim()).filter(Boolean);
}

// 往表单控件里填值（不存在的控件忽略）
function setVal(id, val) {
  const el = document.getElementById(id);
  if (el) el.value = val && val.value != null ? val.value : (val || "");
}

// 从设置页收集所有值（带开关）
function collectSettings() {
  return {
    mp_url: getVal("set_mp_url"),
    mp_token: getVal("set_mp_token"),
    scan_paths: JSON.stringify(getVal("set_scan_paths").split("\n").map(s => s.trim()).filter(Boolean)),
    emby_url: getVal("set_emby_url"),
    emby_api_key: getVal("set_emby_api_key"),
    scan_interval: getVal("set_scan_interval") || "12",
    tmdb_key: getVal("set_tmdb_key"),
    tmdb_lang: getVal("set_tmdb_lang") || "zh-CN",
    auto_scan: document.getElementById("swAutoScanSet").classList.contains("on") ? "1" : "0",
    auto_subscribe: document.getElementById("swAutoSubSet").classList.contains("on") ? "1" : "0",
    include_specials: document.getElementById("swSpecials").classList.contains("on") ? "1" : "0",
  };
}
function getVal(id) { return (document.getElementById(id) || {}).value || ""; }

// 保存设置
document.getElementById("btnSettingsSave").addEventListener("click", async () => {
  const data = await api("/api/settings", {
    method: "POST", body: JSON.stringify(collectSettings()),
  });
  if (data) toast("设置已保存", "success");
});

// 测试连接
document.getElementById("btnSettingsTest").addEventListener("click", async () => {
  const data = await api("/api/settings/test", {
    method: "POST", body: JSON.stringify(collectSettings()),
  });
  if (!data) return;
  document.getElementById("testResult").innerHTML =
    '<div class="test-result">' + data.map(r => `
      <div class="test-item ${r.ok === true ? "ok" : r.ok === false ? "fail" : "none"}">
        <b>${esc(r.name)}</b>：${esc(r.detail)}
      </div>`).join("") + "</div>";
});

// 清空 TMDB 缓存（剧集更新后强制刷新数据）
document.getElementById("btnClearCache").addEventListener("click", async () => {
  if (!confirm("确定清空 TMDB 缓存吗？下次扫描会重新获取最新数据（多花一些时间）。")) return;
  const data = await api("/api/cache/refresh", { method: "POST" });
  if (data) toast("已清空，下次扫描会重新获取最新数据", "success");
});

/* ============================================================
   日志页
   ============================================================ */

async function loadLogs() {
  const data = await api("/api/logs?limit=300");
  if (!data) return;
  document.getElementById("logsBody").innerHTML = data.map(l => `
    <tr class="log-row">
      <td class="ts">${esc(l.ts)}</td>
      <td class="log-level ${esc(l.level)}">${esc(l.level)}</td>
      <td class="muted">${esc(l.category)}</td>
      <td class="log-msg">${esc(l.message)}</td>
    </tr>`).join("");
}

// 日志页每 5 秒自动刷新
setInterval(() => { if (state.tab === "logs") loadLogs(); }, 5000);

document.getElementById("btnLogsClear").addEventListener("click", async () => {
  if (!confirm("确定清空所有日志吗？")) return;
  await api("/api/logs", { method: "DELETE" });
  loadLogs();
});

/* ============================================================
   退出登录 / 修改密码
   ============================================================ */

document.getElementById("btnLogout").addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST" });
  location.href = "/login.html";
});

document.getElementById("btnChangePwd").addEventListener("click", async () => {
  const oldPwd = (document.getElementById("set_old_pwd").value || "").trim();
  const newPwd = (document.getElementById("set_new_pwd").value || "").trim();
  if (!oldPwd || !newPwd) { toast("请填写当前密码和新密码", "error"); return; }
  if (newPwd.length < 6) { toast("新密码至少 6 位", "error"); return; }
  const data = await api("/api/auth/change-password", {
    method: "POST",
    body: JSON.stringify({ old_password: oldPwd, new_password: newPwd }),
  });
  if (data) {
    toast("密码已修改，请牢记", "success");
    document.getElementById("set_old_pwd").value = "";
    document.getElementById("set_new_pwd").value = "";
  }
});

/* ============================================================
   启动：默认加载概览页
   ============================================================ */
loadHome();
