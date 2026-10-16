const { defineConfig, devices } = require("@playwright/test");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const runDir = fs.mkdtempSync(path.join(os.tmpdir(), "liangping-map-e2e-"));
const testDatabase = path.join(runDir, "runtime.sqlite");
fs.mkdirSync(path.join(__dirname, "artifacts", "sprint-m3"), { recursive: true });
process.env.LP_MAP_E2E_DB = testDatabase;
process.once("exit", () => {
  const tempRoot = path.resolve(os.tmpdir());
  if (path.dirname(runDir) === tempRoot && path.basename(runDir).startsWith("liangping-map-e2e-")) fs.rmSync(runDir, { recursive: true, force: true });
});
module.exports = defineConfig({
  outputDir: path.join(runDir, "playwright-results"),
  metadata: { lpMapE2eTempDir: runDir },
  globalTeardown: "./tests/e2e/global-teardown.cjs",
  testDir: "./tests/e2e",
  timeout: 30_000,
  expect: { timeout: 8_000 },
  fullyParallel: false,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:8890", channel: "chrome", viewport: { width: 1366, height: 768 }, ...devices["Desktop Chrome"] },
  webServer: {
    command: "python backend/server.py",
    cwd: __dirname,
    url: "http://127.0.0.1:8890/api/health",
    reuseExistingServer: false,
    timeout: 120_000,
    env: { DATABASE_URL: `sqlite:///${testDatabase.replaceAll("\\", "/")}`, LP_PORT: "8890", DEMO_MODE: "false", LP_ENV: "development", E2E_PASSWORD: "admin123" },
  },
});
