const { test, expect } = require("@playwright/test");
const path = require("node:path");
const screenshot = (name) => path.resolve(__dirname, "../../artifacts/sprint-m3", name);
test("MapLibre workspace is focused and readable", async ({ page }) => {
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") pageErrors.push(message.text()); });
  await page.goto("/");
  if (await page.locator("#loginGate").isVisible()) {
    await page.locator("#loginForm input[name='username']").fill("admin");
    await page.locator("#loginForm input[name='password']").fill(process.env.E2E_PASSWORD || "admin123");
    await page.locator("#loginForm button[type='submit']").click();
  }
  await page.waitForTimeout(4000);
  await expect(page.locator("#health")).toContainText("服务正常");
  await expect(page.locator("#mapCanvas")).toBeVisible();
  await expect(page.locator("#maplibreRouteOverlay polyline").or(page.locator("#mapCanvas svg polyline"))).toHaveCount(2);
  await expect(page.locator("#maplibreRouteOverlay .route-overlay-primary").or(page.locator("#mapCanvas svg .route-primary"))).toHaveCount(1);
  await expect(page.locator("#maplibreRouteOverlay .route-overlay-backup").or(page.locator("#mapCanvas svg .route-backup"))).toHaveCount(0);
  await expect(page.locator("#mapModeStatus")).toContainText("data synced");
  await expect(page.locator("#mapModeStatus")).toContainText("OpenMapTiles style not configured");
  expect(await page.evaluate(() => window.lpMap?.adapter?.kind)).toBe("maplibre");
  expect(await page.evaluate(() => Boolean(window.lpMap?.adapter?.map?.getSource("lp-geography") && window.lpMap.adapter.map.getLayer("lp-reference-roads") && window.lpMap.adapter.map.getLayer("lp-reference-waterways")))).toBeTruthy();
  await expect.poll(() => page.evaluate(() => window.lpMap.adapter.referenceGeographyLoaded)).toBeTruthy();
  expect(await page.evaluate(() => window.lpMap.adapter.map.getSource("lp-geography")._data.features.length)).toBeGreaterThan(100);
  expect(await page.evaluate(() => window.lpMap.adapter.map.queryRenderedFeatures({ layers: ["lp-reference-roads"] }).length)).toBeGreaterThan(20);
  expect(await page.evaluate(() => {
    const adapter = window.lpMap.adapter; const item = adapter.markers.find((marker) => marker.element.classList.contains("vehicle"));
    if (!item) return false;
    const point = adapter.map.project(item.coordinates); const bounds = document.querySelector("#maplibreViewport").getBoundingClientRect(); const rect = item.element.getBoundingClientRect();
    return Math.abs(rect.left + rect.width / 2 - bounds.left - point.x) < 2 && Math.abs(rect.top + rect.height / 2 - bounds.top - point.y) < 2;
  })).toBeTruthy();
  expect(await page.evaluate(() => ["lp-primary-route", "lp-backup-route", "lp-actual-track", "lp-risk-segments"].every((id) => !window.lpMap.adapter.map.getLayer(id)))).toBeTruthy();
  await expect(page.locator("#mapCanvas .map-attribution")).toHaveAttribute("href", "https://www.openstreetmap.org/copyright");
  await expect(page.locator("#mapObjectSummary button").first()).toBeVisible();
  await expect(page.locator("#mapCanvas .map-callout")).toHaveCount(0);
  expect(await page.locator("#maplibreViewport .maplibre-marker:not(.cluster)").first().evaluate((node) => getComputedStyle(node).backgroundColor)).toBe("rgba(0, 0, 0, 0)");
  expect(await page.locator("#mapObjectSummary").evaluate((node) => node.scrollWidth <= node.clientWidth)).toBeTruthy();
  await expect(page.locator("#missionList [data-mission-card].is-selected")).toBeInViewport();
  expect(await page.evaluate(() => {
    const list = document.querySelector("#missionList").getBoundingClientRect();
    const selected = document.querySelector("#missionList [data-mission-card].is-selected").getBoundingClientRect();
    return Math.abs(selected.top - list.top) < 8;
  })).toBeTruthy();
  await expect(page.locator("#missionList")).not.toContainText("API smoke");
  await expect(page.locator("#missionList")).not.toContainText("联调测试");
  await expect(page.locator("#metrics")).toContainText("任务2项");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  const layout = await page.evaluate(() => {
    const workspace = document.querySelector(".map-workspace").getBoundingClientRect();
    const sidebar = document.querySelector(".map-sidebar").getBoundingClientRect();
    const map = document.querySelector("#mapCanvas").getBoundingClientRect();
    const mapPanel = document.querySelector(".map-panel").getBoundingClientRect();
    const nextSection = document.querySelector(".lower-grid").getBoundingClientRect();
    const mission = document.querySelector(".mission-panel").getBoundingClientRect();
    return { mapRatio: map.width / workspace.width, mapWidth: map.width, sidebarWidth: sidebar.width, sidebarHeight: sidebar.height, mapHeight: map.height, workspaceBottom: workspace.bottom, sidebarBottom: sidebar.bottom, mapPanelBottom: mapPanel.bottom, missionBottom: mission.bottom, nextSectionTop: nextSection.top, verticalGap: nextSection.top - mapPanel.bottom, sidebarColumns: getComputedStyle(document.querySelector(".map-sidebar")).gridTemplateColumns, boundaryVisible: document.querySelector(".map-data-boundary").getBoundingClientRect().bottom <= window.innerHeight };
  });
  console.log("desktop map layout", JSON.stringify(layout));
  await page.screenshot({ path: screenshot("maplibre-1366x768.png"), fullPage: false });
  expect(layout.sidebarWidth).toBeGreaterThanOrEqual(300);
  expect(layout.mapWidth).toBeGreaterThanOrEqual(560);
  expect(layout.sidebarColumns.split(" ")).toHaveLength(2);
  expect(layout.verticalGap).toBeLessThanOrEqual(150);
  expect(layout.mapRatio).toBeGreaterThanOrEqual(0.54);
  expect(layout.mapHeight).toBeGreaterThanOrEqual(260);
  expect(layout.boundaryVisible).toBeTruthy();
  expect(await page.locator("#mapTimelineTrack .timeline-item").first().evaluate((node) => { const box = node.getBoundingClientRect(); return box.top >= 0 && box.bottom <= window.innerHeight; })).toBeTruthy();
  expect(pageErrors).toEqual([]);
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.screenshot({ path: screenshot("maplibre-1024x768.png"), fullPage: false });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator("#mapCanvas canvas")).toBeVisible();
  await page.screenshot({ path: screenshot("maplibre-390x844.png"), fullPage: false });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});

test("map controls update visible state", async ({ page }) => {
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") pageErrors.push(message.text()); });
  await page.goto("/?map=maplibre");
  if (await page.locator("#loginGate").isVisible()) {
    await page.locator("#loginForm input[name='username']").fill("admin");
    await page.locator("#loginForm input[name='password']").fill(process.env.E2E_PASSWORD || "admin123");
    await page.locator("#loginForm button[type='submit']").click();
  }
  await expect(page.locator("#mapModeStatus")).toContainText("data synced");
  await page.evaluate(() => { const adapter = window.lpMap.adapter; adapter.map.setZoom(13); adapter.syncSources(); });
  await expect.poll(() => page.evaluate(() => window.lpMap.adapter.buildData().facilities.features.length)).toBeGreaterThan(0);
  expect(await page.evaluate(() => { const areas = window.lpMap.adapter.buildData().airspace.features; return areas.length > 0 && areas.every((feature) => feature.properties.asset_type === "restricted" && feature.properties.display_shape === "derived_circle"); })).toBeTruthy();
  await expect(page.locator("#routeWaypointList button").first()).toBeVisible();
  await page.locator("#routeWaypointList button").first().click();
  await expect.poll(() => page.locator("#maplibreRouteOverlay .route-overlay-primary").getAttribute("points").then((points) => points.trim().split(/\s+/).length)).toBeGreaterThan(3);
  await expect(page.locator("#routeWaypointList button[aria-pressed='true']")).toHaveCount(1);
  expect(await page.evaluate(() => {
    const adapter = window.lpMap.adapter; const feature = adapter.buildData().facilities.features.find((item) => item.properties.path_reference); const target = adapter.map.project(feature.geometry.coordinates); const points = document.querySelector("#maplibreRouteOverlay .route-overlay-primary").getAttribute("points").trim().split(/\s+/).map((pair) => pair.split(",").map(Number));
    return Math.min(...points.map(([x, y]) => Math.hypot(x - target.x, y - target.y))) < 1;
  })).toBeTruthy();
  await page.locator("#routeWaypointList button[aria-pressed='true']").click();
  await expect(page.locator("#routeWaypointList button[aria-pressed='true']")).toHaveCount(0);
  await page.evaluate(() => { const adapter = window.lpMap.adapter; adapter.map.setZoom(12); adapter.syncSources(); });
  await expect.poll(() => page.evaluate(() => window.lpMap.adapter.buildData().facilities.features.filter((feature) => ["facility", "facility_point"].includes(feature.properties.asset_type)).length)).toBe(0);
  await page.evaluate(() => { const adapter = window.lpMap.adapter; adapter.map.setZoom(10); adapter.syncSources(); });
  await expect.poll(() => page.evaluate(() => window.lpMap.adapter.buildData().facilities.features.length)).toBe(0);
  await page.evaluate(() => { const adapter = window.lpMap.adapter; adapter.map.setZoom(11); adapter.syncSources(); });
  await expect.poll(() => page.evaluate(() => window.lpMap.adapter.buildData().facilities.features.filter((feature) => feature.properties.asset_type === "route_reference_point").length)).toBe(30);
  await expect.poll(() => page.evaluate(() => window.lpMap.adapter.buildData().risks.features.filter((feature) => feature.properties.asset_type === "hazard").length)).toBe(24);
  await page.screenshot({ path: screenshot("maplibre-regional-points-zoom11-1366x768.png"), fullPage: false });
  expect(await page.evaluate(() => window.lpMap.adapter.buildData().airspace.features.every((feature) => feature.properties.asset_type === "restricted" && feature.properties.display_shape === "derived_circle"))).toBeTruthy();
  const taskButtons = page.locator("[data-select-mission]");
  await taskButtons.nth(1).click();
  await expect(taskButtons.nth(1)).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#mapMissionSummary")).toContainText("MS-");
  await expect(page.locator("#mapTimelineTrack .timeline-item")).toHaveCount(3);
  await expect(page.locator("#mapTimelineTrack")).toContainText("任务窗口");
  await expect(page.locator("#mapTimelineTrack")).toContainText("临时管制");
  await expect(page.locator("#dataRegister")).toContainText("DEM / 高程");
  await expect(page.locator("#dataRegister")).toContainText("建筑数据 · 未接入");
  await expect(page.locator("#terrainStatus")).toContainText("合成网格");
  await expect(page.locator("#altitudeLayerReadout")).toContainText("全部高度");
  await expect.poll(() => page.locator("#maplibreRouteOverlay polyline").count()).toBeGreaterThanOrEqual(2);
  const routeWidthBeforeZoom = Number(await page.locator("#maplibreRouteOverlay .route-overlay-primary").getAttribute("stroke-width"));
  await page.getByRole("button", { name: "放大地图" }).click();
  await page.locator("#altitudeFilter").selectOption("120-300");
  await expect(page.locator("#altitudeFilter")).toHaveValue("120-300");
  await expect(page.locator("#altitudeLayerReadout")).toContainText("120–300 m");
  await expect(page.locator("#mapTimelineTrack .timeline-item").first()).toHaveAttribute("data-time-state");
  await expect.poll(async () => Number(await page.locator("#maplibreRouteOverlay .route-overlay-primary").getAttribute("stroke-width"))).toBeGreaterThan(routeWidthBeforeZoom);
  const canvas = page.locator("#maplibreViewport canvas");
  const canvasBox = await canvas.boundingBox();
  const beforeDrag = await page.locator("#maplibreRouteOverlay polyline").first().getAttribute("points");
  await page.mouse.move(canvasBox.x + canvasBox.width / 2, canvasBox.y + canvasBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(canvasBox.x + canvasBox.width / 2 + 70, canvasBox.y + canvasBox.height / 2 + 25, { steps: 5 });
  await page.mouse.up();
  await expect.poll(() => page.locator("#maplibreRouteOverlay polyline").first().getAttribute("points")).not.toBe(beforeDrag);
  await page.getByRole("button", { name: "重置地图视图" }).click();
  await expect(page.locator("#mapModeStatus")).toContainText("data synced");
  const layer = page.locator("#layerList input[type='checkbox']").first();
  await layer.uncheck();
  await expect(layer).not.toBeChecked();
  await page.locator("#mapObjectSummary button").nth(2).click();
  await expect(page.locator("#resultBadge")).toContainText("飞行器");
  await taskButtons.first().click();
  await expect(taskButtons.first()).toHaveAttribute("aria-pressed", "true");
  await page.locator("#mapObjectSummary button").filter({ hasText: "低空运行服务中心" }).click();
  await expect(page.locator("#resultBadge")).toContainText("空间对象");
  await expect(page.locator("#resultContent")).toHaveAttribute("data-selected-object-type", "spatial");
  await expect(page.locator("#maplibreViewport .maplibre-marker.is-selected")).toHaveCount(1);
  await page.evaluate(() => { const adapter = window.lpMap.adapter; adapter.map.setZoom(13); adapter.syncSources(); });
  await expect(page.locator("#routeWaypointList button").first()).toBeVisible();
  await page.locator("#routeWaypointList button").first().click();
  await expect.poll(() => page.locator("#maplibreRouteOverlay .route-overlay-primary").getAttribute("points").then((points) => points.trim().split(/\s+/).length)).toBeGreaterThan(3);
  await page.screenshot({ path: screenshot("maplibre-route-reference-selected-1366x768.png"), fullPage: false });
  expect(await page.locator("#maplibreViewport .maplibre-marker:not([hidden])").evaluateAll((nodes) => nodes.every((node, index) => nodes.slice(index + 1).every((other) => { const a = node.getBoundingClientRect(); const b = other.getBoundingClientRect(); return a.right <= b.left || a.left >= b.right || a.bottom <= b.top || a.top >= b.bottom; })))).toBeTruthy();
  await page.locator("#mapObjectSummary button").filter({ hasText: "高风险障碍物参考点" }).click();
  await expect(page.locator("#resultContent")).toHaveAttribute("data-selected-risk", "true");
  await expect(page.locator("#resultContent")).toContainText("需人工核验");
  await expect(page.locator("#resultContent")).toContainText("85 m");
  expect(await page.evaluate(() => {
    const viewport = document.querySelector("#maplibreViewport"); const bounds = viewport.getBoundingClientRect();
    const segments = [...document.querySelectorAll("#maplibreRouteOverlay polyline")].flatMap((line) => { const points = line.getAttribute("points").trim().split(/\s+/).map((pair) => pair.split(",").map(Number)); return points.slice(1).map((point, index) => [points[index], point]); });
    const crosses = (segment, box) => { const [[x1, y1], [x2, y2]] = segment; const dx = x2 - x1; const dy = y2 - y1; const p = [-dx, dx, -dy, dy]; const q = [x1 - box.left, box.right - x1, y1 - box.top, box.bottom - y1]; let low = 0; let high = 1; for (let i = 0; i < 4; i += 1) { if (p[i] === 0) { if (q[i] < 0) return false; } else { const t = q[i] / p[i]; if (p[i] < 0) low = Math.max(low, t); else high = Math.min(high, t); if (low > high) return false; } } return true; };
    return [...document.querySelectorAll("#maplibreViewport .maplibre-marker:not([hidden]):not(.cluster):not(.vehicle):not(.is-selected)")].every((node) => { const rect = node.getBoundingClientRect(); const box = { left: rect.left - bounds.left, right: rect.right - bounds.left, top: rect.top - bounds.top, bottom: rect.bottom - bounds.top }; return !segments.some((segment) => crosses(segment, box)); });
  })).toBeTruthy();
  const facilityPoint = await page.evaluate(() => {
    const feature = window.lpMap.adapter.buildData().facilities.features.find((item) => item.properties.name === "低空运行服务中心");
    const projected = window.lpMap.adapter.map.project(feature.geometry.coordinates);
    return { x: projected.x, y: projected.y };
  });
  const mapBox = await page.locator("#maplibreViewport canvas").boundingBox();
  await page.mouse.click(mapBox.x + facilityPoint.x, mapBox.y + facilityPoint.y);
  await expect(page.locator("#resultContent")).toHaveAttribute("data-selected-object-type", "spatial");
  const mission = page.locator("[data-check]").first();
  await mission.click();
  await expect(page.locator("#resultBadge")).not.toContainText("等待操作");
  await expect(page.locator("#resultContent")).toContainText("DEM参考");
  await page.locator("[data-plan]").first().click();
  await expect(page.locator("#resultContent")).toContainText("航线");
  await page.getByRole("button", { name: "设施管理" }).click();
  await expect(page.locator("#facilityManagementDialog")).toBeVisible();
  await page.locator("#facilityForm [name='facility_id']").fill("E2E-FAC-M0-001");
  await page.locator("#facilityForm [name='name']").fill("M0隔离测试设施");
  await page.locator("#facilityForm [name='longitude']").fill("107.751");
  await page.locator("#facilityForm [name='latitude']").fill("30.701");
  const facilityResponsePromise = page.waitForResponse((response) => response.url().endsWith("/api/facilities") && response.request().method() === "POST");
  await page.locator("#facilityForm button[type='submit']").click();
  const facilityResponse = await facilityResponsePromise;
  const createdFacility = await facilityResponse.json();
  expect(facilityResponse.ok(), JSON.stringify(createdFacility)).toBeTruthy();
  expect(createdFacility.facility_id).toBe("E2E-FAC-M0-001");
  await expect(page.locator("#facilityAdminList")).toContainText("E2E-FAC-M0-001");
  await page.locator("#closeFacilityManagement").click();
  await expect(page.locator("#facilityManagementDialog")).not.toBeVisible();
  await page.getByRole("button", { name: "设施管理" }).click();
  const firstFacility = page.locator("#facilityAdminList .facility-admin-row").first();
  const facilityId = await firstFacility.locator("[data-facility-maintain]").getAttribute("data-facility-maintain");
  await firstFacility.locator("[data-facility-maintain]").click();
  await expect(page.locator(`#facilityAdminList [data-facility-disable='${facilityId}']`).locator("../..")).toContainText("maintenance");
  await page.locator(`#facilityAdminList [data-facility-disable='${facilityId}']`).click();
  await expect(page.locator("#facilityAdminList")).toContainText("disabled");
  await page.locator("#closeFacilityManagement").click();
  expect(pageErrors).toEqual([]);
  await page.locator("#mapTimelineTrack .timeline-item").first().click();
  await expect(page.locator("#mapTimelineTrack .timeline-item.is-active")).toHaveCount(1);
});

test("local place search can confirm and populate a mission endpoint", async ({ page }) => {
  await page.goto("/?map=maplibre");
  if (await page.locator("#loginGate").isVisible()) {
    await page.locator("#loginForm input[name='username']").fill("admin");
    await page.locator("#loginForm input[name='password']").fill(process.env.E2E_PASSWORD || "admin123");
    await page.locator("#loginForm button[type='submit']").click();
  }
  await expect.poll(() => page.evaluate(() => Boolean(window.lpMap?.adapter?.referenceGeographyLoaded && window.lpMap.adapter.referenceGeographyData.some((item) => item.properties?.name)))).toBeTruthy();
  const place = await page.evaluate(() => {
    const features = window.lpMap.adapter.referenceGeographyData;
    const feature = features.find((item) => item.properties?.name);
    return { name: feature.properties.name, coordinates: feature.geometry.coordinates };
  });
  await page.locator("#newMission").click();
  await page.locator("#placeSearchInput").fill(place.name);
  await page.locator("#placeSearchSubmit").click();
  await expect(page.locator("#placeSearchResults")).toContainText(place.name);
  const displayedCoordinates = await page.locator(".place-search-result small").first().innerText();
  const coordinateMatch = displayedCoordinates.match(/(-?\d+\.\d+),\s*(-?\d+\.\d+)/);
  expect(coordinateMatch).not.toBeNull();
  await page.locator(".place-search-result").first().getByRole("button", { name: "设为起点" }).click();
  await expect(page.locator("#missionForm input[name='start_lng']")).toHaveValue(Number(coordinateMatch[1]).toFixed(6));
  await expect(page.locator("#missionForm input[name='start_lat']")).toHaveValue(Number(coordinateMatch[2]).toFixed(6));
  await page.locator(".place-search-result").first().getByRole("button", { name: "加入途经点" }).click();
  await expect(page.locator("#missionViaPointList .mission-via-point")).toHaveCount(1);
  expect(JSON.parse(await page.locator("#missionForm input[name='via_points_json']").inputValue())).toHaveLength(1);
  await expect(page.locator("#formMessage")).toContainText("进入航线规划");
  await expect.poll(() => page.evaluate(() => window.lpMap.adapter.map.getZoom())).toBeGreaterThanOrEqual(13);
  expect(await page.locator("#placeSearchResults").evaluate((node) => node.innerText.includes("OSM 公开参考"))).toBeTruthy();
  await expect(page.locator("#missionForm button[type='submit']")).toBeInViewport({ ratio: 1 });
  await page.screenshot({ path: screenshot("local-place-search-1366x768.png"), fullPage: false });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
  await page.screenshot({ path: screenshot("local-place-search-390x844.png"), fullPage: false });
  await page.locator("#missionForm button[type='submit']").scrollIntoViewIfNeeded();
  await expect(page.locator("#missionForm button[type='submit']")).toBeInViewport();
  await page.setViewportSize({ width: 1366, height: 768 });
  await page.locator("#missionForm input[name='id']").fill("MS-PLACE-QA-01");
  await page.locator("#missionForm button[type='submit']").click();
  await expect(page.locator("#missionDialog")).not.toBeVisible();
  const persisted = await page.evaluate(async () => {
    const token = localStorage.getItem("lp_token");
    const response = await fetch("/api/missions/MS-PLACE-QA-01", { headers: { Authorization: `Bearer ${token}` } });
    return response.json();
  });
  expect(JSON.parse(persisted.via_points_json)).toHaveLength(1);
  expect(JSON.parse(persisted.via_points_json)[0].source).toBe("openstreetmap_reference");
  const missionCard = page.locator('[data-mission-card="MS-PLACE-QA-01"]');
  await missionCard.locator("[data-check]").click();
  await expect.poll(() => page.locator("#resultBadge").innerText()).toMatch(/pass|warning/);
  await expect(page.locator("#resultContent")).toContainText("未接入具备来源、许可与覆盖审计的建筑障碍物数据");
  await expect(page.locator("#resultContent")).toContainText("合成演示数据，不可用于净空结论");
  await expect(page.locator("#resultContent")).not.toContainText("最小净空");
  await missionCard.locator("[data-plan]").click();
  await expect.poll(() => page.evaluate(() => window.lpMap.adapter.context.selectedRoute?.points?.length || 0)).toBe(3);
  await expect.poll(() => page.evaluate(() => window.lpMap.adapter.context.selectedRoute?.name)).toBe("主航线-参考点规划");
  const planned = await page.evaluate(() => window.lpMap.adapter.context.selectedRoute.points);
  expect(Number(planned[1][0])).toBe(Number(JSON.parse(persisted.via_points_json)[0].longitude));
  expect(Number(planned[1][1])).toBe(Number(JSON.parse(persisted.via_points_json)[0].latitude));
});

test("public elevation profile is attributed and shows explicit upstream failures", async ({ page }) => {
  let failUpstream = false;
  await page.route("**/api/missions/*/elevation-profile", (route) => {
    if (failUpstream) return route.fulfill({ status: 503, json: { code: "ELEVATION_SERVICE_UNAVAILABLE", message: "公开高程服务暂不可用" } });
    return route.fulfill({ json: {
      available: true,
      samples: [
        { longitude: 107.74, latitude: 30.64, elevation_m: 440 },
        { longitude: 107.76, latitude: 30.65, elevation_m: 458 },
        { longitude: 107.78, latitude: 30.66, elevation_m: 451 },
      ],
      source: "Open-Meteo Elevation API",
      source_url: "https://open-meteo.com/en/docs/elevation-api",
      source_resolution_m: 90,
      source_resolution_note: "Open-Meteo 官方文档标称 Copernicus DEM GLO-90 / 90m",
      vertical_datum: "not provided",
      data_boundary: "public reference only",
      usage_terms: "商业部署前需核验并取得对应商业许可",
    } });
  });
  await page.goto("/?map=maplibre");
  if (await page.locator("#loginGate").isVisible()) {
    await page.locator("#loginForm input[name='username']").fill("admin");
    await page.locator("#loginForm input[name='password']").fill(process.env.E2E_PASSWORD || "admin123");
    await page.locator("#loginForm button[type='submit']").click();
  }
  await expect(page.locator("#missionList [data-select-mission][aria-pressed='true']")).toBeVisible();
  await page.locator("#queryElevationProfile").click();
  await expect(page.locator("#elevationProfile")).toContainText("Open-Meteo Elevation API");
  await expect(page.locator("#elevationProfile .elevation-chart-sample")).toHaveCount(3);
  await expect(page.locator("#elevationProfile")).toContainText("不用于安全放行");
  await expect(page.locator("#elevationProfile")).toContainText("来源标称 90m");
  await expect(page.locator("#elevationProfile")).toContainText("Copernicus DEM GLO-90");
  await expect(page.locator("#elevationProfile")).toContainText("商业部署前需核验并取得对应商业许可");
  await page.screenshot({ path: screenshot("public-elevation-profile-1366x768.png"), fullPage: false });
  failUpstream = true;
  await page.locator("#queryElevationProfile").click();
  await expect(page.locator("#elevationProfile")).toContainText("公开高程服务暂不可用");
  await expect(page.locator("#elevationProfile")).toContainText("合成演示数据");
});

test("configured local vector style is selected without duplicating fallback OSM roads", async ({ page }) => {
  await page.route("**/api/map/config", (route) => route.fulfill({ json: { provider: "OpenMapTiles", style_url: "http://127.0.0.1:8890/test-openmaptiles-style.json" } }));
  await page.route("**/test-openmaptiles-style.json", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ version: 8, sources: {}, layers: [{ id: "test-background", type: "background", paint: { "background-color": "#172431" } }] }),
  }));
  await page.goto("/?map=maplibre");
  if (await page.locator("#loginGate").isVisible()) {
    await page.locator("#loginForm input[name='username']").fill("admin");
    await page.locator("#loginForm input[name='password']").fill(process.env.E2E_PASSWORD || "admin123");
    await page.locator("#loginForm button[type='submit']").click();
  }
  await expect(page.locator("#mapModeStatus")).toContainText("OpenMapTiles vector tiles · data synced");
  expect(await page.evaluate(() => window.lpMap.adapter.styleMode)).toBe("openmaptiles");
  expect(await page.evaluate(() => Boolean(window.lpMap.adapter.map.getLayer("lp-reference-roads")))).toBeFalsy();
  expect(await page.evaluate(() => Boolean(window.lpMap.adapter.map.getSource("lp-routes")))).toBeTruthy();
});

test("live OpenFreeMap style renders real Liangping vector tiles", async ({ page }) => {
  test.skip(process.env.LP_E2E_LIVE_MAP !== "1", "requires the public OpenFreeMap tile service");
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") pageErrors.push(message.text()); });
  await page.goto("/?map=maplibre");
  if (await page.locator("#loginGate").isVisible()) {
    await page.locator("#loginForm input[name='username']").fill("admin");
    await page.locator("#loginForm input[name='password']").fill(process.env.E2E_PASSWORD || "admin123");
    await page.locator("#loginForm button[type='submit']").click();
  }
  await expect(page.locator("#mapModeStatus")).toContainText("OpenFreeMap · OpenMapTiles vector tiles · data synced");
  await expect.poll(() => page.evaluate(() => window.lpMap.adapter.map.areTilesLoaded()), { timeout: 20_000 }).toBeTruthy();
  const renderedFeatureCount = await page.evaluate(() => window.lpMap.adapter.map.queryRenderedFeatures().length);
  expect(renderedFeatureCount).toBeGreaterThan(20);
  const buildingLayerIds = await page.evaluate(() => window.lpMap.adapter.map.getStyle().layers.filter((layer) => layer["source-layer"] === "building" || layer.id === "building" || layer.id === "building-3d").map((layer) => layer.id));
  expect(buildingLayerIds).toContain("building");
  const buildingHit = await page.evaluate(async () => {
    const map = window.lpMap.adapter.map;
    const layers = map.getStyle().layers.filter((layer) => layer["source-layer"] === "building" || layer.id === "building" || layer.id === "building-3d").map((layer) => layer.id);
    map.jumpTo({ center: [107.758, 30.646], zoom: 16 });
    await new Promise((resolve) => map.once("idle", resolve));
    const canvas = map.getCanvas();
    for (let y = 12; y < canvas.height; y += 18) for (let x = 12; x < canvas.width; x += 18) {
      const feature = map.queryRenderedFeatures([x, y], { layers }).find((item) => item.geometry?.type === "Polygon" || item.geometry?.type === "MultiPolygon");
      if (feature) {
        const bounds = canvas.getBoundingClientRect();
        return { id: feature.id, properties: feature.properties, screenX: bounds.left + x, screenY: bounds.top + y };
      }
    }
    return null;
  });
  expect(buildingHit).not.toBeNull();
  await page.mouse.click(buildingHit.screenX, buildingHit.screenY);
  await expect(page.locator("#resultBadge")).toContainText("建筑轮廓");
  await expect(page.locator("#resultContent")).toContainText("OpenMapTiles / OpenStreetMap");
  await expect(page.locator("#resultContent")).toContainText("不代表完整建筑障碍库");
  const styleName = new URL(process.env.LP_MAP_STYLE_URL).pathname.split("/").at(-1).replace(/[^a-z0-9-]/gi, "");
  await page.screenshot({ path: screenshot(`maplibre-openfreemap-${styleName}-live-1366x768.png`), fullPage: false });
  expect(pageErrors).toEqual([]);
});

test("SVG fallback remains usable", async ({ page }) => {
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") pageErrors.push(message.text()); });
  await page.goto("/?map=svg");
  if (await page.locator("#loginGate").isVisible()) {
    await page.locator("#loginForm input[name='username']").fill("admin");
    await page.locator("#loginForm input[name='password']").fill(process.env.E2E_PASSWORD || "admin123");
    await page.locator("#loginForm button[type='submit']").click();
  }
  await expect(page.locator("#health")).toContainText("服务正常");
  await expect(page.locator("#mapCanvas svg")).toBeVisible();
  await expect(page.locator("#mapCanvas .route-primary")).toBeVisible();
  await expect(page.locator("#mapCanvas .map-callout")).toHaveCount(0);
  await expect(page.locator(".map-data-boundary")).toBeVisible();
  const calloutBoxes = await page.locator("#mapCanvas .map-callout").evaluateAll((nodes) => nodes.map((node) => { const rect = node.getBoundingClientRect(); return { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom }; }));
  expect(calloutBoxes.every((box, index) => calloutBoxes.slice(index + 1).every((other) => box.right <= other.left || box.left >= other.right || box.bottom <= other.top || box.top >= other.bottom))).toBeTruthy();
  await page.locator("#mapObjectSummary button").filter({ hasText: "高风险障碍物参考点" }).click();
  await expect(page.locator("#resultContent")).toHaveAttribute("data-selected-risk", "true");
  await expect(page.locator("#mapCanvas .geo-spatial-point.is-selected")).toHaveCount(1);
  await expect(page.locator("#resultContent")).toContainText("需人工核验");
  expect(pageErrors).toEqual([]);
});
