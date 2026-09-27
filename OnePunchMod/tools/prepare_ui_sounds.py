"""Developer-only: decode local HoN UI OGGs to portable PCM WAVs using installed FMOD.

Original sounds and the installed client remain untouched. Runtime needs no FMOD.
FMOD OPENONLY / Sound_ReadData: https://www.fmod.com/docs/2.02/api/core-api-common.html#fmod_mode
"""
import ctypes as C
from pathlib import Path
import wave


def prepare(project):
    library=C.WinDLL(str(project.parent/'bin/fmod.dll'))
    pointer=C.c_void_p
    def bind(name,args):
        f=getattr(library,name);f.argtypes=args;f.restype=C.c_int;return f
    create=bind('FMOD_System_Create',[C.POINTER(pointer),C.c_uint])
    output=bind('FMOD_System_SetOutput',[pointer,C.c_int])
    init=bind('FMOD_System_Init',[pointer,C.c_int,C.c_uint,pointer])
    sound_create=bind('FMOD_System_CreateSound',[pointer,C.c_char_p,C.c_uint,pointer,C.POINTER(pointer)])
    get_format=bind('FMOD_Sound_GetFormat',[pointer,C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_int)])
    get_defaults=bind('FMOD_Sound_GetDefaults',[pointer,C.POINTER(C.c_float),C.POINTER(C.c_int)])
    length=bind('FMOD_Sound_GetLength',[pointer,C.POINTER(C.c_uint),C.c_uint])
    read=bind('FMOD_Sound_ReadData',[pointer,pointer,C.c_uint,C.POINTER(C.c_uint)])
    release_sound=bind('FMOD_Sound_Release',[pointer])
    release=bind('FMOD_System_Release',[pointer])
    def check(result):
        if result:raise RuntimeError(f'FMOD error {result}')
    system=pointer();check(create(C.byref(system),0x00020200))
    try:
        check(output(system,2)) # NOSOUND: decoding does not require an audio device.
        check(init(system,8,0,None))
        destination=project/'sounds/ui';destination.mkdir(exist_ok=True)
        for path in sorted((project/'sounds').glob('*.ogg')):
            sound=pointer();check(sound_create(system,str(path).encode('utf-8'),0x2000,None,C.byref(sound)))
            try:
                kind,fmt,channels,bits=C.c_int(),C.c_int(),C.c_int(),C.c_int()
                check(get_format(sound,C.byref(kind),C.byref(fmt),C.byref(channels),C.byref(bits)))
                if fmt.value!=2 or bits.value!=16:raise RuntimeError('Expected PCM16 decoded output')
                frequency,priority=C.c_float(),C.c_int()
                check(get_defaults(sound,C.byref(frequency),C.byref(priority)))
                size=C.c_uint();check(length(sound,C.byref(size),4)) # PCMBYTES
                data=C.create_string_buffer(size.value);actual=C.c_uint()
                check(read(sound,data,size.value,C.byref(actual)))
                target=destination/(path.stem+'.wav')
                with wave.open(str(target),'wb') as stream:
                    stream.setnchannels(channels.value);stream.setsampwidth(2)
                    stream.setframerate(round(frequency.value));stream.writeframes(data.raw[:actual.value])
                print(target.name,actual.value,'PCM bytes')
            finally:release_sound(sound)
    finally:release(system)


if __name__=='__main__':prepare(Path(__file__).resolve().parents[1])
