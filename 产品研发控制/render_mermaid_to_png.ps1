# 将两个流程图目录中的 mermaid 代码块渲染成 PNG
# 用法: powershell -ExecutionPolicy Bypass -File render_mermaid_to_png.ps1

$ErrorActionPreference = "Stop"

$root = "d:\Code\public\NF-SafetyHub\产品研发控制"
$dirs = @(
    (Join-Path $root "机制流程图"),
    (Join-Path $root "科普流程图")
)

# 创建 puppeteer config，关掉沙箱（Windows 容器/CI 友好）
# 用 .NET WriteAllText 写无 BOM 的 UTF-8
$puppeteerConfig = Join-Path $env:TEMP "mmdc_puppeteer.json"
[System.IO.File]::WriteAllText($puppeteerConfig, '{ "args": ["--no-sandbox"] }', (New-Object System.Text.UTF8Encoding($false)))

foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        Write-Host "skip (not exist): $dir"
        continue
    }
    $pngDir = Join-Path $dir "png"
    New-Item -ItemType Directory -Force -Path $pngDir | Out-Null

    $mdFiles = Get-ChildItem -Path $dir -Filter *.md -File | Where-Object { $_.Name -ne "README.md" }
    foreach ($md in $mdFiles) {
        $content = Get-Content -Path $md.FullName -Raw -Encoding utf8
        # 提取第一个 ```mermaid ... ``` 代码块
        $pattern = '(?s)```mermaid\s*(.*?)```'
        $m = [regex]::Match($content, $pattern)
        if (-not $m.Success) {
            Write-Host "no mermaid block: $($md.Name)"
            continue
        }
        $mermaid = $m.Groups[1].Value.Trim()
        $base = [System.IO.Path]::GetFileNameWithoutExtension($md.Name)
        $mmd = Join-Path $env:TEMP ("safetyhub_" + $base + ".mmd")
        $png = Join-Path $pngDir ($base + ".png")

        [System.IO.File]::WriteAllText($mmd, $mermaid, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host ">>> rendering $($md.Name) -> $png"
        npx --yes -p @mermaid-js/mermaid-cli mmdc `
            -i $mmd `
            -o $png `
            -b white `
            -w 2400 `
            -s 3 `
            -p $puppeteerConfig
        if ($LASTEXITCODE -ne 0) {
            Write-Host "FAILED on $($md.Name) (exit=$LASTEXITCODE)" -ForegroundColor Red
        }
    }
}

Write-Host "done."
