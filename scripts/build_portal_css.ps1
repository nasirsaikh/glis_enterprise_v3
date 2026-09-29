$ErrorActionPreference = "Stop"

$cssDir = Join-Path $PSScriptRoot "..\static\css"
$cssDir = (Resolve-Path $cssDir).Path

$tailwind = Join-Path $cssDir "tailwindcss.exe"
$daisy = Join-Path $cssDir "daisyui.mjs"
$daisyTheme = Join-Path $cssDir "daisyui-theme.mjs"
$input = Join-Path $cssDir "input.css"
$output = Join-Path $cssDir "output.css"

if (-not (Test-Path $tailwind)) {
    Write-Host "Downloading Tailwind CSS standalone..."
    Invoke-WebRequest -Uri "https://github.com/tailwindlabs/tailwindcss/releases/download/v4.3.3/tailwindcss-windows-x64.exe" -OutFile $tailwind
}

if (-not (Test-Path $daisy)) {
    Write-Host "Downloading daisyUI..."
    Invoke-WebRequest -Uri "https://github.com/saadeghi/daisyui/releases/download/v5.7.46/daisyui.mjs" -OutFile $daisy
}

if (-not (Test-Path $daisyTheme)) {
    Invoke-WebRequest -Uri "https://github.com/saadeghi/daisyui/releases/download/v5.7.46/daisyui-theme.mjs" -OutFile $daisyTheme
}

Write-Host "Building standard Tailwind + daisyUI portal CSS..."
& $tailwind -i $input -o $output

if ($LASTEXITCODE -ne 0) {
    throw "Tailwind/daisyUI build failed."
}

Write-Host "Portal CSS generated: $output"
