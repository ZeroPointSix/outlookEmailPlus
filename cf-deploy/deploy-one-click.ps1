<#
.SYNOPSIS
  Windows 一键脚本：自动部署 Cloudflare 临时邮箱（仅收件）
  基于开源项目：https://github.com/dreamhunter2333/cloudflare_temp_email

.DESCRIPTION
  读取同目录下的 one-click.config.jsonc，自动完成：
    - 环境预检（Node.js / pnpm|npm / wrangler）
    - 下载官方源码（或复用本地源码）
    - 创建 D1 数据库并初始化 Schema
    - 生成 wrangler.toml（注入域名、密码、JWT_SECRET 等）
    - 部署后端 Worker（含自定义域名绑定）
    - 构建并部署前端（Cloudflare Pages）

.PARAMETER PreflightOnly
  只做环境预检，不执行任何部署

.PARAMETER PrepareOnly
  生成配置文件（wrangler.toml）后退出，不正式部署

.PARAMETER RefreshSource
  强制重新下载官方源码（覆盖本地已有源码）

.PARAMETER SourceRoot
  使用你手动下载的源码目录（跳过自动下载）

.PARAMETER SkipInstall
  跳过 npm/pnpm install（源码已安装过依赖时使用）

.EXAMPLE
  # 只做环境预检
  pwsh -File .\deploy-one-click.ps1 -PreflightOnly

  # 生成配置确认后不部署
  pwsh -File .\deploy-one-click.ps1 -PrepareOnly

  # 正式部署
  pwsh -File .\deploy-one-click.ps1

  # 强制重新拉取源码
  pwsh -File .\deploy-one-click.ps1 -RefreshSource

  # 使用本地已有源码
  pwsh -File .\deploy-one-click.ps1 -SourceRoot D:\cloudflare_temp_email

  # 跳过依赖安装
  pwsh -File .\deploy-one-click.ps1 -SkipInstall
#>

param(
    [switch]$PreflightOnly,
    [switch]$PrepareOnly,
    [switch]$RefreshSource,
    [string]$SourceRoot = "",
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# ─────────────────────────────────────────────────────────────
# 自动检测并配置代理（Windows 注册表）
# ─────────────────────────────────────────────────────────────
function Set-ProxyIfAvailable {
    try {
        $regKey  = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction SilentlyContinue
        $enabled = $regKey.ProxyEnable
        $server  = $regKey.ProxyServer
        if ($enabled -eq 1 -and $server) {
            # 仅取 HTTP 代理（兼容 "127.0.0.1:7890" 或 "http=127.0.0.1:7890;https=..." 格式）
            $httpProxy = $server
            if ($server -match 'http=([^;]+)') { $httpProxy = $Matches[1] }
            if ($httpProxy -notmatch '^http') { $httpProxy = "http://$httpProxy" }

            $env:HTTP_PROXY  = $httpProxy
            $env:HTTPS_PROXY = $httpProxy
            $env:http_proxy  = $httpProxy
            $env:https_proxy = $httpProxy

            # 配置 git 代理
            git config --global http.proxy  $httpProxy 2>$null
            git config --global https.proxy $httpProxy 2>$null

            # 配置 npm/pnpm 代理
            npm config set proxy       $httpProxy 2>$null
            npm config set https-proxy $httpProxy 2>$null

            Write-Ok "已自动配置代理: $httpProxy"
            return $httpProxy
        }
    } catch {}
    return $null
}

$DetectedProxy = Set-ProxyIfAvailable

# ─────────────────────────────────────────────────────────────
# 颜色输出工具函数
# ─────────────────────────────────────────────────────────────
function Write-Ok   { param($msg) Write-Host "[  OK  ] $msg" -ForegroundColor Green }
function Write-Info { param($msg) Write-Host "[ INFO ] $msg" -ForegroundColor Cyan }
function Write-Warn { param($msg) Write-Host "[ WARN ] $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host "[ FAIL ] $msg" -ForegroundColor Red }
function Write-Step { param($msg) Write-Host "`n===== $msg =====" -ForegroundColor Magenta }

# ─────────────────────────────────────────────────────────────
# 解析 JSONC（先去除注释，再用 ConvertFrom-Json）
# ─────────────────────────────────────────────────────────────
function Read-Jsonc {
    param([string]$Path)
    $raw = Get-Content $Path -Raw -Encoding UTF8
    # 去除单行注释 // ...
    $raw = [regex]::Replace($raw, '//[^\r\n]*', '')
    # 去除多行注释 /* ... */
    $raw = [regex]::Replace($raw, '/\*[\s\S]*?\*/', '')
    # 去除末尾逗号（JSON5 兼容）
    $raw = [regex]::Replace($raw, ',(\s*[}\]])', '$1')
    return $raw | ConvertFrom-Json
}

# ─────────────────────────────────────────────────────────────
# 执行命令，失败则抛出异常
# ─────────────────────────────────────────────────────────────
function Invoke-Cmd {
    param(
        [string]$Cmd,
        [string]$Desc = "",
        [string]$WorkDir = ""
    )
    if ($Desc) { Write-Info ">>> $Desc" }
    Write-Info "    $Cmd"
    $prevPwd = $PWD
    if ($WorkDir -and (Test-Path $WorkDir)) {
        Set-Location $WorkDir
    }
    Invoke-Expression $Cmd
    $exitCode = $LASTEXITCODE
    if ($WorkDir) { Set-Location $prevPwd }
    if ($exitCode -and $exitCode -ne 0) {
        Write-Fail "命令失败 (exit $exitCode): $Cmd"
        throw "命令执行失败，请查看上方错误信息"
    }
}

# ─────────────────────────────────────────────────────────────
# 生成随机 JWT Secret（32字节 Base64）
# ─────────────────────────────────────────────────────────────
function New-JwtSecret {
    $bytes = [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
    return [Convert]::ToBase64String($bytes)
}

# ─────────────────────────────────────────────────────────────
# STEP 0: 读取配置
# ─────────────────────────────────────────────────────────────
Write-Step "STEP 0: 读取配置"

$ConfigPath = Join-Path $ScriptDir "one-click.config.jsonc"
if (-not (Test-Path $ConfigPath)) {
    Write-Fail "配置文件不存在: $ConfigPath"
    Write-Fail "请先创建 one-click.config.jsonc（参考项目 README）"
    exit 1
}

$Config = Read-Jsonc $ConfigPath

# 读取必填项
$ProjectName   = if ($Config.projectName)      { $Config.projectName }      else { "my-tempmail" }
$MailDomain    = $Config.mailDomain
$FrontendSub   = if ($Config.frontendSubdomain) { $Config.frontendSubdomain } else { "mail" }
$ApiSub        = if ($Config.apiSubdomain)      { $Config.apiSubdomain }      else { "email-api" }
$AdminPassword = $Config.adminPassword

if (-not $MailDomain) {
    Write-Fail "mailDomain 未配置，请在 one-click.config.jsonc 中填写收件域名"
    exit 1
}
if (-not $AdminPassword -or $AdminPassword -eq "change-me-please!!!") {
    Write-Fail "adminPassword 未配置或仍为默认值，请修改 one-click.config.jsonc"
    exit 1
}

# 派生名称
$ApiDomain      = "$ApiSub.$MailDomain"
$FrontendDomain = "$FrontendSub.$MailDomain"
$WorkerName     = "$ProjectName-api"
$FrontendName   = "$ProjectName-frontend"
$DbName         = "$ProjectName-db"

Write-Ok "配置读取成功"
Write-Info "  projectName    : $ProjectName"
Write-Info "  mailDomain     : $MailDomain"
Write-Info "  apiDomain      : $ApiDomain  (后端 Worker)"
Write-Info "  frontendDomain : $FrontendDomain  (前端 Pages)"
Write-Info "  workerName     : $WorkerName"
Write-Info "  dbName         : $DbName"

# ─────────────────────────────────────────────────────────────
# STEP 1: 环境预检
# ─────────────────────────────────────────────────────────────
Write-Step "STEP 1: 环境预检"

$CheckFailed = $false

# Node.js
try {
    $NodeVer = (node --version 2>&1).ToString().Trim()
    Write-Ok "Node.js 已安装: $NodeVer"
} catch {
    Write-Fail "Node.js 未安装，请先安装 https://nodejs.org"
    $CheckFailed = $true
}

# pnpm（优先）或 npm
$PkgMgr = "npm"
try {
    $PnpmVer = (pnpm --version 2>&1).ToString().Trim()
    if ($LASTEXITCODE -eq 0 -and $PnpmVer -match '^\d') {
        Write-Ok "pnpm 已安装: $PnpmVer"
        $PkgMgr = "pnpm"
    } else {
        Write-Warn "pnpm 不可用，将使用 npm"
    }
} catch {
    Write-Warn "pnpm 未安装，将使用 npm"
}

# wrangler（通过 npx）
try {
    $WrVer = (npx wrangler --version 2>&1).ToString().Trim()
    Write-Ok "wrangler 可用: $WrVer"
} catch {
    Write-Warn "wrangler 首次运行时 npx 会自动安装，如遇问题请先执行: npm install -g wrangler"
}

# git
$HasGit = $false
try {
    $GitVer = (git --version 2>&1).ToString().Trim()
    Write-Ok "git 已安装: $GitVer"
    $HasGit = $true
} catch {
    Write-Warn "git 未安装，将通过 zip 下载源码（功能正常，但速度稍慢）"
}

if ($CheckFailed) {
    Write-Fail "预检发现问题，请先解决上述错误后再运行脚本"
    exit 1
}

if ($PreflightOnly) {
    Write-Ok "预检完成（-PreflightOnly 模式），脚本退出"
    exit 0
}

# ─────────────────────────────────────────────────────────────
# STEP 2: 获取源码
# ─────────────────────────────────────────────────────────────
Write-Step "STEP 2: 获取源码"

$GithubRepo     = "https://github.com/dreamhunter2333/cloudflare_temp_email"
$DefaultSrcDir  = Join-Path $ScriptDir "cloudflare_temp_email"

if ($SourceRoot) {
    Write-Info "使用指定源码目录: $SourceRoot"
    if (-not (Test-Path $SourceRoot)) {
        Write-Fail "指定源码目录不存在: $SourceRoot"
        exit 1
    }
    $SrcDir = $SourceRoot
} else {
    $SrcDir = $DefaultSrcDir
    if ($RefreshSource -and (Test-Path $SrcDir)) {
        Write-Info "(-RefreshSource) 删除旧源码: $SrcDir"
        Remove-Item $SrcDir -Recurse -Force
    }
    if (-not (Test-Path $SrcDir)) {
        if ($HasGit) {
            Write-Info "通过 git clone 下载源码..."
            Invoke-Cmd "git clone --depth 1 `"$GithubRepo`" `"$SrcDir`"" "克隆 cloudflare_temp_email 仓库"
        } else {
            Write-Info "通过 zip 下载源码（需要访问 GitHub）..."
            $ZipUrl  = "https://github.com/dreamhunter2333/cloudflare_temp_email/archive/refs/heads/main.zip"
            $ZipPath = Join-Path $ScriptDir "cf_temp_email_src.zip"
            Write-Info "下载: $ZipUrl"
            Invoke-WebRequest -Uri $ZipUrl -OutFile $ZipPath -UseBasicParsing
            Write-Info "解压中..."
            Expand-Archive -Path $ZipPath -DestinationPath $ScriptDir -Force
            $ExtractedDir = Join-Path $ScriptDir "cloudflare_temp_email-main"
            if (Test-Path $ExtractedDir) {
                Rename-Item $ExtractedDir $SrcDir -Force
            }
            Remove-Item $ZipPath -Force
        }
        Write-Ok "源码已下载: $SrcDir"
    } else {
        Write-Ok "复用已有源码: $SrcDir"
    }
}

$WorkerDir    = Join-Path $SrcDir "worker"
$FrontendDir  = Join-Path $SrcDir "frontend"
$DbSchemaPath = Join-Path $SrcDir "db\schema.sql"

foreach ($dir in @($WorkerDir, $FrontendDir)) {
    if (-not (Test-Path $dir)) {
        Write-Fail "源码目录结构异常，未找到: $dir"
        exit 1
    }
}
if (-not (Test-Path $DbSchemaPath)) {
    Write-Fail "数据库 schema 文件不存在: $DbSchemaPath"
    exit 1
}
Write-Ok "源码目录验证通过"

# ─────────────────────────────────────────────────────────────
# STEP 3: 生成 wrangler.toml（初步，D1 ID 占位）
# ─────────────────────────────────────────────────────────────
Write-Step "STEP 3: 生成 worker/wrangler.toml"

$WranglerToml = Join-Path $WorkerDir "wrangler.toml"
$JwtSecret    = New-JwtSecret

# 构造最小化的 wrangler.toml（严格模式：禁匿名、VIP 角色）
$WranglerContent = @"
name = "$WorkerName"
main = "src/worker.ts"
compatibility_date = "2025-04-01"
compatibility_flags = [ "nodejs_compat" ]
keep_vars = true

# 自定义域名（需域名已托管到 Cloudflare）
routes = [
    { pattern = "$ApiDomain", custom_domain = true },
]

[vars]
PREFIX = "tmp"
DEFAULT_DOMAINS = ["$MailDomain"]
DOMAINS = ["$MailDomain"]
ADMIN_PASSWORDS = ["$AdminPassword"]
JWT_SECRET = "$JwtSecret"
ENABLE_USER_CREATE_EMAIL = true
DISABLE_ANONYMOUS_USER_CREATE_EMAIL = true
USER_DEFAULT_ROLE = "vip"
ENABLE_USER_DELETE_EMAIL = true
ENABLE_AUTO_REPLY = false
FRONTEND_URL = "https://$FrontendDomain"

[[d1_databases]]
binding = "DB"
database_name = "$DbName"
database_id = "__D1_ID_PLACEHOLDER__"
"@

$WranglerContent | Set-Content $WranglerToml -Encoding UTF8
Write-Ok "wrangler.toml 初始文件已写入（D1 ID 将在创建数据库后自动填充）"
Write-Info "  路径: $WranglerToml"

if ($PrepareOnly) {
    Write-Info ""
    Write-Info "(-PrepareOnly) 配置已生成，脚本退出"
    Write-Info "检查完配置后，运行以下命令正式部署："
    Write-Info "  pwsh -File .\deploy-one-click.ps1"
    exit 0
}

# ─────────────────────────────────────────────────────────────
# STEP 4: Cloudflare 登录
# ─────────────────────────────────────────────────────────────
Write-Step "STEP 4: Cloudflare 登录"

# 先检查是否已登录（wrangler whoami 成功则跳过 login）
Set-Location $WorkerDir
$WhoAmI = (npx wrangler whoami 2>&1) | Out-String
if ($WhoAmI -match '@' -or $WhoAmI -match 'logged in' -or $WhoAmI -match 'You are') {
    Write-Ok "已检测到 Cloudflare 登录状态，跳过 login 步骤"
    Write-Info ($WhoAmI.Trim() -split "`n" | Select-Object -First 3 | Out-String)
} else {
    Write-Info "即将通过 wrangler login 打开浏览器授权，请在浏览器中完成 Cloudflare 登录..."
    Write-Warn "注意：请先确认域名 $MailDomain 已托管到 Cloudflare！"
    Write-Info "若浏览器未自动打开，请手动访问打印的 OAuth URL"
    Invoke-Cmd "npx wrangler login" "Cloudflare 登录授权"
    Write-Ok "登录成功"
}

# ─────────────────────────────────────────────────────────────
# STEP 5: 安装 Worker 依赖
# ─────────────────────────────────────────────────────────────
if (-not $SkipInstall) {
    Write-Step "STEP 5: 安装 Worker 依赖"
    Set-Location $WorkerDir
    if ($PkgMgr -eq "pnpm") {
        Invoke-Cmd "pnpm install --frozen-lockfile" "安装 Worker 依赖 (pnpm)"
    } else {
        Invoke-Cmd "npm install" "安装 Worker 依赖 (npm)"
    }
    Write-Ok "Worker 依赖安装完成"
} else {
    Write-Warn "跳过 Worker 依赖安装（-SkipInstall）"
}

# ─────────────────────────────────────────────────────────────
# STEP 6: 创建 D1 数据库
# ─────────────────────────────────────────────────────────────
Write-Step "STEP 6: 创建 D1 数据库: $DbName"
Set-Location $WorkerDir

# 先查看是否已存在
$D1ListOutput = (npx wrangler d1 list 2>&1) | Out-String
$D1Id = $null

if ($D1ListOutput -match "$DbName\s+\|\s+([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})") {
    $D1Id = $Matches[1]
    Write-Warn "D1 数据库 '$DbName' 已存在，复用 ID: $D1Id"
} else {
    Write-Info "创建新 D1 数据库..."
    $D1CreateOutput = (npx wrangler d1 create $DbName 2>&1) | Out-String
    Write-Info $D1CreateOutput

    # 从输出提取 database_id
    if ($D1CreateOutput -match 'database_id\s*=\s*"([a-f0-9-]+)"') {
        $D1Id = $Matches[1]
    } elseif ($D1CreateOutput -match '([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})') {
        $D1Id = $Matches[1]
    }

    if (-not $D1Id) {
        Write-Warn "无法自动提取 D1 database_id，请从上方输出复制 UUID"
        $D1Id = (Read-Host "请输入 database_id（UUID 格式）").Trim()
    }
    Write-Ok "D1 数据库创建成功，ID: $D1Id"
}

# 将真实 D1 ID 填入 wrangler.toml
$TomlContent = Get-Content $WranglerToml -Raw -Encoding UTF8
$TomlContent = $TomlContent -replace '__D1_ID_PLACEHOLDER__', $D1Id
$TomlContent | Set-Content $WranglerToml -Encoding UTF8
Write-Ok "wrangler.toml 已更新 database_id = $D1Id"

# ─────────────────────────────────────────────────────────────
# STEP 7: 初始化 D1 数据库 Schema
# ─────────────────────────────────────────────────────────────
Write-Step "STEP 7: 初始化数据库 Schema"
Set-Location $WorkerDir

Write-Info "执行 schema.sql → D1 数据库 $DbName"
Invoke-Cmd "npx wrangler d1 execute `"$DbName`" --remote --file=`"$DbSchemaPath`"" "初始化 D1 schema"
Write-Ok "数据库 Schema 初始化完成"

# ─────────────────────────────────────────────────────────────
# STEP 8: 部署后端 Worker
# ─────────────────────────────────────────────────────────────
Write-Step "STEP 8: 部署后端 Worker: $WorkerName"
Set-Location $WorkerDir
Invoke-Cmd "npx wrangler deploy" "部署后端 Worker"
Write-Ok "后端 Worker 部署成功: https://$ApiDomain"

# ─────────────────────────────────────────────────────────────
# STEP 9: 构建前端
# ─────────────────────────────────────────────────────────────
Write-Step "STEP 9: 构建前端"
Set-Location $FrontendDir

# 写入前端构建环境变量
$EnvFile    = Join-Path $FrontendDir ".env.production"
$EnvContent = "VITE_API_BASE=https://$ApiDomain`nVITE_IS_TELEGRAM=false"
$EnvContent | Set-Content $EnvFile -Encoding UTF8
Write-Ok "前端 .env.production 已写入"
Write-Info "  VITE_API_BASE=https://$ApiDomain"

if (-not $SkipInstall) {
    if ($PkgMgr -eq "pnpm") {
        Invoke-Cmd "pnpm install --frozen-lockfile" "安装前端依赖 (pnpm)"
    } else {
        Invoke-Cmd "npm install" "安装前端依赖 (npm)"
    }
    Write-Ok "前端依赖安装完成"
} else {
    Write-Warn "跳过前端依赖安装（-SkipInstall）"
}

if ($PkgMgr -eq "pnpm") {
    Invoke-Cmd "pnpm build" "构建前端"
} else {
    Invoke-Cmd "npm run build" "构建前端"
}
Write-Ok "前端构建完成"

# ─────────────────────────────────────────────────────────────
# STEP 10: 部署前端到 Cloudflare Pages
# ─────────────────────────────────────────────────────────────
Write-Step "STEP 10: 部署前端到 Cloudflare Pages: $FrontendName"
Set-Location $FrontendDir

$DistDir = Join-Path $FrontendDir "dist"
if (-not (Test-Path $DistDir)) {
    Write-Fail "前端构建产物目录不存在: $DistDir"
    Write-Fail "请检查 Step 9 的构建是否成功"
    exit 1
}

Invoke-Cmd "npx wrangler pages deploy `"$DistDir`" --project-name `"$FrontendName`" --branch main --commit-dirty=true" "部署前端到 Cloudflare Pages"
Write-Ok "前端 Pages 部署成功"

# ─────────────────────────────────────────────────────────────
# 完成：打印汇总信息
# ─────────────────────────────────────────────────────────────
$Separator = "=" * 62
Write-Host ""
Write-Host $Separator -ForegroundColor Magenta
Write-Host "  部署完成！" -ForegroundColor Green
Write-Host $Separator -ForegroundColor Magenta
Write-Host ""
Write-Host "  后端 Worker  : https://$ApiDomain" -ForegroundColor Cyan
Write-Host "  前端访问     : https://$FrontendDomain" -ForegroundColor Cyan
Write-Host "  管理员面板   : https://$FrontendDomain/admin" -ForegroundColor Cyan
Write-Host "  管理员密码   : $AdminPassword" -ForegroundColor Yellow
Write-Host ""
Write-Host $Separator -ForegroundColor Yellow
Write-Host "  还需在 Cloudflare 面板手动完成：" -ForegroundColor Yellow
Write-Host $Separator -ForegroundColor Yellow
Write-Host "  1. Email Routing → 为域名 [$MailDomain] 开启收件"
Write-Host "     ( https://dash.cloudflare.com → Email → Email Routing )"
Write-Host ""
Write-Host "  2. 添加并验证目标转发邮箱（即你想收信的邮箱）"
Write-Host ""
Write-Host "  3. Catch-all 规则 → 'Send to a Worker' → 选择 [$WorkerName]"
Write-Host ""
Write-Host "  4. Pages 绑定自定义域名 [$FrontendDomain]"
Write-Host "     ( Dashboard → Pages → $FrontendName → Custom domains → Add )"
Write-Host ""
Write-Host $Separator -ForegroundColor Magenta
Write-Host "  * 如域名之前有旧 Worker/Pages/DNS 记录，请先在面板清理" -ForegroundColor Gray
Write-Host "  * 详细教程参考: https://github.com/dreamhunter2333/cloudflare_temp_email" -ForegroundColor Gray
Write-Host $Separator -ForegroundColor Magenta
Write-Host ""
