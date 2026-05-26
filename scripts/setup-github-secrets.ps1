$ErrorActionPreference = "Stop"

param(
    [string]$Repo = "NikitaZhilin/NZ_tg_status_bot",
    [string]$SshKeyPath = "",
    [switch]$GenerateDeployKey
)

function Read-RequiredSecret([string]$Name, [string]$Prompt) {
    $Value = Read-Host -Prompt $Prompt
    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "$Name is required"
    }
    return $Value.Trim()
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI 'gh' is not installed or not available in PATH."
}

$DefaultDeployKey = Join-Path $env:USERPROFILE ".ssh\nz_tg_status_bot_deploy_ed25519"
if ([string]::IsNullOrWhiteSpace($SshKeyPath)) {
    $SshKeyPath = $DefaultDeployKey
}

if ($GenerateDeployKey -and -not (Test-Path -LiteralPath $SshKeyPath)) {
    $KeyDir = Split-Path -Parent $SshKeyPath
    New-Item -ItemType Directory -Force -Path $KeyDir | Out-Null
    ssh-keygen -t ed25519 -f $SshKeyPath -N "" -C "github-actions-nz-tg-status-bot"
}

if ([string]::IsNullOrWhiteSpace($SshKeyPath) -or -not (Test-Path -LiteralPath $SshKeyPath)) {
    throw "Deploy SSH private key was not found. Run with -GenerateDeployKey or pass -SshKeyPath. Default: $DefaultDeployKey"
}

Write-Host "Using SSH key: $SshKeyPath"
Write-Host "This must be a VPS deploy key. Do not use unrelated GitHub deploy keys unless their public key is installed on the VPS."

$VpsHost = Read-RequiredSecret "VPS_HOST" "VPS host/IP"
$VpsUser = Read-RequiredSecret "VPS_USER" "VPS SSH user"
$VpsPort = Read-Host -Prompt "VPS SSH port [22]"
if ([string]::IsNullOrWhiteSpace($VpsPort)) {
    $VpsPort = "22"
}
$VpsAppDir = Read-Host -Prompt "VPS app dir [/opt/nz_tg_status_bot]"
if ([string]::IsNullOrWhiteSpace($VpsAppDir)) {
    $VpsAppDir = "/opt/nz_tg_status_bot"
}

$BotToken = Read-RequiredSecret "BOT_TOKEN" "Status bot token"
$AdminIds = Read-RequiredSecret "ADMIN_IDS" "Admin Telegram IDs, comma-separated"
$RemembermeUrl = Read-RequiredSecret "REMEMBERME_API_BASE_URL" "RememberMe API base URL"
$RemembermeToken = Read-RequiredSecret "REMEMBERME_ADMIN_TOKEN" "RememberMe ADMIN_TOKEN"
$IncubatorDb = Read-RequiredSecret "INCUBATOR_DATABASE_PATH" "Incubator SQLite path on VPS"
$IncubatorPid = Read-Host -Prompt "Incubator PID file path on VPS [optional]"

$PublicKeyPath = "$SshKeyPath.pub"
if (Test-Path -LiteralPath $PublicKeyPath) {
    Write-Host ""
    Write-Host "Public key to add to VPS ~/.ssh/authorized_keys if it is not there yet:"
    Write-Host (Get-Content -LiteralPath $PublicKeyPath -Raw)
    Write-Host ""
    $TestSsh = Read-Host -Prompt "Test SSH access with this key before writing secrets? [y/N]"
    if ($TestSsh.Trim().ToLowerInvariant() -eq "y") {
        ssh -i $SshKeyPath -p $VpsPort "$VpsUser@$VpsHost" "echo status-bot-ssh-ok"
    }
}

gh secret set VPS_HOST -R $Repo --body $VpsHost
gh secret set VPS_USER -R $Repo --body $VpsUser
gh secret set VPS_PORT -R $Repo --body $VpsPort
gh secret set VPS_APP_DIR -R $Repo --body $VpsAppDir
Get-Content -LiteralPath $SshKeyPath -Raw | gh secret set VPS_SSH_KEY -R $Repo

gh secret set BOT_TOKEN -R $Repo --body $BotToken
gh secret set ADMIN_IDS -R $Repo --body $AdminIds
gh secret set REMEMBERME_API_BASE_URL -R $Repo --body $RemembermeUrl
gh secret set REMEMBERME_ADMIN_TOKEN -R $Repo --body $RemembermeToken
gh secret set INCUBATOR_DATABASE_PATH -R $Repo --body $IncubatorDb
gh secret set INCUBATOR_PID_FILE -R $Repo --body $IncubatorPid

Write-Host "GitHub Actions secrets were created/updated for $Repo."
