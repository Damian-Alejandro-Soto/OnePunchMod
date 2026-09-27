param([string]$Mailbox, [int]$OwnerPid)
Add-Type -AssemblyName PresentationCore
Add-Type -AssemblyName WindowsBase
$script:lastMessage = ''
$script:players = @{
    hover = New-Object System.Windows.Media.MediaPlayer
    action = New-Object System.Windows.Media.MediaPlayer
}
$timer = New-Object System.Windows.Threading.DispatcherTimer
$timer.Interval = [TimeSpan]::FromMilliseconds(45)
$timer.Add_Tick({
    if (-not (Get-Process -Id $OwnerPid -ErrorAction SilentlyContinue)) {
        [System.Windows.Threading.Dispatcher]::CurrentDispatcher.InvokeShutdown()
        return
    }
    try {
        $message = Get-Content -LiteralPath $Mailbox -Raw -ErrorAction Stop | ConvertFrom-Json
        if ($message.id -and $message.id -ne $script:lastMessage) {
            $script:lastMessage = $message.id
            $player = $script:players[$message.channel]
            if ($player) {
                $player.Stop()
                $player.Open([Uri]::new([string]$message.path))
                $player.Volume = [double]$message.volume
                $player.Play()
            }
        }
    } catch { }
})
$timer.Start()
try { [System.Windows.Threading.Dispatcher]::Run() }
finally {
    $timer.Stop()
    foreach ($player in $script:players.Values) { $player.Close() }
}
