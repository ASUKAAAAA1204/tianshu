const { test, expect } = require("@playwright/test");
const path = require("node:path");

const screenshot = (name) => path.resolve(__dirname, "../../artifacts/sprint-m3", name);

test("candidate route review is audited and revoked routes cannot start flight", async ({ page }) => {
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto("/");
  if (await page.locator("#loginGate").isVisible()) {
    await page.locator("#loginForm input[name='username']").fill("admin");
    await page.locator("#loginForm input[name='password']").fill(process.env.E2E_PASSWORD || "admin123");
    await page.locator("#loginForm button[type='submit']").click();
  }
  await expect(page.locator("#health")).toContainText("服务正常");

  const mission = await page.evaluate(async () => {
    const token = localStorage.getItem("lp_token");
    const api = async (path, method = "GET", payload) => {
      const response = await fetch(path, { method, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: payload === undefined ? undefined : JSON.stringify(payload) });
      return { status: response.status, body: await response.json() };
    };
    const bootstrap = await api("/api/bootstrap");
    const created = await api("/api/missions", "POST", {
      id: `MS-REVIEW-${Date.now()}`, name: "航线人工复核验收", vehicle_id: bootstrap.body.vehicles[0].id,
      route_name: "待规划", start_lng: 107.69, start_lat: 30.68, end_lng: 107.695, end_lat: 30.682, planned_altitude: 120,
    });
    if (created.status !== 201) throw new Error(JSON.stringify(created.body));
    const check = await api(`/api/missions/${created.body.id}/check`, "POST", {});
    if (check.status !== 200 || check.body.decision === "blocked") throw new Error(`规则检查失败: ${JSON.stringify(check.body)}`);
    const planned = await api(`/api/missions/${created.body.id}/routes/plan`, "POST", {});
    if (planned.status !== 201) throw new Error(`生成航线失败: ${JSON.stringify(planned.body)}`);
    const missingReason = await api(`/api/missions/${created.body.id}/routes/${planned.body.id}/adopt`, "POST", { reason: " " });
    if (missingReason.status !== 422 || missingReason.body.code !== "DECISION_REASON_REQUIRED") throw new Error("决策理由必填校验未生效");
    const observerLogin = await api("/api/auth/login", "POST", { username: "observer", password: "admin123" });
    const observerDecision = await fetch(`/api/missions/${created.body.id}/routes/${planned.body.id}/adopt`, { method: "POST", headers: { Authorization: `Bearer ${observerLogin.body.token}`, "Content-Type": "application/json" }, body: JSON.stringify({ reason: "权限校验" }) });
    if (observerDecision.status !== 403) throw new Error("观察员角色不应具备航线决策权限");
    const prematureFlight = await api(`/api/missions/${created.body.id}/flight/start`, "POST", {});
    if (prematureFlight.status !== 409 || prematureFlight.body.code !== "ROUTE_NOT_ADOPTED") throw new Error("未采用航线时必须拒绝启动模拟飞行");
    return { id: created.body.id, routeId: planned.body.id };
  });

  await page.reload();
  await expect(page.locator("#health")).toContainText("服务正常");
  await page.locator(`[data-select-mission="${mission.id}"]`).click();
  await expect(page.locator(`[data-select-mission="${mission.id}"]`)).toHaveAttribute("aria-pressed", "true");
  await expect(page.locator("#mapModeStatus")).toContainText("data synced");
  await expect.poll(() => page.evaluate(() => window.lpMap.adapter.referenceGeographyLoaded)).toBe(true);
  await page.locator(`[data-detail="${mission.id}"]`).click();
  await expect(page.locator(`[data-route-decision="adopt"][data-route-id="${mission.routeId}"]`)).toBeVisible();
  await expect(page.locator("#mapModeStatus")).toContainText("data synced");
  await page.screenshot({ path: screenshot("route-review-1366x768.png"), fullPage: false });
  await page.locator("#resultContent").screenshot({ path: screenshot("route-review-panel-1366.png") });
  expect(await page.locator("#resultContent .timeline-row").evaluateAll((rows) => rows.every((row) => row.scrollWidth <= row.clientWidth))).toBeTruthy();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator("#resultContent").scrollIntoViewIfNeeded();
  await page.screenshot({ path: screenshot("route-review-390x844.png"), fullPage: false });
  expect(await page.locator("#resultContent .timeline-row").evaluateAll((rows) => rows.every((row) => row.scrollWidth <= row.clientWidth))).toBeTruthy();
  await page.setViewportSize({ width: 1366, height: 768 });

  const reason = page.locator(`[data-route-reason="${mission.routeId}"]`);
  await reason.fill("测试候选存在待复核事项，退回优化");
  const returnButton = page.locator(`[data-route-decision="return"][data-route-id="${mission.routeId}"]`);
  await returnButton.focus();
  await expect(returnButton).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#resultContent")).toContainText("已退回修改");
  const recordedDecisions = await page.evaluate(async (missionId) => {
    const token = localStorage.getItem("lp_token");
    const response = await fetch(`/api/missions/${missionId}/route-decisions`, { headers: { Authorization: `Bearer ${token}` } });
    return response.json();
  }, mission.id);
  expect(recordedDecisions[0]).toMatchObject({ route_id: mission.routeId, decision: "returned", actor_username: "admin", reason: "测试候选存在待复核事项，退回优化" });
  const duplicateDecision = await page.evaluate(async ({ missionId, routeId }) => {
    const token = localStorage.getItem("lp_token");
    const response = await fetch(`/api/missions/${missionId}/routes/${routeId}/adopt`, { method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: JSON.stringify({ reason: "重复决策应拒绝" }) });
    return { status: response.status, body: await response.json() };
  }, { missionId: mission.id, routeId: mission.routeId });
  expect(duplicateDecision.status).toBe(409);
  expect(duplicateDecision.body.code).toBe("ROUTE_ALREADY_REVIEWED");
  await expect(page.locator("#resultContent")).toContainText("admin");

  const nextRoute = await page.evaluate(async (missionId) => {
    const token = localStorage.getItem("lp_token");
    const response = await fetch(`/api/missions/${missionId}/routes/plan`, { method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: "{}" });
    return { status: response.status, body: await response.json() };
  }, mission.id);
  expect(nextRoute.status).toBe(201);
  await page.locator(`[data-detail="${mission.id}"]`).click();
  const nextReason = page.locator(`[data-route-reason="${nextRoute.body.id}"]`);
  await nextReason.fill("复核通过，采用新生成候选");
  await page.locator(`[data-route-decision="adopt"][data-route-id="${nextRoute.body.id}"]`).click();
  await expect(page.locator("#resultContent")).toContainText("当前已采用");
  await page.locator("#resultContent").screenshot({ path: screenshot("route-review-adopted-panel.png") });

  const revokeReason = page.locator(`[data-route-reason="${nextRoute.body.id}"]`);
  await revokeReason.fill("现场复核发现条件变化，撤销本次采用");
  await page.locator(`[data-route-decision="revoke"][data-route-id="${nextRoute.body.id}"]`).click();
  await expect(page.locator("#resultContent")).toContainText("已撤销");
  await page.locator("#resultContent").screenshot({ path: screenshot("route-review-revoked-panel.png") });
  const blockedFlight = await page.evaluate(async (missionId) => {
    const token = localStorage.getItem("lp_token");
    const response = await fetch(`/api/missions/${missionId}/flight/start`, { method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: "{}" });
    return { status: response.status, body: await response.json() };
  }, mission.id);
  expect(blockedFlight.status).toBe(409);
  expect(blockedFlight.body.code).toBe("ROUTE_NOT_ADOPTED");

  const finalRoute = await page.evaluate(async (missionId) => {
    const token = localStorage.getItem("lp_token");
    const response = await fetch(`/api/missions/${missionId}/routes/plan`, { method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: "{}" });
    return response.json();
  }, mission.id);
  await page.locator(`[data-detail="${mission.id}"]`).click();
  await page.locator(`[data-route-reason="${finalRoute.id}"]`).fill("最终复核通过");
  await page.locator(`[data-route-decision="adopt"][data-route-id="${finalRoute.id}"]`).click();
  const started = await page.evaluate(async (missionId) => {
    const token = localStorage.getItem("lp_token");
    const response = await fetch(`/api/missions/${missionId}/flight/start`, { method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: "{}" });
    return { status: response.status, body: await response.json() };
  }, mission.id);
  expect(started.status).toBe(201);

  const restrictionChecks = await page.evaluate(async () => {
    const token = localStorage.getItem("lp_token");
    const api = async (path, method = "GET", payload) => {
      const response = await fetch(path, { method, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, body: payload === undefined ? undefined : JSON.stringify(payload) });
      return { status: response.status, body: await response.json() };
    };
    const bootstrap = await api("/api/bootstrap");
    const createAndCheck = async (id, viaPoints = []) => {
      const created = await api("/api/missions", "POST", {
        id, name: "限制区域逐段检查", vehicle_id: bootstrap.body.vehicles[0].id, route_name: "待规划",
        start_lng: 107.76, start_lat: 30.68, end_lng: 107.82, end_lat: 30.68,
        planned_altitude: 120, via_points_json: JSON.stringify(viaPoints),
      });
      if (created.status !== 201) throw new Error(JSON.stringify(created.body));
      return api(`/api/missions/${id}/check`, "POST", {});
    };
    const direct = await createAndCheck(`MS-CROSS-${Date.now()}`);
    const bypass = await createAndCheck(`MS-BYPASS-${Date.now()}`, [{ name: "北侧绕行参考点", longitude: 107.79, latitude: 30.705, source: "synthetic_demo" }]);
    return { direct: direct.body, bypass: bypass.body };
  });
  expect(restrictionChecks.direct.items.some((item) => item.rule_code === "R-001" && item.level === "hard")).toBeTruthy();
  expect(restrictionChecks.direct.items.some((item) => item.rule_code === "A-001")).toBeTruthy();
  expect(restrictionChecks.bypass.items.some((item) => item.rule_code === "R-001" || item.rule_code === "A-001")).toBeFalsy();
  expect(pageErrors).toEqual([]);
});
