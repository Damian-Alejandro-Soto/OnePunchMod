"""One reusable Windows audio host; hover sounds never spawn a process per event."""
import atexit
import array
import configparser
import hashlib
import json
import os
import subprocess
import tempfile
import time
import wave

_process = None
_mailbox = None
_config = None
_signature = None
_last_hover = 0.0
_action_until = 0.0


def _wav_at_volume(root, sound, volume):
    """Cache PCM gain once per file/volume; never change the system mixer volume."""
    if volume == 1:
        return sound
    stat=os.stat(sound)
    key=hashlib.sha256(f'{sound}|{stat.st_mtime_ns}|{stat.st_size}|{volume:.3f}'.encode()).hexdigest()[:24]
    directory=os.path.join(root,'OnePunchMod','Cache','ui_audio')
    os.makedirs(directory,exist_ok=True)
    target=os.path.join(directory,key+'.wav')
    if os.path.isfile(target):return target
    with wave.open(sound,'rb') as source:
        params=source.getparams();data=source.readframes(source.getnframes())
    if params.sampwidth==2:
        samples=array.array('h',data)
        data=array.array('h',(round(value*volume) for value in samples)).tobytes()
    else:
        width=params.sampwidth
        samples=[]
        for offset in range(0,len(data),width):
            value=int.from_bytes(data[offset:offset+width],'little',signed=width!=1)
            if width==1:value-=128
            value=round(value*volume)+(128 if width==1 else 0)
            samples.append(value.to_bytes(width,'little',signed=width!=1))
        data=b''.join(samples)
    with wave.open(target+'.new','wb') as output:
        output.setparams(params);output.writeframes(data)
    os.replace(target+'.new',target)
    return target


def close():
    global _process, _mailbox
    if _process is not None:
        if _process.poll() is None:
            _process.terminate()
        _process = None
    if _mailbox:
        for path in (_mailbox, _mailbox+'.new'):
            try: os.remove(path)
            except OSError: pass
        _mailbox = None


atexit.register(close)


def play(root, event):
    global _process, _mailbox, _config, _signature, _last_hover, _action_until
    if os.name != 'nt':
        return
    try:
        path = os.path.join(root, 'OnePunchMod', 'one_punch_settings.ini')
        stat = os.stat(path)
        signature = (path, stat.st_mtime_ns, stat.st_size)
        if signature != _signature:
            config = configparser.ConfigParser()
            config.read(path, encoding='utf-8')
            _config, _signature = config, signature
        if not _config.getboolean('audio', 'enabled', fallback=True):
            return
        raw = _config.get('audio', event, fallback='').strip().strip('"')
        volume = max(0, min(1, _config.getfloat('ui', 'sound_volume', fallback=.8)))
        if not raw or not volume:
            return
        sound = raw if os.path.isabs(raw) else os.path.join(root, 'OnePunchMod', raw)
        if not os.path.isfile(sound):
            return
        hover = event in ('ui_hover', 'avatar_hover')
        now = time.monotonic()
        if hover and (now-_last_hover < .16 or now < _action_until):
            return
        if hover:
            _last_hover = now
        else:
            _action_until = now+.4
        if sound.lower().endswith('.wav'):
            import winsound
            winsound.PlaySound(_wav_at_volume(root,sound,volume),
                              winsound.SND_FILENAME|winsound.SND_ASYNC|winsound.SND_NODEFAULT)
            return
        if _process is None or _process.poll() is not None:
            close()
            fd, _mailbox = tempfile.mkstemp(prefix='onepunch_audio_', suffix='.json')
            os.close(fd)
            script = os.path.join(os.path.dirname(__file__), 'tools', 'ui_audio_player.ps1')
            _process = subprocess.Popen(
                ['powershell.exe', '-NoProfile', '-WindowStyle', 'Hidden', '-ExecutionPolicy', 'Bypass',
                 '-File', script, '-Mailbox', _mailbox, '-OwnerPid', str(os.getpid())],
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(_mailbox+'.new', 'w', encoding='utf-8') as stream:
            json.dump({'id':time.time_ns(), 'path':os.path.abspath(sound), 'volume':volume,
                       'channel':'hover' if hover else 'action'}, stream)
        os.replace(_mailbox+'.new', _mailbox)
    except (OSError, ValueError, RuntimeError, wave.Error, configparser.Error):
        # Audio must never block selecting or applying an avatar.
        return
