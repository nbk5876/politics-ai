<#
Registers the Politics AI watcher as a Windows Scheduled Task: 8:00 AM and 8:00 PM every day.
NOT run automatically. Run it once, by hand, after review and approval:

    powershell -ExecutionPolicy Bypass -File scripts\register-task.ps1

Remove it later with:  Unregister-ScheduledTask -TaskName "PoliticsAI-Watcher" -Confirm:$false

Notes
- Runs as the signed-in user, so the DH_PASS user environment variable is available. No password is stored in the task.
- "Only when the user is logged on". If the PC is off or asleep at 8, StartWhenAvailable runs it when it wakes.
- Output goes to logs\watcher.log (not committed). The run uses --live: it sends LabChan messages, saves articles,
  uploads the links page, and remembers what it has reported.
#>
$ErrorActionPreference = "Stop"
$repo   = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python).Source
# The Microsoft Store "python" shortcut fails under Task Scheduler: refuse it and require a real install.
if ($python -like "*\WindowsApps\*" -or -not (& $python --version 2>$null)) {
    throw "python at '$python' is the Microsoft Store stub or does not run; install Python or put a real python.exe first on PATH."
}
$log    = Join-Path $repo "logs\watcher.log"
New-Item -ItemType Directory -Force -Path (Join-Path $repo "logs") | Out-Null

# cmd wrapper so output is appended to a log file with a timestamp header
$cmd = "/c echo ==== %DATE% %TIME% ==== >> `"$log`" && cd /d `"$repo`" && `"$python`" -m watcher.run --live >> `"$log`" 2>&1"
$action   = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $cmd -WorkingDirectory $repo
$triggers = @((New-ScheduledTaskTrigger -Daily -At "8:00AM"), (New-ScheduledTaskTrigger -Daily -At "8:00PM"))
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName "PoliticsAI-Watcher" -Action $action -Trigger $triggers -Settings $settings `
    -Principal $principal -Description "Politics AI watcher: reads feeds, notifies on LabChan, updates ai-safety-topic-links.html" -Force | Out-Null
Get-ScheduledTask -TaskName "PoliticsAI-Watcher" | Select-Object TaskName, State
