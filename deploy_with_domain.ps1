# ============================================================
# استقرار نهایی با دامنه darsyar360.ir و HTTPS
# ============================================================

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host 'ERROR: Need Administrator' -ForegroundColor Red
    exit 1
}

$ErrorActionPreference = 'Stop'
$INSTALL_DIR = 'C:\bale_course_survey_final'
$DOMAIN = 'darsyar360.ir'

Write-Host ''
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host "  Deploy v3.5.0 - Domain: $DOMAIN" -ForegroundColor Cyan
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ''

# --- Step 0: Check prerequisites ---
Write-Host '=== Step 0: Check prerequisites ===' -ForegroundColor Cyan

if (-not (Test-Path $INSTALL_DIR)) {
    Write-Host "ERROR: Folder not found: $INSTALL_DIR" -ForegroundColor Red
    exit 1
}
Write-Host 'OK: Project folder found' -ForegroundColor Green

$pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) {
    $pythonExe = "C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe"
}
Write-Host "OK: Python path = $pythonExe" -ForegroundColor Green

# Install packages
if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
    Set-ExecutionPolicy Bypass -Scope Process -Force
    $chocoScriptPath = "$env:TEMP\choco-install.ps1"
    (New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1') | Out-File -FilePath $chocoScriptPath -Encoding UTF8
    & $chocoScriptPath
    refreshenv
}
if (-not (Get-Command nssm -ErrorAction SilentlyContinue)) { choco install nssm -y --no-progress; refreshenv }
if (-not (Get-Command nginx -ErrorAction SilentlyContinue)) { choco install nginx -y --no-progress; refreshenv }

Push-Location $INSTALL_DIR
python -m pip install --timeout 180 -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com flask pandas openpyxl waitress
Pop-Location
Write-Host 'OK: Dependencies checked' -ForegroundColor Green

# --- Step 1: Stop old services ---
Write-Host ''
Write-Host '=== Step 1: Stop old services ===' -ForegroundColor Cyan

$servicesToStop = @('SurveyMiniApp', 'SurveyWebsite', 'SurveyBot', 'SurveyTunnel')
foreach ($svc in $servicesToStop) {
    if (Get-Service -Name $svc -ErrorAction SilentlyContinue) {
        Stop-Service -Name $svc -Force -ErrorAction SilentlyContinue
        nssm remove $svc confirm
        Write-Host "  Removed: $svc" -ForegroundColor Green
    }
}
Get-Process nginx -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Write-Host 'OK: Old services stopped' -ForegroundColor Green

# --- Step 2: Open firewall ports ---
Write-Host ''
Write-Host '=== Step 2: Open firewall ports ===' -ForegroundColor Cyan

$portsToOpen = @(80, 443, 5000, 8080)
foreach ($portNum in $portsToOpen) {
    $ruleName = "Port $portNum"
    if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $portNum | Out-Null
    }
    Write-Host "  OK: Port $portNum" -ForegroundColor Green
}

# --- Step 3: Configure Nginx with SSL ---
Write-Host ''
Write-Host '=== Step 3: Configure Nginx + SSL ===' -ForegroundColor Cyan

$iis = Get-Service W3SVC -ErrorAction SilentlyContinue
if ($iis -and $iis.Status -eq 'Running') {
    Stop-Service W3SVC -Force
    Set-Service W3SVC -StartupType Disabled
}

$nginxPath = $null
$nginxExe = Get-Command nginx -ErrorAction SilentlyContinue
if ($nginxExe) { $nginxPath = Split-Path $nginxExe.Source }
if (-not $nginxPath -or -not (Test-Path "$nginxPath\nginx.exe")) {
    $found = Get-ChildItem -Path 'C:\' -Filter 'nginx.exe' -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { $nginxPath = Split-Path $found.FullName }
}
Write-Host "  Nginx path: $nginxPath" -ForegroundColor Green

# Generate self-signed SSL certificate
Write-Host '  Generating SSL certificate...' -ForegroundColor Yellow
$sslDir = "$nginxPath\ssl"
if (-not (Test-Path $sslDir)) { New-Item -ItemType Directory -Path $sslDir -Force | Out-Null }

$cert = New-SelfSignedCertificate -DnsName $DOMAIN -CertStoreLocation "Cert:\LocalMachine\My" -NotAfter (Get-Date).AddYears(10) -FriendlyName $DOMAIN
$certPath = "$sslDir\$DOMAIN.pfx"
$pwd = ConvertTo-SecureString -String "survey123" -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath $certPath -Password $pwd | Out-Null

# Convert PFX to PEM (using OpenSSL if available, or use certutil)
$keyPath = "$sslDir\$DOMAIN.key"
$crtPath = "$sslDir\$DOMAIN.crt"

# Try OpenSSL
$openssl = Get-Command openssl -ErrorAction SilentlyContinue
if ($openssl) {
    & openssl pkcs12 -in $certPath -nocerts -nodes -out $keyPath -passin pass:survey123 2>$null
    & openssl pkcs12 -in $certPath -nokeys -out $crtPath -passin pass:survey123 2>$null
} else {
    # Install OpenSSL via Chocolatey
    choco install openssl -y --no-progress
    refreshenv
    $opensslPath = (Get-Command openssl -ErrorAction SilentlyContinue).Source
    if ($opensslPath) {
        & $opensslPath pkcs12 -in $certPath -nocerts -nodes -out $keyPath -passin pass:survey123 2>$null
        & $opensslPath pkcs12 -in $certPath -nokeys -out $crtPath -passin pass:survey123 2>$null
    }
}

Write-Host '  OK: SSL certificate generated' -ForegroundColor Green

# Write nginx.conf with SSL
Write-Host '  Writing nginx.conf...' -ForegroundColor Yellow
$confPath = Join-Path $nginxPath 'conf\nginx.conf'

$confLines = @(
    'worker_processes  1;',
    '',
    'events {',
    '    worker_connections  1024;',
    '}',
    '',
    'http {',
    '    include       mime.types;',
    '    default_type  application/octet-stream;',
    '    sendfile      on;',
    '    keepalive_timeout  65;',
    '    client_max_body_size 50M;',
    '',
    '    # Redirect HTTP to HTTPS',
    '    server {',
    '        listen 80;',
    "        server_name $DOMAIN www.$DOMAIN;",
    '        return 301 https://$host$request_uri;',
    '    }',
    '',
    '    # HTTPS Server',
    '    server {',
    '        listen 443 ssl;',
    "        server_name $DOMAIN www.$DOMAIN;",
    '',
    "        ssl_certificate     ssl/$DOMAIN.crt;",
    "        ssl_certificate_key  ssl/$DOMAIN.key;",
    '        ssl_protocols TLSv1.2 TLSv1.3;',
    '',
    '        location / {',
    '            proxy_pass http://127.0.0.1:8080;',
    '            proxy_set_header Host $host;',
    '            proxy_set_header X-Real-IP $remote_addr;',
    '            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;',
    '            proxy_set_header X-Forwarded-Proto $scheme;',
    '        }',
    '',
    '        location /miniapp/ {',
    '            proxy_pass http://127.0.0.1:5000/;',
    '            proxy_set_header Host $host;',
    '            proxy_set_header X-Real-IP $remote_addr;',
    '        }',
    '',
    '        location /api/ {',
    '            proxy_pass http://127.0.0.1:5000/api/;',
    '            proxy_set_header Host $host;',
    '        }',
    '    }',
    '}'
)

$confContent = $confLines -join "`r`n"
$enc = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($confPath, $confContent, $enc)
Write-Host '  OK: nginx.conf written' -ForegroundColor Green

# --- Step 4: Create Services ---
Write-Host ''
Write-Host '=== Step 4: Create Services ===' -ForegroundColor Cyan

if (-not (Test-Path "$INSTALL_DIR\logs")) { New-Item -ItemType Directory -Path "$INSTALL_DIR\logs" -Force | Out-Null }

# MiniApp
nssm install SurveyMiniApp $pythonExe "miniapp.py" | Out-Null
nssm set SurveyMiniApp AppDirectory $INSTALL_DIR | Out-Null
nssm set SurveyMiniApp AppStdout "$INSTALL_DIR\logs\miniapp-out.log" | Out-Null
nssm set SurveyMiniApp AppStderr "$INSTALL_DIR\logs\miniapp-err.log" | Out-Null
nssm set SurveyMiniApp Start SERVICE_AUTO_START | Out-Null
Write-Host '  OK: SurveyMiniApp' -ForegroundColor Green

# Website
nssm install SurveyWebsite $pythonExe "website.py" | Out-Null
nssm set SurveyWebsite AppDirectory $INSTALL_DIR | Out-Null
nssm set SurveyWebsite AppStdout "$INSTALL_DIR\logs\website-out.log" | Out-Null
nssm set SurveyWebsite AppStderr "$INSTALL_DIR\logs\website-err.log" | Out-Null
nssm set SurveyWebsite Start SERVICE_AUTO_START | Out-Null
Write-Host '  OK: SurveyWebsite' -ForegroundColor Green

# Bot
nssm install SurveyBot $pythonExe "bot.py" | Out-Null
nssm set SurveyBot AppDirectory $INSTALL_DIR | Out-Null
nssm set SurveyBot AppStdout "$INSTALL_DIR\logs\bot-out.log" | Out-Null
nssm set SurveyBot AppStderr "$INSTALL_DIR\logs\bot-err.log" | Out-Null
nssm set SurveyBot Start SERVICE_AUTO_START | Out-Null
Write-Host '  OK: SurveyBot' -ForegroundColor Green

# --- Step 5: Start Services ---
Write-Host ''
Write-Host '=== Step 5: Start Services ===' -ForegroundColor Cyan

Start-Service SurveyMiniApp
Start-Sleep 2
Start-Service SurveyWebsite
Start-Sleep 2
Start-Service SurveyBot
Start-Sleep 2

Push-Location $nginxPath
$oldEAP = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try { & .\nginx.exe -t 2>&1 | Out-Null } catch {}
$ErrorActionPreference = $oldEAP
Start-Process -FilePath '.\nginx.exe' -WindowStyle Hidden
Pop-Location
Start-Sleep 2
Write-Host 'OK: All services started' -ForegroundColor Green

# --- Summary ---
Write-Host ''
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host '  DEPLOYMENT COMPLETE!' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Cyan
Write-Host ''
Write-Host 'Access URLs:' -ForegroundColor Yellow
Write-Host "  Website:    https://$DOMAIN/" -ForegroundColor White
Write-Host "  Admin:      https://$DOMAIN/admin/login" -ForegroundColor White
Write-Host "  Mobile App: https://$DOMAIN/app" -ForegroundColor White
Write-Host "  MiniApp:    https://$DOMAIN/miniapp" -ForegroundColor White
Write-Host "  Download:   https://$DOMAIN/download-app" -ForegroundColor White
Write-Host ''
Write-Host 'Note: SSL uses self-signed certificate.' -ForegroundColor Yellow
Write-Host 'For production, use Let''s Encrypt or Cloudflare SSL.' -ForegroundColor Yellow
Write-Host ''
