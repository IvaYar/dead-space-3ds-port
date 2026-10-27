"""Run the isolated native HID sampler through real libctru in Azahar."""
import ctypes as C,hashlib,json,time
import smoke_azahar as frontend
PORTING=frontend.PORTING;ROOT=frontend.ROOT
def main():
    log=ROOT/'Azahar/sdmc/3ds/deadspace/sensor-azahar-log.txt'
    if log.exists():log.unlink()
    core=C.CDLL(str((PORTING/'toolchain/azahar-libretro/azahar_libretro.dll').resolve()))
    for name,callback in (('environment',frontend.environment),('video_refresh',frontend.video),('audio_sample',frontend.audio),
                         ('audio_sample_batch',frontend.audio_batch),('input_poll',frontend.poll),('input_state',frontend.input_state)):
        setter=getattr(core,'retro_set_'+name);setter.argtypes=[type(callback)];setter(callback)
    core.retro_load_game.argtypes=[C.POINTER(frontend.GameInfo)];core.retro_load_game.restype=C.c_bool
    core.retro_init();app=PORTING/'3ds/build-sensor/sensor-audit.cxi';game=frontend.GameInfo(str(app.resolve()).encode(),None,0,None)
    assert core.retro_load_game(C.byref(game))
    started=time.monotonic();text=''
    try:
        for frame in range(2400):
            core.retro_run()
            if frame%15==0 and log.exists():
                text=log.read_text()
                if 'SENSOR BACKEND PASSED' in text or 'SENSOR BACKEND STOPPED' in text:break
            if frontend.shutdown or time.monotonic()-started>40:break
    finally:core.retro_unload_game();core.retro_deinit()
    target=ROOT/'sensor-native.log';target.write_bytes(log.read_bytes() if log.exists() else b'')
    assert 'SENSOR BACKEND PASSED' in text,text
    assert 'Backend=0 init=0 enable=0 close=0 active=0' in text
    report={'emulator':'Azahar libretro 2126.2','passed':True,'hardware_tested':False,'game_adapter_enabled':False,
        'cxi_sha256':hashlib.sha256(app.read_bytes()).hexdigest(),'log_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
        'elapsed_seconds':round(time.monotonic()-started,3)}
    (PORTING/'analysis/sensor-native-result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(text);print(json.dumps(report,indent=2))
if __name__=='__main__':main()
