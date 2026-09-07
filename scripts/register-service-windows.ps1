$ErrorActionPreference = 'Stop'
$root = 'C:\AI\MOSS-TTSD'
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c C:\AI\MOSS-TTSD\scripts\start-windows.cmd' -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName 'MOSS-TTSD' -Action $action -Trigger $trigger -Settings $settings -User 'SYSTEM' -RunLevel Highest -Description '云途觉晓多人云音创作平台，MOSS-TTSD v1.0，V100 FP16/SDPA，LAN port 7863' -Force | Out-Null

if (-not (Get-NetFirewallRule -Name 'MOSS-TTSD-LAN-7863' -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -Name 'MOSS-TTSD-LAN-7863' -DisplayName 'MOSS-TTSD LAN 7863' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 7863 -RemoteAddress LocalSubnet -Profile Any | Out-Null
}

$desktop = [Environment]::GetFolderPath('CommonDesktopDirectory')
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $desktop '云途觉晓多人云音创作平台.lnk'))
$shortcut.TargetPath = "$env:WINDIR\explorer.exe"
$shortcut.Arguments = 'http://127.0.0.1:7863'
$shortcut.Description = '打开云途觉晓多人云音创作平台'
$shortcut.Save()
'@echo off', 'schtasks /Run /TN "MOSS-TTSD"', 'pause' | Set-Content (Join-Path $desktop 'Start MOSS-TTSD.cmd') -Encoding ASCII
'@echo off', 'schtasks /End /TN "MOSS-TTSD"', 'pause' | Set-Content (Join-Path $desktop 'Stop MOSS-TTSD.cmd') -Encoding ASCII

Write-Output 'Service and LAN firewall rule registered. Start with: Start-ScheduledTask -TaskName MOSS-TTSD'
