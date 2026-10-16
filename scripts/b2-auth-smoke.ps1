$ErrorActionPreference = "Stop"
$base = if ($env:LP_BASE_URL) { $env:LP_BASE_URL } else { "http://127.0.0.1:8765" }
foreach ($username in @("admin", "dispatcher", "observer", "auditor")) {
  $payload = @{ username = $username; password = "admin123" } | ConvertTo-Json -Compress
  $login = Invoke-RestMethod -Method Post -Uri "$base/api/auth/login" -ContentType "application/json" -Body $payload
  if (-not $login.token -or $login.role -ne $username) { throw "Login/role check failed for $username" }
  $me = Invoke-RestMethod -Uri "$base/api/auth/me" -Headers @{ Authorization = "Bearer $($login.token)" }
  if ($me.role -ne $username) { throw "Session role check failed for $username" }
  if ($username -eq "observer") {
    $writeChecks = @(
      @{ method = "Post"; uri = "$base/api/demo/reset"; body = "{}" },
      @{ method = "Post"; uri = "$base/api/missions"; body = "{}" },
      @{ method = "Post"; uri = "$base/api/layers/import"; body = "{}" },
      @{ method = "Post"; uri = "$base/api/missions/NO-SUCH/check"; body = "{}" },
      @{ method = "Post"; uri = "$base/api/missions/NO-SUCH/routes/plan"; body = "{}" },
      @{ method = "Post"; uri = "$base/api/missions/NO-SUCH/flight/start"; body = "{}" }
    )
    foreach ($check in $writeChecks) {
      try {
        Invoke-RestMethod -Method $check.method -Uri $check.uri -Headers @{ Authorization = "Bearer $($login.token)" } -ContentType "application/json" -Body $check.body
        throw "Observer write gate did not reject: $($check.uri)"
      } catch {
        if ($_.Exception.Response.StatusCode.value__ -ne 403) { throw }
      }
    }
  }
  if ($username -eq "auditor") {
    foreach ($uri in @("$base/api/missions", "$base/api/layers/import", "$base/api/missions/NO-SUCH/check")) {
      try {
        Invoke-RestMethod -Method Post -Uri $uri -Headers @{ Authorization = "Bearer $($login.token)" } -ContentType "application/json" -Body "{}"
        throw "Auditor write gate did not reject: $uri"
      } catch {
        if ($_.Exception.Response.StatusCode.value__ -ne 403) { throw }
      }
    }
  }
  Invoke-RestMethod -Method Post -Uri "$base/api/auth/logout" -Headers @{ Authorization = "Bearer $($login.token)" } | Out-Null
  Write-Host "${username}: login, session, logout passed"
}
