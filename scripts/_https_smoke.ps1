$ErrorActionPreference = "Stop"
$payload = @{ username = "admin"; password = "local-validation-bootstrap-2026" } | ConvertTo-Json
$login = Invoke-WebRequest -SkipCertificateCheck -UseBasicParsing -Uri "https://lowalt.local/api/auth/login" -Method Post -Headers @{ Host = "lowalt.local" } -ContentType "application/json" -Body $payload -SessionVariable session
Write-Host "LOGIN $($login.StatusCode) $($login.Content)"
$health = Invoke-WebRequest -SkipCertificateCheck -UseBasicParsing -Uri "https://lowalt.local/api/health" -Headers @{ Host = "lowalt.local" } -WebSession $session
Write-Host "HEALTH $($health.StatusCode) $($health.Content)"
$bootstrap = Invoke-WebRequest -SkipCertificateCheck -UseBasicParsing -Uri "https://lowalt.local/api/bootstrap" -Headers @{ Host = "lowalt.local" } -WebSession $session
Write-Host "BOOTSTRAP $($bootstrap.StatusCode) $($bootstrap.Content.Substring(0, [Math]::Min(180, $bootstrap.Content.Length)))"
