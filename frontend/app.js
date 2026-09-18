const $ = (selector) => document.querySelector(selector);
let platformData = null;
let selectedRoute = null;
let currentRole = "admin";
const apiFetch = (url, options = {}) => { options.headers = { ...(options.headers || {}), ...(localStorage.getItem("lp_token") ? { Authorization: `Bearer ${localStorage.getItem("lp_token")}` } : {}) }; return fetch(url, options); };

const project = ([lng, lat]) => [((lng - 107.70) / 0.16) * 100, ((30.75 - lat) / 0.15) * 100];
const metric = (label, value, unit, tone = "") => `<div class="metric"><div class="metric-label">${label}</div><div class="metric-value ${tone}">${value}<small>${unit}</small></div></div>`;

function renderMap() {
  const zones = platformData.layers.filter((x) => x.visible !== false && x.status === "published").map((x) => {
    const geometry = JSON.parse(x.geometry_json);
    return `<polygon points="${geometry.coordinates[0].map((p) => project(p).join(",")).join(" ")}" class="geo-zone ${x.layer_type}"><title>${x.name}</title></polygon>`;
  }).join("");
  const aircraft = platformData.vehicles.map((v) => {
    const [x, y] = project([v.longitude, v.latitude]);
    return `<g transform="translate(${x} ${y})" class="geo-aircraft"><circle r="1.7"/><text x="2.7" y="1">${v.id}</text></g>`;
  }).join("");
  const route = selectedRoute ? `<polyline points="${selectedRoute.points.map((p) => project(p).join(",")).join(" ")}" class="geo-route selected"><title>${selectedRoute.name}</title></polyline>` : "";
  $("#mapCanvas").innerHTML = `<svg class="geo-map" viewBox="0 0 100 100" preserveAspectRatio="none"><rect width="100" height="100" fill="#0f1a2a"/>${zones}${route}${aircraft}</svg><div class="map-label label-north">N · WGS84</div><div class="map-label label-south">梁平县域演示坐标范围</div>`;
}

function render(data) {
  platformData = data;
  data.layers.forEach((x) => { if (x.visible === undefined) x.visible = true; });
  const running = data.missions.filter((x) => x.status === "running").length;
  const warnings = data.missions.filter((x) => x.status === "warning").length;
  $("#metrics").innerHTML = [metric("在线飞行器", data.vehicles.length, "架"), metric("今日任务", data.missions.length, "项"), metric("运行中", running, "项", "green"), metric("待处置预警", warnings, "项", warnings ? "red" : "green")].join("");
  renderMap();
  $("#layerList").innerHTML = data.layers.map((x) => `<label class="layer-row"><input type="checkbox" ${x.visible && x.status === "published" ? "checked" : ""} ${x.status !== "published" ? "disabled" : ""} data-layer="${x.id}"><span class="layer-swatch ${x.layer_type}"></span><span>${x.name}</span><small>${x.status} · v${x.version}</small></label>`).join("");
  document.querySelectorAll("[data-layer]").forEach((control) => control.onchange = () => { data.layers.find((x) => String(x.id) === control.dataset.layer).visible = control.checked; renderMap(); });
  const writeControls = ["admin", "dispatcher"].includes(currentRole) ? `<button data-check="${"${x.id}"}">检查</button><button data-plan="${"${x.id}"}">航线</button><button data-flight="${"${x.id}"}">启动飞行</button><button class="event" data-event="${"${x.id}"}">注入告警</button>` : "";
  $("#missionList").innerHTML = data.missions.map((x) => `<article class="mission-item"><div class="mission-icon">${x.status === "running" ? "▶" : "○"}</div><div class="mission-main"><div class="mission-title">${x.name}</div><div class="mission-meta">${x.vehicle_id} · ${x.route_name} · ${x.planned_altitude}m</div></div><div class="mission-actions"><button data-detail="${x.id}">详情</button>${writeControls.replaceAll("${x.id}", x.id)}<span class="state state-${x.status}">${x.status_label}</span></div></article>`).join("");
  $("#ruleList").innerHTML = data.rules.map((x) => `<div class="rule-item"><span class="rule-code">${x.code}</span><span>${x.name}</span><span class="rule-level ${x.level}">${x.level_label}</span></div>`).join("");
  $("#vehicleList").innerHTML = data.vehicles.map((x) => `<div class="vehicle-item"><div><strong>${x.name}</strong><span>${x.model} · ${x.longitude.toFixed(3)}, ${x.latitude.toFixed(3)} · ${x.altitude}m</span></div><div class="vehicle-health"><span class="health-bar"><i style="width:${x.battery}%"></i></span><span>${x.battery}%</span></div></div>`).join("");
  $("#vehicleSelect").innerHTML = data.vehicles.map((x) => `<option value="${x.id}">${x.name}（${x.id}）</option>`).join("");
  document.querySelectorAll("[data-detail]").forEach((b) => b.onclick = () => showDetails(b.dataset.detail));
  document.querySelectorAll("[data-check]").forEach((b) => b.onclick = () => runAction(b.dataset.check, "check"));
  document.querySelectorAll("[data-plan]").forEach((b) => b.onclick = () => runAction(b.dataset.plan, "routes/plan"));
  document.querySelectorAll("[data-flight]").forEach((b) => b.onclick = () => startFlight(b.dataset.flight));
  document.querySelectorAll("[data-event]").forEach((b) => b.onclick = () => injectEvent(b.dataset.event));
}

function showError(result) {
  $("#resultBadge").textContent = "操作失败";
  $("#resultContent").innerHTML = `<div class="result-block blocked"><strong>${result.code}</strong><span>${result.message}</span></div>`;
}

async function showDetails(id) {
  const response = await apiFetch(`/api/missions/${id}`);
  const mission = await response.json();
  if (!response.ok) return showError(mission);
  const check = mission.checks[0];
  const route = mission.routes[0];
  $("#resultBadge").textContent = mission.status_label;
  $("#resultContent").innerHTML = `<div class="detail-grid"><span>任务编号</span><strong>${mission.id}</strong><span>飞行器</span><strong>${mission.vehicle_id}</strong><span>起终点</span><strong>${mission.start_lng}, ${mission.start_lat} → ${mission.end_lng}, ${mission.end_lat}</strong><span>计划高度</span><strong>${mission.planned_altitude} 米</strong><span>最近检查</span><strong>${check ? `${check.decision} / ${check.risk_level}` : "尚未检查"}</strong><span>候选航线</span><strong>${route ? `${route.name} / ${route.distance_m.toFixed(1)} 米` : "尚未生成"}</strong></div>`;
  loadEvents(id);
}

async function runAction(id, action) {
  const response = await apiFetch(`/api/missions/${id}/${action}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  const result = await response.json();
  if (!response.ok) return showError(result);
  if (action === "check") {
    $("#resultBadge").textContent = `${result.decision} · ${result.risk_level}`;
    $("#resultContent").innerHTML = `<div class="result-summary ${result.decision}">${result.decision === "pass" ? "规则检查通过，可生成航线" : result.decision === "warning" ? "存在软约束，需人工确认" : "存在硬约束，禁止生成航线"}</div>${result.items.length ? result.items.map((x) => `<div class="result-block ${x.level}"><strong>${x.rule_code}</strong><span>${x.message}</span><small>${x.action}</small></div>`).join("") : '<div class="result-empty">没有发现冲突项</div>'}`;
  } else {
    selectedRoute = result;
    renderMap();
    $("#resultBadge").textContent = "航线已生成";
    $("#resultContent").innerHTML = `<div class="route-result"><strong>${result.name}</strong><span>距离 ${result.distance_m} 米 · 预计 ${result.duration_s} 秒</span><span>风险等级：${result.risk_level}</span></div>`;
  }
}

async function startFlight(id) {
  const response = await apiFetch(`/api/missions/${id}/flight/start`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  const result = await response.json();
  if (!response.ok) return showError(result);
  $("#resultBadge").textContent = "飞行中";
  $("#resultContent").innerHTML = `<div class="flight-status">任务 ${id} 已启动模拟飞行 · 链路在线 · 电量 ${result.telemetry.battery}% <button data-tick="${id}">推进10%</button></div>`;
  bindTick(id);
}

function bindTick(id) {
  const button = $("[data-tick]");
  if (!button) return;
  button.onclick = async () => {
    const response = await apiFetch(`/api/missions/${id}/flight/tick`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ step: 10 }) });
    const result = await response.json();
    if (!response.ok) return showError(result);
    $("#resultBadge").textContent = `${result.status} · ${result.progress}%`;
    $("#resultContent").innerHTML = `<div class="flight-status">进度 ${result.progress}% · 位置 ${result.telemetry.longitude.toFixed(5)}, ${result.telemetry.latitude.toFixed(5)} · 电量 ${result.telemetry.battery}% ${result.status === "completed" ? "· 任务已完成" : ""} <button data-tick="${id}">继续推进</button></div>`;
    bindTick(id);
  };
}

async function injectEvent(id) {
  const type = window.prompt("输入事件类型：deviation / low_battery / link_loss / temporary_restriction", "low_battery");
  if (!type) return;
  const response = await apiFetch(`/api/missions/${id}/events`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ event_type: type }) });
  const result = await response.json();
  if (!response.ok) return showError(result);
  $("#resultBadge").textContent = "有新告警";
  $("#resultContent").innerHTML = `<div class="result-block ${result.severity === "critical" ? "hard" : "soft"}"><strong>${result.event_type}</strong><span>${result.message}</span><small>${result.severity}</small></div>`;
  loadEvents(id);
}

async function loadEvents(id) {
  const response = await apiFetch(`/api/missions/${id}/events`);
  if (!response.ok) return;
  const events = await response.json();
  $("#eventList").innerHTML = events.length ? events.map((event) => `<div class="event-row ${event.severity === "critical" ? "severity-critical" : "severity-warning"}"><strong>${event.event_type}</strong><span>${event.message}</span><small>${event.status}</small>${event.status === "open" ? `<button data-resolve="${event.id}">标记已处置</button>` : ""}</div>`).join("") : "";
  document.querySelectorAll("[data-resolve]").forEach((button) => button.onclick = async () => { await apiFetch(`/api/events/${button.dataset.resolve}/resolve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); loadEvents(id); });
}

async function bootstrap() {
  const response = await apiFetch("/api/bootstrap");
  if (response.status === 401) throw new Error("401 未登录");
  if (!response.ok) throw new Error("初始化数据加载失败");
  render(await response.json());
  $("#health").textContent = "● 服务正常 · SQLite 数据已加载";
}

const dialog = $("#missionDialog");
$("#newMission").onclick = () => dialog.showModal();
$("#closeDialog").onclick = () => dialog.close();
$("#cancelDialog").onclick = () => dialog.close();
$("#missionForm").onsubmit = async (event) => {
  event.preventDefault();
  const response = await apiFetch("/api/missions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))) });
  const result = await response.json();
  if (!response.ok) { $("#formMessage").textContent = result.message; return; }
  platformData.missions.unshift(result); render(platformData); dialog.close();
  $("#health").textContent = `● 任务 ${result.id} 已保存并写入审计日志`;
};

$("#loginForm").onsubmit = async (event) => { event.preventDefault(); const response = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))) }); const result = await response.json(); if (!response.ok) { $("#loginMessage").textContent = result.message; return; } localStorage.setItem("lp_token", result.token); currentRole = result.role; $("#currentUser").textContent = `${result.username} · ${result.role}`; $("#logoutButton").hidden = false; $("#loginGate").style.display = "none"; bootstrap(); };
$("#logoutButton").onclick = async () => { await apiFetch("/api/auth/logout", { method: "POST" }); localStorage.removeItem("lp_token"); $("#loginGate").style.display = "grid"; $("#logoutButton").hidden = true; };
bootstrap().catch((error) => { if (error.message.includes("401")) $("#loginGate").style.display = "grid"; $("#health").textContent = `● 服务不可用 · ${error.message}`; });
