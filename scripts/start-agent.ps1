# 텔레그램 채널을 켜고 이 폴더에서 총괄 에이전트(Claude Code)를 시작한다.
# 사용: PowerShell에서
#   powershell -ExecutionPolicy Bypass -File .\scripts\start-agent.ps1
# 종료: Claude Code 창에서 /exit 또는 Ctrl+C 두 번
# 주의: 이 창이 켜져 있는 동안에만 텔레그램 메시지를 받는다.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# Bun: 텔레그램 플러그인 서버 실행에 필요
$bunDir = Join-Path $env:USERPROFILE '.bun\bin'
if (Test-Path $bunDir) { $env:Path = "$bunDir;$env:Path" }
if (-not (Get-Command bun -ErrorAction SilentlyContinue)) {
    Write-Host '[중단] Bun이 없습니다. https://bun.sh 에서 설치하세요.'
    exit 1
}

# 봇 토큰: 환경변수 또는 /telegram:configure 가 만든 파일 (내용은 읽지 않고 있는지만 확인)
$tokenFile = Join-Path $env:USERPROFILE '.claude\channels\telegram\.env'
if (-not $env:TELEGRAM_BOT_TOKEN -and -not (Test-Path $tokenFile)) {
    Write-Host '[중단] 봇 토큰이 없습니다. claude 실행 후 /telegram:configure <토큰> 을 먼저 하세요.'
    exit 1
}

Write-Host "[시작] $root"
Write-Host '[안내] 텔레그램 채널 켜짐. 이 창을 닫으면 봇이 응답하지 않습니다.'
claude --channels plugin:telegram@claude-plugins-official
