const { test, expect } = require("@playwright/test");

test("recorded telemetry replay moves the aircraft and actual-track overlay", async ({ page }) => {
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") pageErrors.push(message.text()); });
  await page.goto("/?map=maplibre");
  if (await page.locator("#loginGate").isVisible()) {
    await page.locator("#loginForm input[name='username']").fill("admin");
    await page.locator("#loginForm input[name='password']").fill(process.env.E2E_PASSWORD || "admin123");
    await page.locator("#loginForm button[type='submit']").click();
  }
  await expect(page.locator("#health")).toContainText("服务正常");

  const missionId = await page.evaluate(async () => {
    const token = localStorage.getItem("lp_token");
    const request = async (path, method = "GET", payload) => {
      const response = await fetch(path, { method, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: payload === undefined ? undefined : JSON.stringify(payload) });
      const body = await response.json();
      if (!response.ok) throw new Error(`${method} ${path}: ${response.status} ${JSON.stringify(body)}`);
      return body;
    };
    const bootstrap = await request("/api/bootstrap");
    const mission = await request("/api/missions", "POST", {
      id: `MS-REPLAY-${Date.now()}`, name: "轨迹回放验收任务", vehicle_id: bootstrap.vehicles[0].id,
      route_name: "REPLAY-TEST", start_lng: 107.69, start_lat: 30.68, end_lng: 107.695, end_lat: 30.682, planned_altitude: 120,
    });
    const emptyTrack = await request(`/api/missions/${mission.id}/telemetry/track`);
    if (emptyTrack.available !== false || emptyTrack.samples.length !== 0) throw new Error("尚无飞行会话时应返回明确的空轨迹状态");
    const check = await request(`/api/missions/${mission.id}/check`, "POST", {});
    if (check.decision === "blocked") throw new Error(`回放验收路线被规则阻断: ${JSON.stringify(check)}`);
    const route = await request(`/api/missions/${mission.id}/routes/plan`, "POST", {});
    await request(`/api/missions/${mission.id}/routes/${route.id}/adopt`, "POST", { reason: "隔离环境回放验收" });
    await request(`/api/missions/${mission.id}/flight/start`, "POST", {});
    await request(`/api/missions/${mission.id}/flight/tick`, "POST", { step: 25 });
    await request(`/api/missions/${mission.id}/flight/tick`, "POST", { step: 25 });
    const track = await request(`/api/missions/${mission.id}/telemetry/track`);
    if (track.samples.length !== 3) throw new Error(`期望3个记录点，实际${track.samples.length}`);
    return mission.id;
  });

  await page.reload();
  await expect(page.locator("#health")).toContainText("服务正常");
  await page.locator(`[data-select-mission="${missionId}"]`).click();
  const slider = page.locator("#trackReplayRange");
  const toggle = page.locator("#trackReplayToggle");
  await expect(page.locator("#trackReplayStatus")).toContainText("3 个定位点");
  await expect(slider).toHaveAttribute("max", "2");
  await expect(slider).toHaveValue("2");
  const endLongitude = await page.evaluate(() => window.lpMap.adapter.buildData().vehicle.longitude);
  const replay = await page.evaluate(async (id) => {
    const token = localStorage.getItem("lp_token");
    const response = await fetch(`/api/missions/${id}/telemetry/track`, { headers: { Authorization: `Bearer ${token}` } });
    return response.json();
  }, missionId);

  await toggle.click();
  await expect.poll(() => slider.inputValue()).toBe("1");
  const firstReplayPosition = await page.evaluate(() => {
    const data = window.lpMap.adapter.buildData();
    const actual = data.routes.features.find((feature) => feature.properties.route_type === "actual");
    return { longitude: data.vehicle.longitude, track: actual?.geometry.coordinates || [] };
  });
  expect(firstReplayPosition.longitude).toBeCloseTo(replay.samples[1].longitude, 6);
  expect(firstReplayPosition.longitude).not.toBeCloseTo(endLongitude, 6);
  expect(firstReplayPosition.track).toHaveLength(2);
  await toggle.click();
  await page.waitForTimeout(750);
  await expect(slider).toHaveValue("1");
  expect(pageErrors).toEqual([]);
});
