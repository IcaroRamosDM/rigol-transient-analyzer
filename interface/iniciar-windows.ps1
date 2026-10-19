param([int]$Port = 8765, [string]$Distribution = 'Ubuntu-26.04', [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$ctProjectPath = Split-Path $PSScriptRoot
if ($ctProjectPath -match '^\\\\wsl(?:\.localhost|\$)\\([^\\]+)\\(.+)$') {
    $Distribution = $Matches[1]
    $ctLinuxPath = '/' + $Matches[2].Replace('\', '/')
} else {
    $ctLinuxPath = (& wsl.exe -d $Distribution --exec wslpath -a $ctProjectPath).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel localizar o projeto no Ubuntu.' }
}
$ctUrl = 'http://localhost:' + $Port
function Test-RtaInterface {
    try {
        $ctInfo = Invoke-RestMethod -Uri ($ctUrl + '/api/bootstrap') -TimeoutSec 1
        return $ctInfo.app -eq 'Rigol Transient Analyzer'
    } catch { return $false }
}
if (-not (Test-RtaInterface)) {
    $ctArguments = @('-d', $Distribution, '--cd', $ctLinuxPath, '--',
                     'bash', './iniciar-interface.sh', '--no-browser', '--port', [string]$Port)
    $ctQuoted = $ctArguments | ForEach-Object {
        if ($_ -match '[\s"]') { '"' + $_.Replace('"', '\"') + '"' } else { $_ }
    }
    Start-Process -FilePath 'wsl.exe' -ArgumentList ($ctQuoted -join ' ') -WindowStyle Hidden
    $ctReady = $false
    for ($ctTry = 0; $ctTry -lt 40; $ctTry++) {
        if (Test-RtaInterface) { $ctReady = $true; break }
        Start-Sleep -Milliseconds 300
    }
    if (-not $ctReady) {
        throw 'A interface nao iniciou. No Ubuntu, abra a pasta do projeto e execute: make interface'
    }
}
if (-not $NoBrowser) { Start-Process $ctUrl }
