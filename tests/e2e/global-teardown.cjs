const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

module.exports = async (config) => {
  const outputDir = config.outputDir;
  if (!outputDir) return;
  const resolved = path.dirname(path.resolve(outputDir));
  if (path.dirname(resolved) !== path.resolve(os.tmpdir()) || !path.basename(resolved).startsWith("liangping-map-e2e-")) {
    throw new Error("Refusing to clean a directory outside the isolated map E2E temp location");
  }
  if (fs.existsSync(resolved)) fs.rmSync(resolved, { recursive: true, force: true });
};
