# Oracle's official CLI and MCP server use a separate local authentication profile.
[CmdletBinding()]
param(
    [ValidateSet('Install', 'Login', 'Check')]
    [string]$Action = 'Check',
    [string]$Region,
    [string]$TenancyName
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$profileName = 'DOCUMOUSE'
$serverName = 'oracle-oci-cloud'
$configPath = Join-Path $env:USERPROFILE '.oci\config'

function Invoke-External {
    param([string]$Command, [string[]]$ArgumentList)
    & $Command @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE."
    }
}

function Get-OracleServer {
    param([string]$CodexCommand)
    $json = & $CodexCommand mcp list --json
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not read the Codex MCP configuration.'
    }
    return @($json | ConvertFrom-Json) | Where-Object { $_.name -eq $serverName }
}

$uv = (Get-Command uv -ErrorAction Stop).Source
$codex = (Get-Command codex -ErrorAction Stop).Source
$toolBin = (& $uv tool dir --bin).Trim()
if ($LASTEXITCODE -ne 0) {
    throw 'Could not locate the uv tool directory.'
}
$oci = Join-Path $toolBin 'oci.exe'

if ($Action -eq 'Install') {
    Invoke-External $uv @('tool', 'install', '--python', '3.12', 'oci-cli==3.94.2')
    Invoke-External $uv @('tool', 'install', '--python', '3.13', 'oracle.oci-cloud-mcp-server==2.2.3')

    if (Get-OracleServer $codex) {
        Write-Host "MCP server '$serverName' already exists; its configuration was preserved."
    } else {
        Invoke-External $codex @(
            'mcp', 'add', $serverName,
            '--env', "OCI_CONFIG_FILE=$configPath",
            '--env', "OCI_CONFIG_PROFILE=$profileName",
            '--env', 'OCI_MCP_AUTH_TYPE=security_token',
            '--env', 'FASTMCP_LOG_LEVEL=ERROR',
            '--', $uv, 'tool', 'run', '--python', '3.13',
            'oracle.oci-cloud-mcp-server==2.2.3'
        )
        # A cold start on Windows can exceed Codex's default ten-second timeout.
        $codexRoot = if ([string]::IsNullOrWhiteSpace($env:CODEX_HOME)) {
            Join-Path $env:USERPROFILE '.codex'
        } else { $env:CODEX_HOME }
        $codexConfig = Join-Path $codexRoot 'config.toml'
        $content = [System.IO.File]::ReadAllText($codexConfig)
        $header = [regex]'(?m)^\[mcp_servers\.oracle-oci-cloud\]\r?\n'
        if ($header.Matches($content).Count -ne 1) {
            throw 'Could not locate the new Oracle MCP section to set its startup timeout.'
        }
        $content = $header.Replace($content, [System.Text.RegularExpressions.MatchEvaluator]{
            param($match)
            $match.Value + "startup_timeout_sec = 90`r`n"
        }, 1)
        [System.IO.File]::WriteAllText($codexConfig, $content, [System.Text.UTF8Encoding]::new($false))
    }
    Write-Host 'Tools installed. Restart the Oracle MCP server in Codex to load it.'
    Write-Host 'Oracle account signup and browser authentication are still required.'
    return
}

if (-not (Test-Path -LiteralPath $oci)) {
    throw 'Oracle CLI is missing. Run this script with -Action Install first.'
}

if ($Action -eq 'Login') {
    if ([string]::IsNullOrWhiteSpace($Region) -or [string]::IsNullOrWhiteSpace($TenancyName)) {
        throw 'Supply -Region and -TenancyName from your existing Oracle account.'
    }
    Invoke-External $oci @(
        'session', 'authenticate', '--region', $Region,
        '--tenancy-name', $TenancyName, '--profile-name', $profileName,
        '--config-location', $configPath
    )
    return
}

Invoke-External $oci @('--version')
$server = Get-OracleServer $codex
if (-not $server) {
    throw 'Oracle MCP is not registered. Run this script with -Action Install first.'
}
$expectedArguments = @('tool', 'run', '--python', '3.13', 'oracle.oci-cloud-mcp-server==2.2.3')
if (-not $server.enabled -or $server.transport.type -ne 'stdio' -or
    $server.transport.command -ne $uv -or
    ($server.transport.args -join '|') -ne ($expectedArguments -join '|') -or
    $server.transport.env.OCI_CONFIG_FILE -ne $configPath -or
    $server.transport.env.OCI_CONFIG_PROFILE -ne $profileName -or
    $server.transport.env.OCI_MCP_AUTH_TYPE -ne 'security_token') {
    throw "The existing '$serverName' configuration differs from this project's setup. Inspect it before changing it."
}
Write-Host 'Oracle MCP is registered with the DOCUMOUSE session profile.'
if (-not (Test-Path -LiteralPath $configPath)) {
    Write-Host 'Authentication pending: finish Oracle signup, then run -Action Login.'
    return
}
Invoke-External $oci @(
    'session', 'validate', '--config-file', $configPath,
    '--profile', $profileName, '--auth', 'security_token'
)
Write-Host 'Oracle session validated. This check does not create or change cloud resources.'
