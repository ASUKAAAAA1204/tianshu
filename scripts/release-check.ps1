$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
  python -m unittest discover -s tests -q
  if ($LASTEXITCODE -ne 0) { throw 'Python unit tests failed.' }
  python scripts/validate-demo-data.py
  if ($LASTEXITCODE -ne 0) { throw 'Demo data validation failed.' }
  python scripts/frontend-contract-smoke.py
  if ($LASTEXITCODE -ne 0) { throw 'Frontend contract smoke failed.' }
  python scripts/api-surface-smoke.py
  if ($LASTEXITCODE -ne 0) { throw 'API surface smoke failed.' }
  python scripts/oss-embedding-smoke.py
  if ($LASTEXITCODE -ne 0) { throw 'Open-source embedding smoke failed.' }
  python -m compileall -q backend
  if ($LASTEXITCODE -ne 0) { throw 'Backend compile check failed.' }
  node --check frontend/app.js
  node --check frontend/map-controller.js
  node --check frontend/adapters/map-adapter.js
  node --check frontend/adapters/maplibre-adapter.js
  if ($LASTEXITCODE -ne 0) { throw 'Frontend syntax check failed.' }
  npm run test:e2e -- tests/e2e/debug-map.spec.cjs
  if ($LASTEXITCODE -ne 0) { throw 'Playwright E2E smoke failed.' }
  $required = @(
    'docs/evidence/用户证据包-20260919.md',
    'docs/evidence/results/postgres-validation-20260919.md',
    'docs/release/RELEASE-0.6.1-p0-4-6.md',
    'docs/release/RELEASE-0.6.1-readiness-boundary.md',
    'scripts/p1-postgres-smoke.ps1',
    'scripts/p1-postgres-flow.ps1',
    'scripts/p1-postgres-restore.ps1'
  )
  foreach ($path in $required) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Release artifact missing: $path" }
  }
  Write-Host 'Release check passed: tests and P0-4/P0-5/P0-6 artifacts are present.'
}
finally { Pop-Location }
