param(
    [string]$KeyPath = (Join-Path $env:USERPROFILE ".ssh\nz_tg_status_bot_deploy_ed25519")
)

$ErrorActionPreference = "Stop"

if (Test-Path -LiteralPath $KeyPath) {
    Write-Host "Deploy key already exists: $KeyPath"
} else {
    $KeyDir = Split-Path -Parent $KeyPath
    New-Item -ItemType Directory -Force -Path $KeyDir | Out-Null
    Write-Host "Creating deploy key. When ssh-keygen asks for passphrase, press Enter twice."
    ssh-keygen -t ed25519 -f $KeyPath -C "github-actions-nz-tg-status-bot"
}

Write-Host ""
Write-Host "Private key:"
Write-Host $KeyPath
Write-Host ""
Write-Host "Public key. Add this line to VPS ~/.ssh/authorized_keys for the deploy user:"
Write-Host ""
$PublicKeyPath = "$KeyPath.pub"
if (-not (Test-Path -LiteralPath $PublicKeyPath)) {
    throw "Public key was not created: $PublicKeyPath"
}
Get-Content -LiteralPath $PublicKeyPath -Raw
