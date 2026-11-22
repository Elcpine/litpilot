# 把 dist\hf-space 推到 Hugging Face Space，并在被拒时自动重试 --force。
#
# 为什么要有这个脚本：在终端里手打 `git add -A && git commit -m "..." && git push space main`
# 太容易打错（这台机器上已经出现过 "gi add -Agit commi" 这种字符被吞掉的情况）。
# 现在只要在 dist\hf-space 里打 `.\push.ps1` 就行。
#
# 前置条件：dist\hf-space 里已经有 git 仓库和名为 space 的 remote（hf_space_export.py 会保留这两样）。

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

# 有 PATH 里的 git 就用 PATH 里的，没有就去找常见安装位置。
$git = "git"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    $found = $null
    foreach ($p in @("D:\user\Git\cmd\git.exe", "C:\Program Files\Git\cmd\git.exe", "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe")) {
        if (Test-Path $p) { $found = $p; break }
    }
    if (-not $found) {
        Write-Host "找不到 git。装一个：winget install --id Git.Git -e" -ForegroundColor Red
        exit 1
    }
    $git = $found
}

Write-Host "git = $git" -ForegroundColor DarkGray
if (-not (Test-Path ".git")) {
    Write-Host "这里没有 .git：先跑 python scripts\hf_space_export.py 生成目录，再 git init -b main + git remote add space <url>" -ForegroundColor Red
    exit 1
}

$remotes = & $git remote
if ($remotes -notcontains "space") {
    Write-Host "没有名为 space 的 remote。先执行：" -ForegroundColor Red
    Write-Host '  git remote add space https://huggingface.co/spaces/gloam05/litpilot'
    exit 1
}

Write-Host "`n== 待提交 ==" -ForegroundColor Cyan
& $git status --short
& $git add -A
& $git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "没有新改动，直接推送。"
} else {
    & $git commit -m "LitPilot: docker space"
    if ($LASTEXITCODE -ne 0) { Write-Host "commit 失败" -ForegroundColor Red; exit 1 }
}

Write-Host "`n== 推送（要输 Hugging Face 用户名 + write token，或走 SSH）==" -ForegroundColor Cyan
& $git push space main
if ($LASTEXITCODE -ne 0) {
    Write-Host "`npush 被拒：常见原因是本地这笔和远端不是一条线（Space 是静态模板建的那一笔）。" -ForegroundColor Yellow
    Write-Host "改用强制推送（本次就是要覆盖模板内容，属于预期）..." -ForegroundColor Yellow
    & $git push space main --force
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`n还是失败。对号入座：" -ForegroundColor Red
        Write-Host "  Could not resolve host / Could not connect to server / code=000  → 443 被墙，开代理，或改走 SSH"
        Write-Host "  改走 SSH：git remote set-url space git@hf.co:spaces/gloam05/litpilot"
        Write-Host "           `$env:GIT_SSH_COMMAND=`"ssh -i `$env:USERPROFILE\.ssh\hf_litpilot`""
        Write-Host "  Repository not found      → Space 名字/用户不对，或还没在网页上建"
        Write-Host "  Permission denied         → 公钥没加到 https://huggingface.co/settings/keys"
        Write-Host "  Authentication failed     → token 不是 write 权限"
        exit 1
    }
}

Write-Host "`n推完了。去 Space 页面看 Build 日志：出现 docker 字样、状态running，就说明从静态站切成了 Docker 应用。" -ForegroundColor Green
Write-Host "然后验：https://gloam05-litpilot.hf.space/api/health" -ForegroundColor Green
