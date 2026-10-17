# Builds two standalone Windows programs, one beta setup, a portable archive,
# and a separately downloadable optional speech component.
# Example: powershell -ExecutionPolicy Bypass -File buildtools\build-windows.ps1 -Repo user/DonathonTimer -Tag v0.9.4-beta1
[CmdletBinding()]
param(
    [string]$Repo = "",
    [string]$Tag = "v0.9.4-beta1",
    [string]$Python = "py -3.12"
)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Сборка EXE выполняется только в Windows.' }
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $root
try {
    $pyExe = Join-Path $root '.build-venv\Scripts\python.exe'
    if (-not (Test-Path $pyExe)) {
        $cmd = $Python -split '\s+'
        if ($cmd.Count -eq 1) { & $cmd[0] -m venv .build-venv }
        else { & $cmd[0] $cmd[1] -m venv .build-venv }
        if ($LASTEXITCODE -ne 0) { throw 'Не удалось создать виртуальное окружение Python 3.12' }
    }
    & $pyExe -m pip install --disable-pip-version-check --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'Ошибка обновления pip' }
    & $pyExe -m pip install --disable-pip-version-check -r requirements.txt -r requirements-speech.txt 'pyinstaller>=6.12,<7' 'Pillow>=11,<13'
    if ($LASTEXITCODE -ne 0) { throw 'Ошибка установки библиотек сборки' }

    # High-resolution Windows shortcut/setup icon from the approved logo.
    & $pyExe buildtools\make_icon.py
    if ($LASTEXITCODE -ne 0) { throw 'Ошибка создания иконки' }

    $assets = Join-Path $root 'src\donathon\assets'
    $templates = Join-Path $root 'src\donathon\templates'
    $releaseDir = Join-Path $root 'release'
    New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null
    Get-ChildItem $releaseDir -File | Where-Object { $_.Extension -in '.exe', '.zip' -or $_.Name -eq 'SHA256SUMS.txt' } | Remove-Item -Force
    $version = '0.9.4-beta1'

    # Optional self-contained speech worker; users only fetch it by opting in.
    & $pyExe -m PyInstaller --clean --noconfirm --onedir --console --name DonathonSpeechWorker `
       --paths $root `
       --collect-all faster_whisper --collect-all ctranslate2 --collect-all av `
       --collect-all tokenizers --collect-all onnxruntime --collect-all huggingface_hub `
       speech_worker.py
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось собрать модуль речи' }
    $speechZip = Join-Path $releaseDir "DonathonSpeech-$version.zip"
    if (Test-Path $speechZip) { Remove-Item $speechZip -Force }
    Compress-Archive -Path (Join-Path $root 'dist\DonathonSpeechWorker') -DestinationPath $speechZip -CompressionLevel Optimal
    $hash = (Get-FileHash $speechZip -Algorithm SHA256).Hash.ToLowerInvariant()

    # This manifest is bundled in the *main* EXE and checked before extraction.
    $url = if ($Repo) { "https://github.com/$Repo/releases/download/$Tag/DonathonSpeech-$version.zip" } else { '' }
    [System.IO.File]::WriteAllText((Join-Path $assets 'speech_release.json'), ((@{ version = $version; url = $url; sha256 = $hash } | ConvertTo-Json -Compress)), (New-Object System.Text.UTF8Encoding($false)))

    & $pyExe -m PyInstaller --clean --noconfirm --onedir --windowed --name DonathonTimer `
       --paths $root --icon buildtools\DonathonTimer.ico `
       --add-data "${assets};src/donathon/assets" `
       --add-data "${templates};src/donathon/templates" `
       --collect-submodules uvicorn --collect-submodules keyring.backends `
       --collect-all sounddevice `
       --exclude-module faster_whisper --exclude-module ctranslate2 `
       app.py
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось собрать DonathonTimer.exe' }

    $portable = Join-Path $releaseDir "DonathonTimer-$version-Portable.zip"
    if (Test-Path $portable) { Remove-Item $portable -Force }
    Compress-Archive -Path (Join-Path $root 'dist\DonathonTimer') -DestinationPath $portable -CompressionLevel Optimal

    $isccPaths = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    $iscc = $isccPaths | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $iscc) {
        Write-Warning 'Inno Setup 6 не найден: portable ZIP готов, но Setup.exe ещё не собран.'
        Write-Host 'Установи Inno Setup 6 (https://jrsoftware.org/isinfo.php), затем запусти сборку снова.'
    } else {
        $source = Join-Path $root 'dist\DonathonTimer'
        & $iscc "/DSourceDir=$source" "/DOutputDir=$releaseDir" 'installer\DonathonTimer.iss'
        if ($LASTEXITCODE -ne 0) { throw 'Не удалось собрать Setup.exe' }
    }
    $sums = @()
    Get-ChildItem $releaseDir -File | Where-Object { $_.Name -match '\.(exe|zip)$' } | ForEach-Object {
        $sums += "{0}  {1}" -f (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant(), $_.Name
    }
    $sums | Set-Content -LiteralPath (Join-Path $releaseDir 'SHA256SUMS.txt') -Encoding UTF8
    Write-Host "ГОТОВО: $releaseDir"
    Get-ChildItem $releaseDir -File | Select-Object Name, Length | Format-Table -AutoSize
} finally {
    Pop-Location
}
