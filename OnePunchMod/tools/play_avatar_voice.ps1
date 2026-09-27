param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)][string]$LogPath
)

$ErrorActionPreference = 'Stop'

function Write-DebugLog {
    param([string]$Message)
    try {
        $parent = Split-Path -Parent $LogPath
        if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
        $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss.fff'
        Add-Content -LiteralPath $LogPath -Value "$stamp | PID=$PID | $Message" -Encoding UTF8
    } catch { }
}

$player = $null
$timer = $null
$script:finished = $false
$script:opened = $false
$script:elapsed = 0

try {
    Write-DebugLog "BEGIN path=$Path exists=$(Test-Path -LiteralPath $Path) size=$((Get-Item -LiteralPath $Path -ErrorAction SilentlyContinue).Length)"
    Add-Type -AssemblyName PresentationCore
    Add-Type -AssemblyName WindowsBase
    Write-DebugLog 'ASSEMBLIES_LOADED'

    $player = New-Object System.Windows.Media.MediaPlayer
    $player.add_MediaOpened({
        param($sender, $eventArgs)
        $script:opened = $true
        Write-DebugLog "MEDIA_OPENED duration=$($sender.NaturalDuration)"
        $sender.Volume = 1.0
        $sender.Play()
        Write-DebugLog 'PLAY_CALLED'
    })
    $player.add_MediaEnded({
        param($sender, $eventArgs)
        Write-DebugLog 'MEDIA_ENDED'
        $script:finished = $true
    })
    $player.add_MediaFailed({
        param($sender, $eventArgs)
        $detail = if ($eventArgs -and $eventArgs.ErrorException) { $eventArgs.ErrorException.ToString() } else { 'unknown media failure' }
        Write-DebugLog "MEDIA_FAILED $detail"
        $script:finished = $true
    })

    $player.Open([Uri]::new($Path))
    Write-DebugLog 'OPEN_CALLED'

    $timer = New-Object System.Windows.Threading.DispatcherTimer
    $timer.Interval = [TimeSpan]::FromMilliseconds(50)
    $timer.add_Tick({
        $script:elapsed += 50
        if ($script:finished -or $script:elapsed -ge 10000) {
            if (-not $script:finished) { Write-DebugLog 'TIMEOUT waiting for media end' }
            $timer.Stop()
            if ($player) { $player.Close() }
            [System.Windows.Threading.Dispatcher]::CurrentDispatcher.InvokeShutdown()
        }
    })
    $timer.Start()
    Write-DebugLog 'DISPATCHER_STARTED'
    [System.Windows.Threading.Dispatcher]::Run()
    Write-DebugLog "DISPATCHER_FINISHED opened=$script:opened elapsed_ms=$script:elapsed"
} catch {
    Write-DebugLog "ERROR $($_.Exception.ToString())"
} finally {
    if ($timer) { $timer.Stop() }
    if ($player) { $player.Close() }
    Write-DebugLog 'END'
}
