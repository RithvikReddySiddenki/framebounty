param([string]$Path = "$PSScriptRoot/../.env")
$ErrorActionPreference = 'Stop'

# Parse data, never execute it. Validate the complete file before changing the
# process environment, and accept only documented application settings.
$allowed = @{}
foreach ($line in Get-Content -LiteralPath "$PSScriptRoot/../.env.example") {
    if ($line -match '^([A-Z][A-Z0-9_]*)=') { $allowed[$Matches[1]] = $true }
}
$settings = @{}
foreach ($rawLine in Get-Content -LiteralPath $Path) {
    $line = $rawLine.Trim()
    if (-not $line -or $line.StartsWith('#')) { continue }
    if ($line -notmatch '^([A-Z][A-Z0-9_]*)=(.*)$') {
        throw 'Invalid environment-file entry. Use KEY=value; shell expressions are not supported.'
    }
    $name, $value = $Matches[1], $Matches[2].Trim()
    if (-not $allowed.ContainsKey($name) -or $settings.ContainsKey($name)) {
        throw 'Unknown or duplicate application setting in environment file.'
    }
    if ($value.Length -ge 2) {
        $first, $last = $value[0], $value[$value.Length - 1]
        if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
            $value = $value.Substring(1, $value.Length - 2)
        }
    }
    $settings[$name] = $value
}
foreach ($name in $settings.Keys) {
    [Environment]::SetEnvironmentVariable($name, $settings[$name], 'Process')
}
Write-Host "Loaded $($settings.Count) application settings into this terminal. Values were not displayed."
