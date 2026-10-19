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
    return { mapRatio: map.width / workspace.width, mapWidth: map.width, sidebarWidth: sidebar.width, mapHeight: map.height, verticalGap: nextSection.top - mapPanel.bottom, sidebarColumns: getComputedStyle(document.querySelector(".map-sidebar")).gridTemplateColumns, boundaryVisible: document.querySelector(".map-data-boundary").getBoundingClientRect().bottom <= window.innerHeight };
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
