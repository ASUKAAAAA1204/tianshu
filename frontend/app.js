const $ = (selector) => document.querySelector(selector);
let platformData = null;
let selectedRoute = null;
let selectedMissionId = null;
let selectedMapObject = null;
let currentRole = "admin";
let missionViaPoints = [];
const trackReplay = { missionId: null, samples: [], index: 0, playing: false, timer: null, message: "请选择任务" };
const apiFetch = (url, options = {}) => { options.headers = { ...(options.headers || {}), ...(localStorage.getItem("lp_token") ? { Authorization: `Bearer ${localStorage.getItem("lp_token")}` } : {}) }; return fetch(url, options); };
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);

const project = ([lng, lat]) => [((lng - 107.40) / 0.70) * 100, ((30.90 - lat) / 0.40) * 100];
const metric = (label, value, unit, tone = "") => `<div class="metric"><div class="metric-label">${label}</div><div class="metric-value ${tone}">${value}<small>${unit}</small></div></div>`;

function spatialObjectKey(feature) { const properties = feature?.properties || {}; return String(properties.id || properties.point_id || properties.name || ""); }
function isSpatialSelected(feature) { return selectedMapObject?.type === "spatial" && spatialObjectKey(selectedMapObject.feature) === spatialObjectKey(feature); }

function renderSpatialGeometry(feature) {
  const geometry = feature.geometry;
  const title = feature.properties?.name || feature.properties?.point_id || "空间对象";
  const selectedClass = isSpatialSelected(feature) ? " is-selected" : "";
  if (!geometry) return "";
  if (geometry.type === "Polygon") return `<polygon points="${geometry.coordinates[0].map((p) => project(p).join(",")).join(" ")}" class="geo-spatial ${feature.properties?.asset_type || "polygon"}${selectedClass}"><title>${title}</title></polygon>`;
  if (geometry.type === "MultiPolygon") return geometry.coordinates.map((polygon) => `<polygon points="${polygon[0].map((p) => project(p).join(",")).join(" ")}" class="geo-spatial ${feature.properties?.asset_type || "polygon"}${selectedClass}"><title>${title}</title></polygon>`).join("");
  if (geometry.type === "Point") {
    const [x, y] = project(geometry.coordinates);
    return `<g transform="translate(${x} ${y})" class="geo-spatial-point ${feature.properties?.asset_type || "point"}${selectedClass}"><circle r="1.1"><title>${title}</title></circle></g>`;
  }
  return "";
}

function displayMapObject(type, value) {
  selectedMapObject = type === "vehicle" ? { type, id: value.id } : { type, feature: value };
  const properties = type === "vehicle" ? value : value.properties || {};
  const isBuilding = type === "building";
  const tileProperties = isBuilding && properties.tile_reference && typeof properties.tile_reference === "object" ? properties.tile_reference : null;
  const title = type === "vehicle" ? (value.name || value.id) : (properties.name || properties.point_id || (isBuilding ? `建筑轮廓 · ${value.id || "未命名"}` : "空间对象"));
  const isRisk = type === "spatial" && ["obstacle", "hazard", "restricted"].includes(properties.asset_type);
  const detailRows = type === "vehicle" ? [
    ["对象类型", "飞行器"], ["运行状态", value.status_label || value.status || "未提供"],
    ["高度", value.altitude != null ? `${value.altitude} m · 合成演示值` : "未提供"],
    ["电量", value.battery != null ? `${value.battery}% · 合成演示值` : "未提供"],
    ["链路", value.link_status || "未提供"], ["数据时间", value.updated_at || value.telemetry_at || "未提供"], ["数据来源", "合成演示数据"],
  ] : isBuilding ? [
    ["对象类型", "矢量建筑轮廓 · 公开参考"],
    ["建筑高度属性", properties.height != null ? `${properties.height} m · 瓦片属性` : properties["building:height"] != null ? `${properties["building:height"]} m · 瓦片属性` : "未提供"],
    ["地图挤出高度", properties.render_height != null ? `${properties.render_height} m · 样式渲染值，可能为估算` : "当前要素未提供"],
    ["楼层数", properties["building:levels"] != null ? `${properties["building:levels"]} 层 · 瓦片属性` : "未提供"],
    ["数据来源", properties.source_kind === "geofabrik_osm_reference" ? "Geofabrik / © OpenStreetMap contributors · ODbL 1.0" : "OpenMapTiles / OpenStreetMap contributors"],
    ...(tileProperties ? [
      ["在线瓦片建筑高度", tileProperties.height != null ? `${tileProperties.height} m · 原始瓦片属性` : tileProperties["building:height"] != null ? `${tileProperties["building:height"]} m · 原始瓦片属性` : "未提供"],
      ["在线瓦片楼层数", tileProperties["building:levels"] != null ? `${tileProperties["building:levels"]} 层 · 瓦片属性` : "未提供"],
      ["在线挤出渲染高度", tileProperties.render_height != null ? `${tileProperties.render_height} m · 样式渲染值，可能为估算` : "未提供"],
      ["在线属性来源", "OpenFreeMap / OpenMapTiles schema / OpenStreetMap contributors"],
    ] : []),
    ["判定边界", "底图参考对象；不代表完整建筑障碍库或实测高度，不参与安全放行"],
  ] : [
    ["对象类型", properties.asset_type || "未分类"], ["风险级别", properties.risk_level || (isRisk ? "未提供" : "未标注")],
    ["高度/限制", properties.height_m != null ? `对象高度 ${properties.height_m} m` : properties.min_altitude_m != null || properties.max_altitude_m != null ? `${properties.min_altitude_m ?? "未提供"}-${properties.max_altitude_m ?? "未提供"} m` : "未提供"],
    ["有效时段", properties.valid_from || properties.valid_to ? `${properties.valid_from || "未提供"} 至 ${properties.valid_to || "未提供"}` : "未提供"],
    ["数据时间", properties.updated_at || properties.observed_at || "未提供（演示数据）"], ["数据版本", properties.data_version || "未提供"], ["数据来源", properties.source_kind || properties.source || "公开参考，具体来源未提供"],
    ["核验状态", "需人工核验；不代表授权/许可结论"],
  ];
  const content = $("#resultContent");
  content.dataset.selectedObjectType = type;
  content.dataset.selectedObjectId = type === "vehicle" ? value.id : String(properties.id || properties.point_id || properties.name || "");
  content.dataset.selectedRisk = String(isRisk);
  const block = document.createElement("div");
  block.className = `result-block ${type === "vehicle" ? "pass" : isRisk ? "blocked" : "soft"}`;
  const heading = document.createElement("strong"); heading.textContent = title;
  const grid = document.createElement("div"); grid.className = "object-detail-grid";
  detailRows.forEach(([label, valueText]) => { const labelNode = document.createElement("span"); labelNode.textContent = label; const valueNode = document.createElement("strong"); valueNode.textContent = valueText; grid.append(labelNode, valueNode); });
  block.append(heading, grid);
  content.replaceChildren(block);
  $("#resultBadge").textContent = type === "vehicle" ? "飞行器 · 模拟数据" : isBuilding ? "建筑轮廓 · 底图参考" : isRisk ? `风险对象 · ${properties.risk_level || "级别未提供"} · 待核验` : "空间对象 · 参考数据";
  renderMap();
}

$("#facilityForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const message = $("#facilityFormMessage");
  const response = await apiFetch("/api/facilities", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(new FormData(form))) });
  const result = await response.json();
  console.debug("facility-create", response.status, result);
  if (!response.ok) { message.textContent = result.message || "设施创建失败"; return; }
  platformData.facilities.push(result); form.reset(); message.textContent = "设施已保存"; render(platformData);
});

function renderMap() {
  if (window.lpMap?.render) {
    const mission = platformData.missions.find((item) => item.id === selectedMissionId);
    window.lpMap.render({
      data: platformData,
      selectedRoute,
      selectedMissionId,
      selectedVehicleId: mission?.vehicle_id,
      selectedMapObject,
      replayTrack: trackReplay,
      onVehicleClick: (id) => { const vehicle = platformData.vehicles.find((item) => item.id === id); if (vehicle) displayMapObject("vehicle", vehicle); },
      onSpatialClick: (feature) => { if (feature) displayMapObject("spatial", feature); },
      onBuildingClick: (feature) => { if (feature) displayMapObject("building", feature); },
    });
    const summary = document.querySelector("#mapMissionSummary");
    if (summary) summary.textContent = mission ? `${mission.id} · ${mission.name} · ${mission.status_label} · ${mission.planned_altitude || "高度未提供"}m` : "暂无任务 · 当前地图仅显示可用空间参考对象";
    renderMapTimeline(mission);
    return;
  }
  const spatial = (platformData.spatial_assets?.features || []).filter((x) => x.visible !== false);
  const spatialGeometry = spatial.map(renderSpatialGeometry).join("");
  const zones = platformData.layers.filter((x) => x.visible !== false && x.status === "published").map((x) => {
    const geometry = JSON.parse(x.geometry_json);
    return `<polygon points="${geometry.coordinates[0].map((p) => project(p).join(",")).join(" ")}" class="geo-zone ${x.layer_type}"><title>${x.name}</title></polygon>`;
  }).join("");
  const aircraft = platformData.vehicles.map((v) => {
    const [x, y] = project([v.longitude, v.latitude]);
    return `<g transform="translate(${x} ${y})" class="geo-aircraft"><circle r="1.7"/><text x="2.7" y="1">${v.id}</text></g>`;
  }).join("");
  const route = selectedRoute ? `<polyline points="${selectedRoute.points.map((p) => project(p).join(",")).join(" ")}" class="geo-route selected"><title>${selectedRoute.name}</title></polyline>` : "";
  $("#mapCanvas").innerHTML = `<svg class="geo-map" viewBox="0 0 100 100" preserveAspectRatio="none"><rect width="100" height="100" fill="#0f1a2a"/>${spatialGeometry}${zones}${route}${aircraft}</svg><div class="map-label label-north">N · WGS84 · 公开参考图层</div><div class="map-label label-south">梁平县域演示坐标范围</div>`;
}

function formatTime(value) {
  if (!value) return "未提供";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
}

function timelineStatus(start, end) {
  if (!start && !end) return "时间未提供";
  const now = Date.now(); const from = start ? new Date(start).getTime() : -Infinity; const to = end ? new Date(end).getTime() : Infinity;
  if (Number.isFinite(to) && now > to) return "已结束";
  if (Number.isFinite(from) && now < from) return "待开始";
  return "进行中（演示）";
}

function renderMapTimeline(mission) {
  const track = $("#mapTimelineTrack"); if (!track) return;
  track.replaceChildren();
  if (!mission) { const empty = document.createElement("div"); empty.className = "timeline-empty"; empty.textContent = "暂无选中任务，无法生成时间上下文"; track.append(empty); return; }
  const items = [];
  const push = (kind, label, start, end, detail, action) => items.push({ kind, label, start, end, detail, action });
  push("mission-window", "任务窗口", mission.time_window_start, mission.time_window_end, `${formatTime(mission.time_window_start)} → ${formatTime(mission.time_window_end)} · ${timelineStatus(mission.time_window_start, mission.time_window_end)}`, () => showDetails(mission.id));
  const spatial = platformData.map_features?.features || platformData.spatial_assets?.features || [];
  spatial.filter((feature) => feature.properties?.asset_type === "restricted").forEach((feature) => { const props = feature.properties || {}; push("window-control", `临时管制 · ${props.name || "参考限制区"}`, props.valid_from, props.valid_to, `${formatTime(props.valid_from)} → ${formatTime(props.valid_to)} · ${timelineStatus(props.valid_from, props.valid_to)}`, () => displayMapObject("spatial", feature)); });
  (platformData.alerts || []).filter((item) => !item.mission_id || item.mission_id === mission.id).forEach((alert) => { const at = alert.occurred_at || alert.created_at || alert.timestamp; push("alert-point", `告警 · ${alert.event_type || alert.code || "运行事件"}`, at, at, `${formatTime(at)} · ${alert.status || "状态未提供"}`, () => { $("#resultBadge").textContent = `告警 · ${alert.severity || "级别未提供"}`; $("#resultContent").textContent = `${alert.message || "告警详情未提供"} · 需人工核验 · 合成演示数据`; }); });
  const updated = mission.updated_at || mission.created_at || platformData.generated_at;
  push("data-point", "数据更新时间", updated, updated, `${formatTime(updated)} · 来源：合成演示数据`, () => { $("#resultBadge").textContent = "数据边界"; $("#resultContent").textContent = "当前时间戳仅用于演示，不代表实时遥测或权威运行时间"; });
  items.sort((a, b) => (new Date(a.start || "9999-12-31").getTime() || 0) - (new Date(b.start || "9999-12-31").getTime() || 0));
  items.forEach((item) => { const button = document.createElement("button"); button.type = "button"; const timeState = item.detail.includes("已结束") ? "ended" : item.detail.includes("待开始") ? "upcoming" : item.detail.includes("进行中") ? "active" : "unknown"; button.className = `timeline-item ${item.kind} time-${timeState}`; button.dataset.timelineLabel = item.label; button.dataset.timeState = timeState; button.setAttribute("aria-label", `${item.label}，${item.detail}`); const title = document.createElement("strong"); title.textContent = item.label; const detail = document.createElement("span"); detail.textContent = item.detail; const source = document.createElement("small"); source.textContent = "公开参考 / 合成演示数据"; button.append(title, detail, source); button.addEventListener("click", () => { document.querySelectorAll(".timeline-item").forEach((node) => node.classList.remove("is-active")); item.action?.(); window.setTimeout(() => { const active = [...document.querySelectorAll(".timeline-item")].find((node) => node.dataset.timelineLabel === item.label); active?.classList.add("is-active"); }, 0); }); track.append(button); });
}

function renderTrackReplay() {
  const samples = trackReplay.samples;
  const slider = $("#trackReplayRange"); const toggle = $("#trackReplayToggle");
  if (!slider || !toggle) return;
  slider.max = String(Math.max(0, samples.length - 1));
  slider.value = String(Math.min(trackReplay.index, Math.max(0, samples.length - 1)));
  slider.disabled = samples.length < 2;
  toggle.disabled = samples.length < 2;
  toggle.textContent = trackReplay.playing ? "Ⅱ" : "▶";
  toggle.setAttribute("aria-label", trackReplay.playing ? "暂停轨迹回放" : "播放轨迹回放");
  $("#trackReplayStatus").textContent = samples.length >= 2 ? `${samples.length} 个定位点 · 仅回放已记录轨迹` : trackReplay.message;
  const sample = samples[trackReplay.index];
  $("#trackReplayTime").textContent = sample?.timestamp ? formatTime(sample.timestamp) : "--";
}

function stopTrackReplay() {
  if (trackReplay.timer) window.clearInterval(trackReplay.timer);
  trackReplay.timer = null; trackReplay.playing = false;
}

async function loadTrackReplay(missionId) {
  if (missionId && selectedMissionId !== missionId) return;
  stopTrackReplay();
  Object.assign(trackReplay, { missionId, samples: [], index: 0, message: "正在读取已记录轨迹…" });
  renderTrackReplay();
  if (!missionId) { trackReplay.message = "请选择任务"; renderTrackReplay(); return; }
  const response = await apiFetch(`/api/missions/${encodeURIComponent(missionId)}/telemetry/track`);
  if (selectedMissionId !== missionId || trackReplay.missionId !== missionId) return;
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    trackReplay.message = result.code === "TRACK_NOT_FOUND" ? "暂无可回放轨迹" : (result.message || "轨迹读取失败");
    renderTrackReplay(); return;
  }
  const result = await response.json();
  trackReplay.samples = (result.samples || []).filter((sample) => Number.isFinite(Number(sample.longitude)) && Number.isFinite(Number(sample.latitude)) && Number.isFinite(Number(sample.sequence)));
  trackReplay.index = Math.max(0, trackReplay.samples.length - 1);
  trackReplay.message = trackReplay.samples.length < 2 ? (result.message || "轨迹点不足，暂不可回放") : "";
  renderTrackReplay(); renderMap();
}

function setTrackReplayIndex(index) {
  trackReplay.index = Math.max(0, Math.min(trackReplay.samples.length - 1, Number(index) || 0));
  renderTrackReplay(); renderMap();
}

$("#trackReplayRange")?.addEventListener("input", (event) => { stopTrackReplay(); setTrackReplayIndex(event.currentTarget.value); });
$("#trackReplayToggle")?.addEventListener("click", () => {
  if (trackReplay.playing) { stopTrackReplay(); renderTrackReplay(); return; }
  if (trackReplay.samples.length < 2) return;
  if (trackReplay.index >= trackReplay.samples.length - 1) setTrackReplayIndex(0);
  trackReplay.playing = true; renderTrackReplay();
  trackReplay.timer = window.setInterval(() => {
    const next = trackReplay.index + 1;
    if (next >= trackReplay.samples.length) { stopTrackReplay(); renderTrackReplay(); return; }
    setTrackReplayIndex(next);
    if (next >= trackReplay.samples.length - 1) { stopTrackReplay(); renderTrackReplay(); }
  }, 600);
});

function render(data) {
  platformData = data;
  renderDataRegister(data);
  const isDemoNoise = (item) => /(?:api\s*smoke|e2e设施|b3b4|e2e|平台联调|联调测试|测试任务)/i.test(`${item.id || ""} ${item.name || ""} ${item.route_name || ""}`);
  const displayMissions = data.missions.filter((item) => !isDemoNoise(item));
  if (!displayMissions.some((item) => item.id === selectedMissionId)) selectedMissionId = displayMissions.find((item) => item.status === "running")?.id || displayMissions[0]?.id || null;
  data.layers.forEach((x) => { if (x.visible === undefined) x.visible = true; });
  const running = displayMissions.filter((x) => x.status === "running").length;
  const warnings = displayMissions.filter((x) => x.status === "warning").length;
  const altitudeLabels = { all: "全部高度", "0-60": "0–60 m", "60-120": "60–120 m", "120-300": "120–300 m", "300+": "300 m 以上" };
  const altitudeFilter = $("#altitudeFilter"); const altitudeReadout = $("#altitudeLayerReadout");
  if (altitudeFilter && altitudeReadout) { altitudeReadout.textContent = `当前高度层：${altitudeLabels[altitudeFilter.value] || "全部高度"}`; }
  $("#metrics").innerHTML = [metric("飞行器", data.vehicles.length, "架"), metric("任务", displayMissions.length, "项"), metric("运行中", running, "项", "green"), metric("待确认", warnings, "项", warnings ? "red" : "green")].join("");
  renderMap();
  $("#layerList").innerHTML = data.layers.map((x) => `<label class="layer-row"><input type="checkbox" ${x.visible && x.status === "published" ? "checked" : ""} ${x.status !== "published" ? "disabled" : ""} data-layer="${x.id}"><span class="layer-swatch ${x.layer_type}"></span><span>${x.name}</span><small>${x.status === "published" ? "可用" : "未发布"} · v${x.version}</small></label>`).join("");
  document.querySelectorAll("[data-layer]").forEach((control) => control.onchange = () => { data.layers.find((x) => String(x.id) === control.dataset.layer).visible = control.checked; renderMap(); });
  const facilities = data.facilities || data.facilities_list || [];
  const displayFacilities = facilities.filter((item) => !/(?:e2e|api\s*smoke|b3b4|测试)/i.test(`${item.facility_id || ""} ${item.name || ""}`));
  $("#facilityList").innerHTML = displayFacilities.map((item) => `<div class="facility-row"><div><strong>${item.name || item.facility_id}</strong><span>${item.facility_type || "设施"} · ${item.status || "unknown"}</span></div><small>${item.service_radius_m ? `${item.service_radius_m}m` : "半径未知"} · ${item.opening_hours || "时间未知"}</small></div>`).join("") || `<div class="result-empty">暂无设施数据</div>`;
  renderFacilityAdmin(facilities);
  const writeControls = ["admin", "dispatcher"].includes(currentRole) ? `<button data-check="${"${x.id}"}">检查</button><button data-plan="${"${x.id}"}">航线</button><button data-flight="${"${x.id}"}" __FLIGHT_DISABLED__>启动飞行</button><button class="event" data-event="${"${x.id}"}">注入告警</button>` : "";
  const orderedMissions = [...displayMissions].sort((a, b) => Number(b.id === selectedMissionId) - Number(a.id === selectedMissionId));
  $("#missionList").innerHTML = orderedMissions.map((x) => `<article class="mission-item ${x.id === selectedMissionId ? "is-selected" : ""}" data-mission-card="${x.id}"><button class="mission-select" type="button" data-select-mission="${x.id}" aria-pressed="${x.id === selectedMissionId}"><span class="mission-icon">${x.status === "running" ? "▶" : "○"}</span><span class="mission-main"><span class="mission-title">${x.name}</span><span class="mission-meta">${x.vehicle_id} · ${x.route_name} · ${x.planned_altitude}m</span></span><span class="state state-${x.status}">${x.status_label}</span></button><div class="mission-actions"><button data-detail="${x.id}">详情</button>${writeControls.replaceAll("${x.id}", x.id).replace("__FLIGHT_DISABLED__", x.selected_route_id ? "" : "disabled title=\"需先人工采用航线\"")}</div></article>`).join("") || `<div class="result-empty">暂无运行任务</div>`;
  $("#ruleList").innerHTML = data.rules.map((x) => `<div class="rule-item"><span class="rule-code">${x.code}</span><span>${x.name}</span><span class="rule-level ${x.level}">${x.level_label}</span></div>`).join("");
  $("#vehicleList").innerHTML = data.vehicles.map((x) => `<div class="vehicle-item"><div><strong>${x.name}</strong><span>${x.model} · ${x.longitude.toFixed(3)}, ${x.latitude.toFixed(3)} · ${x.altitude}m</span></div><div class="vehicle-health"><span class="health-bar"><i class="health-fill" data-battery="${x.battery}"></i></span><span>${x.battery}%</span></div></div>`).join("");
  document.querySelectorAll(".health-fill").forEach((bar) => { bar.style.width = `${bar.dataset.battery}%`; });
  $("#vehicleSelect").innerHTML = data.vehicles.map((x) => `<option value="${x.id}">${x.name}（${x.id}）</option>`).join("");
  document.querySelectorAll("[data-detail]").forEach((b) => b.onclick = () => showDetails(b.dataset.detail));
  document.querySelectorAll("[data-select-mission]").forEach((button) => button.onclick = () => selectMission(button.dataset.selectMission));
  document.querySelectorAll("[data-check]").forEach((b) => b.onclick = () => runAction(b.dataset.check, "check"));
  document.querySelectorAll("[data-plan]").forEach((b) => b.onclick = () => runAction(b.dataset.plan, "routes/plan"));
  document.querySelectorAll("[data-flight]").forEach((b) => b.onclick = () => startFlight(b.dataset.flight));
  document.querySelectorAll("[data-event]").forEach((b) => b.onclick = () => injectEvent(b.dataset.event));
}

function renderDataRegister(data) {
  const target = $("#dataRegister"); if (!target) return;
  target.replaceChildren();
  const rows = [
    ["DEM / 高程", "公开查询可用 · 本地为合成网格", "Open-Meteo / Copernicus GLO-90 · 垂直基准未知 · 不作净空判断", "demo"],
    ["空域与限制", "公开参考 / 合成", "来源版本未登记为权威许可", "demo"],
    ["建筑轮廓", "158 个公开参考 · 高度 0/158", "Geofabrik / OpenStreetMap · ODbL · 局部数据，不作三维碰撞判定", "not-ready"],
  ];
  rows.forEach(([title, status, note, tone]) => { const row = document.createElement("div"); row.className = `data-register-row ${tone}`; const heading = document.createElement("strong"); heading.textContent = `${title} · ${status}`; const detail = document.createElement("small"); detail.textContent = note; row.append(heading, detail); target.append(row); });
}

function renderFacilityAdmin(facilities) {
  const target = $("#facilityAdminList");
  if (!target) return;
  target.innerHTML = facilities.map((item) => `<div class="facility-admin-row"><div><strong>${item.name || item.facility_id}</strong><small>${item.facility_id} · ${item.status}</small></div><div class="facility-admin-actions"><button type="button" data-facility-maintain="${item.facility_id}" ${item.status === "disabled" ? "disabled" : ""}>维护</button><button type="button" data-facility-disable="${item.facility_id}" ${item.status === "disabled" ? "disabled" : ""}>停用</button></div></div>`).join("") || `<div class="result-empty">暂无设施数据</div>`;
  target.querySelectorAll("[data-facility-maintain]").forEach((button) => { button.onclick = () => updateFacility(button.dataset.facilityMaintain, { status: "maintenance" }); });
  target.querySelectorAll("[data-facility-disable]").forEach((button) => { button.onclick = () => updateFacility(button.dataset.facilityDisable, null, true); });
}

function selectMission(id) {
  if (!platformData?.missions?.some((mission) => mission.id === id)) return;
  selectedMissionId = id;
  selectedRoute = null;
  selectedMapObject = null;
  $("#elevationProfile").textContent = "任务已切换；请重新查询该任务高程参考。";
  $("#resultContent").removeAttribute("data-selected-object-type");
  $("#resultContent").removeAttribute("data-selected-object-id");
  document.querySelectorAll("[data-mission-card]").forEach((card) => {
    const selected = card.dataset.missionCard === id;
    card.classList.toggle("is-selected", selected);
    card.querySelector("[data-select-mission]")?.setAttribute("aria-pressed", String(selected));
  });
  renderMap();
  void loadTrackReplay(id);
  showDetails(id);
}

async function updateFacility(id, patch = {}, disable = false) {
  const response = await apiFetch(`/api/facilities/${id}`, { method: disable ? "DELETE" : "PATCH", headers: { "Content-Type": "application/json" }, body: disable ? undefined : JSON.stringify(patch) });
  const result = await response.json();
  if (!response.ok) { $("#facilityFormMessage").textContent = result.message || "设施更新失败"; return; }
  const item = platformData.facilities.find((facility) => facility.facility_id === id);
  if (item) Object.assign(item, result);
  render(platformData);
}

function showError(result) {
  $("#resultBadge").textContent = "操作失败";
  $("#resultContent").innerHTML = `<div class="result-block blocked"><strong>${result.code}</strong><span>${result.message}</span></div>`;
}

async function showDetails(id) {
  selectedMapObject = null;
  $("#resultContent").removeAttribute("data-selected-object-type");
  $("#resultContent").removeAttribute("data-selected-object-id");
  if (platformData?.missions?.some((mission) => mission.id === id) && selectedMissionId !== id) {
    selectedMissionId = id;
    document.querySelectorAll("[data-mission-card]").forEach((card) => {
      const selected = card.dataset.missionCard === id;
      card.classList.toggle("is-selected", selected);
      card.querySelector("[data-select-mission]")?.setAttribute("aria-pressed", String(selected));
    });
    renderMap();
  }
  if (trackReplay.missionId !== id) void loadTrackReplay(id);
  const response = await apiFetch(`/api/missions/${id}`);
  const mission = await response.json();
  if (!response.ok) return showError(mission);
  const check = mission.checks[0];
  const route = mission.routes[0];
  $("#resultBadge").textContent = mission.status_label;
  selectedRoute = mission.routes.find((item) => Number(item.id) === Number(mission.selected_route_id)) || null;
  renderMap();
  const terrain = route?.terrain;
  const terrainSummary = terrain?.available ? `${terrain.terrain_risk} · 起点至最高采样点相对起伏 ${terrain.terrain_relief_m}m · ${terrain.sample_count}点 · 合成演示估算` : "暂无DEM参考";
  const decisions = mission.route_decisions || [];
  const canReview = ["admin", "dispatcher"].includes(currentRole) && !["running", "completed"].includes(mission.status);
  const routeHistory = mission.routes?.length ? `<div class="subhead">候选航线与人工复核</div><div class="route-history">${mission.routes.map((item) => {
    const latestDecision = decisions.find((decision) => Number(decision.route_id) === Number(item.id));
    const adopted = Number(mission.selected_route_id) === Number(item.id) && latestDecision?.decision === "adopted";
    const decisionLabel = adopted ? "当前已采用" : ({ adopted: "曾采用 · 已被替换", returned: "已退回修改", revoked: "已撤销" }[latestDecision?.decision] || "待人工复核");
    const actionMarkup = canReview && (!latestDecision || adopted) ? `<div class="route-review-actions"><label>决策理由<input type="text" maxlength="500" required data-route-reason="${item.id}" placeholder="填写采用、退回或撤销理由"></label><div>${adopted ? `<button type="button" data-route-decision="revoke" data-route-id="${item.id}">撤销采用</button>` : `<button type="button" data-route-decision="adopt" data-route-id="${item.id}">采用航线</button><button type="button" data-route-decision="return" data-route-id="${item.id}">退回修改</button>`}</div></div>` : "";
    return `<article class="route-review ${adopted ? "is-adopted" : ""}"><div class="route-review-head"><strong>${escapeHtml(item.name)}</strong><span>${decisionLabel}</span></div><span>${Number(item.distance_m).toFixed(1)} 米 · ${Number(item.duration_s).toFixed(1)} 秒 · 风险 ${escapeHtml(item.risk_level)}</span><small>${item.terrain?.available ? `DEM合成演示 · 相对地形起伏 ${item.terrain.terrain_relief_m}m · 不代表离地净空` : "暂无DEM参考"} · ${escapeHtml(item.created_at || "已记录")}</small>${actionMarkup}</article>`;
  }).join("")}</div>` : "";
  const decisionHistory = decisions.length ? `<div class="subhead">决策审计记录</div><div class="route-decision-history">${decisions.map((item) => `<div><strong>${({ adopted: "采用", returned: "退回修改", revoked: "撤销" }[item.decision] || escapeHtml(item.decision))} · 航线 #${item.route_id}</strong><span>${escapeHtml(item.reason || "未提供理由")}</span><small>${escapeHtml(item.actor_username || "未知操作者")} · ${escapeHtml(item.created_at || "时间未记录")}</small></div>`).join("")}</div>` : "";
  $("#resultContent").innerHTML = `<div class="detail-grid"><span>任务编号</span><strong>${escapeHtml(mission.id)}</strong><span>飞行器</span><strong>${escapeHtml(mission.vehicle_id)}</strong><span>起终点</span><strong>${mission.start_lng}, ${mission.start_lat} → ${mission.end_lng}, ${mission.end_lat}</strong><span>计划高度</span><strong>${mission.planned_altitude} 米</strong><span>最近检查</span><strong>${check ? `${escapeHtml(check.decision)} / ${escapeHtml(check.risk_level)}` : "尚未检查"}</strong><span>候选航线</span><strong>${route ? `${escapeHtml(route.name)} / ${Number(route.distance_m).toFixed(1)} 米` : "尚未生成"}</strong><span>地形参考</span><strong>${terrainSummary}</strong><span>飞行状态</span><strong>${mission.selected_route_id ? "当前采用航线已确认" : "未采用航线，禁止启动模拟飞行"}</strong></div>${routeHistory}${decisionHistory}`;
  bindRouteDecisionButtons(mission.id);
  if (mission.replans?.length) {
    $("#resultContent").innerHTML += mission.replans.map((item) => `<div class="result-block ${item.status === "confirmed" ? "pass" : "soft"}"><strong>重规划 #${item.id}</strong><span>${item.reason}</span><small>${item.status}${item.status === "proposed" ? ` <button data-confirm-replan="${item.id}" data-mission="${mission.id}">人工确认</button>` : ""}</small></div>`).join("");
    bindReplanButtons(mission.id);
  }
  loadEvents(id);
  loadTimeline(id);
}

async function runAction(id, action) {
  const response = await apiFetch(`/api/missions/${id}/${action}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  const result = await response.json();
  if (!response.ok) return showError(result);
  if (action === "check") {
    $("#resultBadge").textContent = `${result.decision} · ${result.risk_level}`;
  const terrainNote = result.terrain?.available ? `<div class="result-block soft"><strong>DEM参考 · 合成演示</strong><span>起始高程 ${result.terrain.start_elevation_m}m · 最大高程 ${result.terrain.terrain_max_m}m · 相对地形起伏 ${result.terrain.terrain_relief_m}m</span><small>${result.terrain.sample_count}个采样点 · 仅为相对地形起伏参考，不代表离地净空或安全放行</small></div>` : `<div class="result-block soft"><strong>DEM参考未接入</strong><span>当前结果不包含地形净空判定</span><small>公开参考 / 合成演示数据</small></div>`;
    $("#resultContent").innerHTML = `<div class="result-summary ${result.decision}">${result.decision === "pass" ? "规则检查通过，可生成航线" : result.decision === "warning" ? "存在软约束，需人工确认" : "存在硬约束，禁止生成航线"}</div>${result.items.length ? result.items.map((x) => `<div class="result-block ${x.level}"><strong>${x.rule_code}</strong><span>${x.message}</span><small>${x.action}${x.feature_ids?.length ? ` <button type="button" data-focus-buildings="${x.feature_ids.join(",")}">地图定位</button>` : ""}</small></div>`).join("") : '<div class="result-empty">没有发现冲突项</div>'}${terrainNote}`;
    document.querySelectorAll("[data-focus-buildings]").forEach((button) => button.addEventListener("click", () => {
      const ids = button.dataset.focusBuildings.split(",").filter(Boolean);
      if (!window.lpMap?.focusReferenceBuildings?.(ids)) button.textContent = "定位失败";
    }));
  } else {
    selectedRoute = result;
    renderMap();
    $("#resultBadge").textContent = "航线已生成";
    const terrain = result.terrain;
    const terrainLine = terrain?.available ? `<span>DEM合成演示：地形风险参考 ${terrain.terrain_risk} · 相对地形起伏 ${terrain.terrain_relief_m} 米；不代表离地净空</span>` : `<span>DEM地形：暂无参考数据</span>`;
    const candidates = (result.candidates || []).map((item) => `<div class="result-block ${item.feasible ? (item.name === result.name ? "pass" : "soft") : "blocked"}"><strong>${item.name}${item.name === result.name ? " · 已选" : ""}</strong><span>${item.feasible ? `评分 ${item.score} · 距离 ${item.distance_m} 米` : `不可行：${item.hard_conflicts.join("、")}`}</span><small>${item.terrain?.available ? `地形合成参考 ${item.terrain.terrain_risk} · 相对地形起伏 ${item.terrain.terrain_relief_m}m · 非离地净空` : "暂无DEM参考"}${item.soft_conflicts?.length ? ` · 软约束 ${item.soft_conflicts.join("、")}` : ""}</small></div>`).join("");
    $("#resultContent").innerHTML = `<div class="route-result"><strong>${result.name}</strong><span>策略：${result.strategy || "direct"} · 距离 ${result.distance_m} 米 · 预计 ${result.duration_s} 秒</span><span>风险等级：${result.risk_level}</span>${terrainLine}</div><div class="subhead">候选航线评分</div>${candidates}`;
    const missionResponse = await apiFetch(`/api/missions/${id}`);
    const mission = await missionResponse.json();
    const plannedRoute = mission.routes?.find((item) => Number(item.id) === Number(result.id));
    if (plannedRoute) {
      const latestDecision = (mission.route_decisions || []).find((item) => Number(item.route_id) === Number(plannedRoute.id));
      const adopted = Number(mission.selected_route_id) === Number(plannedRoute.id) && latestDecision?.decision === "adopted";
      const actions = ["admin", "dispatcher"].includes(currentRole) ? `<div class="route-review-actions"><label>决策理由<input type="text" maxlength="500" required data-route-reason="${plannedRoute.id}" placeholder="填写采用或退回理由"></label><div><button type="button" data-route-decision="adopt" data-route-id="${plannedRoute.id}">采用航线</button><button type="button" data-route-decision="return" data-route-id="${plannedRoute.id}">退回修改</button></div></div>` : "";
      $("#resultContent").insertAdjacentHTML("beforeend", `<article class="route-review ${adopted ? "is-adopted" : ""}"><div class="route-review-head"><strong>${escapeHtml(plannedRoute.name)}</strong><span>${adopted ? "当前已采用" : "待人工复核"}</span></div><span>${Number(plannedRoute.distance_m).toFixed(1)} 米 · ${Number(plannedRoute.duration_s).toFixed(1)} 秒</span>${actions}</article>`);
      bindRouteDecisionButtons(id);
    }
  }
}

function bindRouteDecisionButtons(missionId) {
  document.querySelectorAll("[data-route-decision]").forEach((button) => {
    button.onclick = async () => {
      const reasonInput = document.querySelector(`[data-route-reason="${button.dataset.routeId}"]`);
      const reason = reasonInput?.value.trim();
      if (!reason) {
        reasonInput?.focus();
        if (reasonInput) reasonInput.setCustomValidity("请填写决策理由");
        reasonInput?.reportValidity();
        return;
      }
      reasonInput?.setCustomValidity("");
      button.disabled = true;
      const response = await apiFetch(`/api/missions/${missionId}/routes/${button.dataset.routeId}/${button.dataset.routeDecision}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reason }) });
      const result = await response.json();
      if (!response.ok) {
        button.disabled = false;
        return showError(result);
      }
      await bootstrap();
      $("#resultBadge").textContent = ({ adopted: "航线已采用", returned: "已退回修改", revoked: "采用已撤销" }[result.decision] || "决策已记录");
    };
  });
}

async function startFlight(id) {
  const response = await apiFetch(`/api/missions/${id}/flight/start`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  const result = await response.json();
  if (!response.ok) return showError(result);
  if (selectedMissionId === id) await loadTrackReplay(id);
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
    if (selectedMissionId === id) await loadTrackReplay(id);
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
  $("#eventList").innerHTML = events.length ? events.map((event) => `<div class="event-row ${event.severity === "critical" ? "severity-critical" : "severity-warning"}"><strong>${event.event_type}</strong><span>${event.message}</span><small>${event.status}</small>${event.status === "open" ? `<button data-replan="${id}" data-event="${event.id}">生成重规划</button><button data-resolve="${event.id}">标记已处置</button>` : ""}</div>`).join("") : "";
  document.querySelectorAll("[data-replan]").forEach((button) => button.onclick = () => proposeReplan(button.dataset.replan, button.dataset.event));
  document.querySelectorAll("[data-resolve]").forEach((button) => button.onclick = async () => { await apiFetch(`/api/events/${button.dataset.resolve}/resolve`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); loadEvents(id); });
}

async function proposeReplan(missionId, eventId) {
  const response = await apiFetch(`/api/missions/${missionId}/replan`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ event_id: Number(eventId) }) });
  const result = await response.json();
  if (!response.ok) return showError(result);
  $("#resultBadge").textContent = "待人工确认";
  $("#resultContent").innerHTML = `<div class="route-result"><strong>${result.reason}</strong><span>距离 ${result.distance_m} 米 · 预计 ${result.duration_s} 秒</span><button data-confirm-replan="${result.id}" data-mission="${missionId}">确认采用该方案</button></div>`;
  bindReplanButtons(missionId);
}

function bindReplanButtons(missionId) {
  document.querySelectorAll("[data-confirm-replan]").forEach((button) => button.onclick = async () => {
    const response = await apiFetch(`/api/replans/${button.dataset.confirmReplan}/confirm`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    const result = await response.json();
    if (!response.ok) return showError(result);
    $("#resultBadge").textContent = "重规划已确认";
    $("#resultContent").innerHTML = `<div class="result-summary pass">已由 ${result.actor_username} 确认采用重规划方案 #${result.id}</div>`;
    loadEvents(missionId);
  });
}

async function loadTimeline(id) {
  const response = await apiFetch(`/api/missions/${id}/timeline`);
  if (!response.ok) return;
  const result = await response.json();
  const timeline = result.timeline || [];
  if (!timeline.length) return;
  $("#resultContent").insertAdjacentHTML("beforeend", `<div class="subhead">运行时间线</div><div class="timeline-list">${timeline.map((item) => `<div class="timeline-row"><strong>${item.action}</strong><span>${item.detail?.message || item.detail?.reason || item.detail?.decision || "状态变更"}</span><small>${item.at}${item.actor ? ` · ${item.actor}` : ""}</small></div>`).join("")}</div>`);
}

async function bootstrap() {
  const identityResponse = await apiFetch("/api/auth/me");
  if (identityResponse.status === 401) throw new Error("401 未登录");
  if (identityResponse.ok) {
    const identity = await identityResponse.json();
    currentRole = identity.role;
    $("#currentUser").textContent = `${identity.username} · ${identity.role}`;
    $("#logoutButton").hidden = false;
    $("#loginGate").style.display = "none";
  }
  const response = await apiFetch("/api/bootstrap");
  if (response.status === 401) throw new Error("401 未登录");
  if (!response.ok) throw new Error("初始化数据加载失败");
  render(await response.json());
  if (selectedMissionId) await showDetails(selectedMissionId);
  $("#health").textContent = "● 服务正常 · SQLite 数据已加载";
}

function placeFeatureCoordinates(feature) {
  const coordinates = [];
  const visit = (value) => {
    if (!Array.isArray(value)) return;
    if (value.length >= 2 && Number.isFinite(Number(value[0])) && Number.isFinite(Number(value[1]))) coordinates.push([Number(value[0]), Number(value[1])]);
    else value.forEach(visit);
  };
  visit(feature.geometry?.coordinates);
  if (!coordinates.length) return null;
  return coordinates.length === 1 ? coordinates[0] : [coordinates.reduce((sum, point) => sum + point[0], 0) / coordinates.length, coordinates.reduce((sum, point) => sum + point[1], 0) / coordinates.length];
}

function searchLocalPlaces(query) {
  const normalized = query.trim().toLocaleLowerCase();
  if (normalized.length < 2) return [];
  const features = window.lpMap?.adapter?.referenceGeographyData || [];
  const matches = [];
  for (const feature of features) {
    const properties = feature.properties || {};
    const name = String(properties.name || properties["name:zh"] || properties.official_name || "").trim();
    if (!name.toLocaleLowerCase().includes(normalized)) continue;
    const coordinates = placeFeatureCoordinates(feature);
    if (!coordinates || coordinates[0] < 105 || coordinates[0] > 110 || coordinates[1] < 28 || coordinates[1] > 32) continue;
    matches.push({ feature, name, coordinates, kind: feature.geometry?.type === "Point" ? "点位" : "范围/线状要素中心（近似）" });
    if (matches.length >= 12) break;
  }
  return matches;
}

function renderPlaceResults(query) {
  const target = $("#placeSearchResults");
  target.replaceChildren();
  if (query.trim().length < 2) { target.textContent = "请输入至少 2 个字符"; return; }
  const matches = searchLocalPlaces(query);
  if (!matches.length) { target.textContent = "本地参考数据中没有匹配结果；可继续手动填写坐标。"; return; }
  matches.forEach((match) => {
    const row = document.createElement("div"); row.className = "place-search-result";
    const info = document.createElement("div");
    const title = document.createElement("strong"); title.textContent = match.name;
    const meta = document.createElement("small"); meta.textContent = `OSM 公开参考 · ${match.kind} · ${match.coordinates[0].toFixed(6)}, ${match.coordinates[1].toFixed(6)}`;
    info.append(title, meta);
    const actions = document.createElement("div"); actions.className = "place-search-actions";
    const focus = document.createElement("button"); focus.type = "button"; focus.textContent = "定位"; focus.setAttribute("aria-label", `在地图定位：${match.name}`);
    focus.addEventListener("click", () => { if (!window.lpMap?.focusPoint?.(match.coordinates)) $("#formMessage").textContent = "当前地图不支持地点定位，请手动填写坐标。"; });
    actions.append(focus);
    for (const role of ["start", "end"]) {
      const button = document.createElement("button"); button.type = "button"; button.textContent = role === "start" ? "设为起点" : "设为终点";
      button.addEventListener("click", () => {
        const form = $("#missionForm");
        form.elements[`${role}_lng`].value = match.coordinates[0].toFixed(6);
        form.elements[`${role}_lat`].value = match.coordinates[1].toFixed(6);
        $("#formMessage").textContent = `${role === "start" ? "起点" : "终点"}已设为“${match.name}”的参考坐标；请核对位置后再创建任务。`;
        window.lpMap?.focusPoint?.(match.coordinates);
      });
      actions.append(button);
    }
    const via = document.createElement("button"); via.type = "button"; via.textContent = "加入途经点";
    via.addEventListener("click", () => {
      if (missionViaPoints.length >= 12) { $("#formMessage").textContent = "途经点最多 12 个。"; return; }
      const sourceId = String(match.feature.id || match.feature.properties?.osm_way_id || "");
      if (missionViaPoints.some((point) => point.source_id && point.source_id === sourceId)) { $("#formMessage").textContent = "该参考要素已加入途经点。"; return; }
      missionViaPoints.push({ name: match.name, longitude: match.coordinates[0], latitude: match.coordinates[1], source: "openstreetmap_reference", source_id: sourceId });
      renderMissionViaPoints();
      $("#formMessage").textContent = `已添加途经点“${match.name}”；保存任务后会进入航线规划。`;
    });
    actions.append(via);
    row.append(info, actions); target.append(row);
  });
}

function renderMissionViaPoints() {
  const input = $("#missionForm input[name='via_points_json']");
  const target = $("#missionViaPointList");
  input.value = JSON.stringify(missionViaPoints);
  target.replaceChildren();
  if (!missionViaPoints.length) { target.textContent = "未添加途经点"; return; }
  missionViaPoints.forEach((point, index) => {
    const row = document.createElement("div"); row.className = "mission-via-point";
    const name = document.createElement("span"); name.textContent = `${index + 1}. ${point.name} · ${point.longitude.toFixed(6)}, ${point.latitude.toFixed(6)}`;
    const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "移除"; remove.setAttribute("aria-label", `移除途经点：${point.name}`);
    remove.addEventListener("click", () => { missionViaPoints.splice(index, 1); renderMissionViaPoints(); });
    row.append(name, remove); target.append(row);
  });
}

function renderElevationProfile(profile) {
  const target = $("#elevationProfile");
  target.replaceChildren();
  const samples = (profile.samples || []).filter((sample) => Number.isFinite(Number(sample.elevation_m)));
  if (!profile.available || !samples.length) { target.textContent = "公开服务未返回完整采样。高程数据不足，不能用于净空判断。"; return; }
  const elevations = samples.map((sample) => Number(sample.elevation_m));
  const minimum = Math.min(...elevations); const maximum = Math.max(...elevations);
  const summary = document.createElement("div"); summary.className = "elevation-profile-summary";
  summary.textContent = `${samples.length} 个沿线采样点 · ${minimum.toFixed(1)}–${maximum.toFixed(1)} m · 来源标称 ${profile.source_resolution_m ? `${profile.source_resolution_m}m` : "分辨率未知"} · 垂直基准未声明`;
  const chart = document.createElement("div"); chart.className = "elevation-chart"; chart.setAttribute("role", "img"); chart.setAttribute("aria-label", `公开参考高程剖面，${samples.length}个采样点，最低${minimum.toFixed(1)}米，最高${maximum.toFixed(1)}米`);
  samples.forEach((sample, index) => {
    const bar = document.createElement("span"); bar.className = "elevation-chart-sample";
    const ratio = maximum === minimum ? 0.5 : (Number(sample.elevation_m) - minimum) / (maximum - minimum);
    bar.style.height = `${Math.max(14, 18 + ratio * 72)}%`;
    bar.title = `点 ${index + 1} · ${Number(sample.elevation_m).toFixed(1)} m · ${Number(sample.longitude).toFixed(5)}, ${Number(sample.latitude).toFixed(5)}`;
    chart.append(bar);
  });
  const endpoints = document.createElement("div"); endpoints.className = "elevation-chart-endpoints";
  const start = document.createElement("span"); start.textContent = `起点 ${elevations[0].toFixed(1)} m`;
  const end = document.createElement("span"); end.textContent = `终点 ${elevations.at(-1).toFixed(1)} m`;
  endpoints.append(start, end);
  const source = document.createElement("a"); source.href = profile.source_url; source.target = "_blank"; source.rel = "noopener noreferrer"; source.textContent = profile.source;
  const boundary = document.createElement("small"); boundary.className = "elevation-profile-boundary"; boundary.textContent = `${profile.data_boundary}；${profile.source_resolution_note || "数据源未声明分辨率"}；垂直基准未声明，不用于安全放行。${profile.usage_terms ? ` ${profile.usage_terms}` : ""}`;
  target.append(summary, chart, endpoints, source, boundary);
}

async function queryElevationProfile() {
  const target = $("#elevationProfile"); const missionId = selectedMissionId;
  if (!missionId) { target.textContent = "请先选择任务。"; return; }
  target.textContent = "正在查询公开高程参考…";
  const response = await apiFetch(`/api/missions/${encodeURIComponent(missionId)}/elevation-profile`, { cache: "no-store" });
  const result = await response.json();
  if (!response.ok) { target.textContent = `${result.message || "公开高程服务不可用"}；现有离线高程仅为合成演示数据。`; return; }
  renderElevationProfile(result);
}

const dialog = $("#missionDialog");
const mapContext = () => ({
  data: platformData,
  selectedRoute,
  selectedMissionId,
  selectedVehicleId: platformData?.missions?.find((item) => item.id === selectedMissionId)?.vehicle_id,
  selectedMapObject,
  replayTrack: trackReplay,
  onVehicleClick: (id) => { const vehicle = platformData.vehicles.find((item) => item.id === id); if (vehicle) displayMapObject("vehicle", vehicle); },
  onSpatialClick: (feature) => { if (feature) displayMapObject("spatial", feature); },
});

$("#mapZoomIn").onclick = () => window.lpMap?.setZoom((window.lpMap.adapter?.map?.getZoom() || window.lpMap.state.zoom || 1) + .5, mapContext());
$("#mapZoomOut").onclick = () => window.lpMap?.setZoom((window.lpMap.adapter?.map?.getZoom() || window.lpMap.state.zoom || 1) - .5, mapContext());
$("#mapReset").onclick = () => window.lpMap?.reset(mapContext());
$("#queryElevationProfile").onclick = () => { queryElevationProfile().catch(() => { $("#elevationProfile").textContent = "公开高程服务暂不可用；现有离线高程仅为合成演示数据。"; }); };
$("#altitudeFilter").onchange = (event) => { const labels = { all: "全部高度", "0-60": "0–60 m", "60-120": "60–120 m", "120-300": "120–300 m", "300+": "300 m 以上" }; const readout = $("#altitudeLayerReadout"); if (readout) readout.textContent = `当前高度层：${labels[event.target.value] || "未知"}`; window.lpMap?.setFilters({ altitude: event.target.value }, mapContext()); };
$("#openFacilityManagement").onclick = () => $("#facilityManagementDialog").showModal();
$("#closeFacilityManagement").onclick = () => $("#facilityManagementDialog").close();
$("#newMission").onclick = () => { missionViaPoints = []; renderMissionViaPoints(); $("#placeSearchInput").value = ""; $("#placeSearchResults").replaceChildren(); $("#formMessage").textContent = ""; dialog.showModal(); };
$("#placeSearchSubmit").onclick = () => renderPlaceResults($("#placeSearchInput").value);
$("#placeSearchInput").addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); renderPlaceResults(event.currentTarget.value); } });
$("#closeDialog").onclick = () => dialog.close();
$("#cancelDialog").onclick = () => dialog.close();
$("#missionForm").onsubmit = async (event) => {
  event.preventDefault();
  const response = await apiFetch("/api/missions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))) });
  const result = await response.json();
  if (!response.ok) { $("#formMessage").textContent = result.message; return; }
  platformData.missions.unshift(result); selectedMissionId = result.id; render(platformData); dialog.close(); showDetails(result.id);
  $("#health").textContent = `● 任务 ${result.id} 已保存并写入审计日志`;
};

$("#loginForm").onsubmit = async (event) => {
  event.preventDefault();
  const response = await fetch("/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))) });
  const result = await response.json();
  if (!response.ok) { $("#loginMessage").textContent = result.message; return; }
  localStorage.setItem("lp_token", result.token);
  currentRole = result.role;
  $("#currentUser").textContent = `${result.username} · ${result.role}`;
  $("#logoutButton").hidden = false;
  $("#loginGate").style.display = "none";
  try {
    await bootstrap();
  } catch (error) {
    if (error.message.includes("401")) localStorage.removeItem("lp_token");
    $("#loginGate").style.display = "grid";
    $("#loginMessage").textContent = error.message;
    $("#health").textContent = `● 身份初始化失败 · ${error.message}`;
  }
};
$("#logoutButton").onclick = async () => { await apiFetch("/api/auth/logout", { method: "POST" }); localStorage.removeItem("lp_token"); $("#loginGate").style.display = "grid"; $("#logoutButton").hidden = true; };
if (localStorage.getItem("lp_token")) {
  bootstrap().catch((error) => { if (error.message.includes("401")) { localStorage.removeItem("lp_token"); $("#loginGate").style.display = "grid"; } $("#health").textContent = `● 服务不可用 · ${error.message}`; });
} else {
  $("#loginGate").style.display = "grid";
  $("#health").textContent = "● 等待身份认证";
}
