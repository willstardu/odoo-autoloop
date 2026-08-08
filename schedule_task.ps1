# ============================================================
# 安装/卸载 Windows 计划任务：定时运行 Odoo 自动测试流水线
# 用法（管理员 PowerShell）：
#   powershell -ExecutionPolicy Bypass -File schedule_task.ps1 -Install
#   powershell -ExecutionPolicy Bypass -File schedule_task.ps1 -Uninstall
# 默认每天 02:00 运行，可加 -Hour 参数自定义
# ============================================================
param(
    [switch]$Install,
    [switch]$Uninstall,
    [int]$Hour = 2,
    [int]$Minute = 0
)

$TaskName = "OdooAutoTestLoop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ScriptDir ".venv\Scripts\python.exe"
$RunScript = Join-Path $ScriptDir "run.py"
$LogDir = Join-Path $ScriptDir "artifacts\reports"

function Install-Task {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    $Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$RunScript`"" -WorkingDirectory $ScriptDir
    $Trigger = New-ScheduledTaskTrigger -Daily -At "$Hour`:$Minute"
    $Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 2) -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5)
    $Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "Odoo 19 OmniPod auto coder+test loop (GLM-5.2 + Qwen2.5VL)" -Force
    Write-Host "[OK] Task '$TaskName' installed: daily $Hour`:$Minute"
    Write-Host "     Run: $Python $RunScript"
}

function Uninstall-Task {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "[OK] Task '$TaskName' removed"
}

if ($Uninstall) { Uninstall-Task }
elseif ($Install) { Install-Task }
else {
    Write-Host "Usage: powershell -ExecutionPolicy Bypass -File schedule_task.ps1 -Install [-Hour 2] [-Minute 0]"
    Write-Host "       powershell -ExecutionPolicy Bypass -File schedule_task.ps1 -Uninstall"
}
