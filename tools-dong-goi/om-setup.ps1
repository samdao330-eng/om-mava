# Cài những gì OpenMontage cần trên Windows, chạy trong thư mục OM.
# OM MAVA Updater (nút Cài / Cập nhật / Cài công cụ) gọi script này. Không cần quyền quản trị:
# ffmpeg (BtbN, kiểm SHA-256), Node (nodejs.org, kiểm SHA-256), uv (astral) tải vào %USERPROFILE%\.openmontage\tools
# và thêm vào PATH của người dùng. Máy đã có sẵn thì dùng luôn. Không đụng .env đã có, projects\ hay phim.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Set-Location -LiteralPath $PSScriptRoot

function Say($m) { Write-Output ""; Write-Output "==> $m" }
function Warn($m) { Write-Output "[!] $m" }

$Tools = Join-Path $env:USERPROFILE '.openmontage\tools'
$UvBin = Join-Path $env:USERPROFILE '.local\bin'
New-Item -ItemType Directory -Force -Path $Tools, $UvBin | Out-Null

function Add-UserPath($dir) {
  $cur = [Environment]::GetEnvironmentVariable('Path', 'User')
  if (-not $cur) { $cur = '' }
  if (($cur -split ';') -notcontains $dir) {
    [Environment]::SetEnvironmentVariable('Path', ($dir + ';' + $cur).TrimEnd(';'), 'User')
  }
  if (($env:Path -split ';') -notcontains $dir) { $env:Path = "$dir;$env:Path" }
}
function Have($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Check-Sha($file, $want) {
  $got = (Get-FileHash -Algorithm SHA256 -LiteralPath $file).Hash.ToLower()
  if ($got -ne $want.ToLower()) { Remove-Item -Force $file; throw "Sai mã SHA-256: $file — bỏ, không cài" }
}
function Get-Text($url) { (Invoke-WebRequest -UseBasicParsing -Uri $url).Content }
function Node-Major { try { [int]((& node -v) -replace '^v(\d+).*', '$1') } catch { 0 } }

# đường dẫn công cụ đã cài trước đó (lần chạy khác)
foreach ($d in @("$Tools\ffmpeg\bin", "$Tools\node", $UvBin)) { if (Test-Path $d) { Add-UserPath $d } }

Say 'Công cụ: ffmpeg, Node, uv'
if (-not (Have ffmpeg) -or -not (Have ffprobe)) {
  $base = 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest'
  $line = (Get-Text "$base/checksums.sha256") -split "`n" |
    Where-Object { $_ -match ' ffmpeg-n[\d.]+-latest-win64-gpl-[\d.]+\.zip$' } |
    Sort-Object { [version](($_ -replace '.*-gpl-([\d.]+)\.zip$', '$1') + '.0') } | Select-Object -Last 1
  if (-not $line) { throw 'Không đọc được danh sách ffmpeg' }
  $sum, $name = $line.Trim() -split '\s+'
  Say "Tải ffmpeg $name"
  $zip = Join-Path $env:TEMP $name
  Invoke-WebRequest -UseBasicParsing -Uri "$base/$name" -OutFile $zip
  Check-Sha $zip $sum
  $tmp = Join-Path $env:TEMP 'om-ffmpeg'
  Remove-Item -Recurse -Force $tmp, "$Tools\ffmpeg" -ErrorAction SilentlyContinue
  Expand-Archive -LiteralPath $zip -DestinationPath $tmp
  Move-Item (Get-ChildItem $tmp -Directory | Select-Object -First 1).FullName "$Tools\ffmpeg"
  Remove-Item -Recurse -Force $tmp, $zip
  Add-UserPath "$Tools\ffmpeg\bin"
}
if ((Node-Major) -lt 20) {
  $base = 'https://nodejs.org/dist/latest-v22.x'
  $line = (Get-Text "$base/SHASUMS256.txt") -split "`n" | Where-Object { $_ -match ' node-v[\d.]+-win-x64\.zip$' } | Select-Object -First 1
  if (-not $line) { throw 'Không đọc được danh sách Node' }
  $sum, $name = $line.Trim() -split '\s+'
  Say "Tải Node $name"
  $zip = Join-Path $env:TEMP $name
  Invoke-WebRequest -UseBasicParsing -Uri "$base/$name" -OutFile $zip
  Check-Sha $zip $sum
  $tmp = Join-Path $env:TEMP 'om-node'
  Remove-Item -Recurse -Force $tmp, "$Tools\node" -ErrorAction SilentlyContinue
  Expand-Archive -LiteralPath $zip -DestinationPath $tmp
  Move-Item (Get-ChildItem $tmp -Directory | Select-Object -First 1).FullName "$Tools\node"
  Remove-Item -Recurse -Force $tmp, $zip
  Add-UserPath "$Tools\node"
}
if (-not (Have uv)) {
  Say 'Cài uv'
  $env:UV_NO_MODIFY_PATH = '1'
  Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
  Add-UserPath $UvBin
}
Write-Output ("ffmpeg: " + ((& ffmpeg -version | Select-Object -First 1) -split ' ')[2] + "   Node: " + (& node -v) + "   uv: " + (& uv --version))

Say 'Môi trường Python 3.12 + requirements.txt'
& uv venv --allow-existing --python 3.12 .venv; if ($LASTEXITCODE) { throw 'uv venv lỗi' }
& uv pip install --python .venv -r requirements.txt
if ($LASTEXITCODE) {
  Warn 'Tải thư viện lỗi (mạng?) — thử lại sau 5 giây'; Start-Sleep 5
  & uv pip install --python .venv -r requirements.txt; if ($LASTEXITCODE) { throw 'Cài thư viện Python lỗi' }
}
$py = '.venv\Scripts\python.exe'
Say 'Tăng tốc GPU nếu máy có card hợp (bỏ qua nếu không)'
& $py -m lib.accel_setup --json | Out-Null
if ($LASTEXITCODE) { Warn 'accel_setup lỗi — OM vẫn chạy bằng CPU.' }

if (-not (Test-Path .env)) { Copy-Item .env.example .env }

Say 'Remotion (dựng chữ/caption)'
Push-Location remotion-composer
& npm.cmd ci --no-audit --no-fund
if ($LASTEXITCODE) { Warn 'npm ci lỗi — bấm Cài công cụ để thử lại' }
Pop-Location

Say 'Kiểm tra nhanh'
& $py -c "import yaml; print('Python OK')"
& $py -m tools list | Out-Null
if ($LASTEXITCODE) { Warn 'python -m tools list lỗi' } else { Write-Output 'Công cụ OM: OK' }
Write-Output ("OM v" + (Get-Content VERSION).Trim() + " — cài xong.")
