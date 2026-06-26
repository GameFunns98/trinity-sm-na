$startupFolder = [Environment]::GetFolderPath("Startup")
$targetScript = Join-Path $PSScriptRoot "start_trinity_server_hidden.vbs"
$shortcutPath = Join-Path $startupFolder "Trinity Server.lnk"

if (-not (Test-Path $targetScript)) {
    throw "Soubor '$targetScript' nebyl nalezen."
}

$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetScript
$shortcut.WorkingDirectory = $PSScriptRoot
$shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,220"
$shortcut.Save()

Write-Host "Zastupce byl vytvoren:" $shortcutPath
Write-Host "Server se po prihlaseni spusti na pozadi pres start_trinity_server_hidden.vbs."
