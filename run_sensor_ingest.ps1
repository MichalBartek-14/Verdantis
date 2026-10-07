# Wrapper for the "VerdantisSensorIngest-Devinska" Windows Task Scheduler task.
# Runs exactly one ingest_sensor_data.py pull (same as a manual run) and logs it -
# the scheduled task's trigger controls frequency, not this script.
#
# To change frequency: Task Scheduler -> "VerdantisSensorIngest-Devinska" -> Triggers
# tab -> Edit. Currently: once daily at 20:00. For something more frequent (e.g. every
# 20 min), either edit that trigger's repetition settings, or point the task's Action
# at `ingest_sensor_data.py --client devinska --watch --interval 1200` instead and make
# the trigger "At log on" / "At startup" (a --watch run is a long-lived foreground
# process, not a one-shot, so it needs a different kind of trigger than this script's).
#
# Scope is deliberately local-only: fetch + reparse + rewrite
# outputs/devinska/sensor_temperature.json. No docs/ copy, no publish_site.py, no git
# commit/push - those stay manual (see CLAUDE.md's "nothing here runs automatically").

$ErrorActionPreference = "Stop"
$repoRoot = "C:\Users\misko\Documents\Michal\MyWork\Verdantis\forestry_pilot"
$logDir = Join-Path $repoRoot "outputs\devinska\ingest_logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir ("{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

Set-Location $repoRoot
python ingest_sensor_data.py --client devinska *>&1 | Tee-Object -FilePath $logFile
