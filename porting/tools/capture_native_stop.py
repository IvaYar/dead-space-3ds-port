"""Capture an exploratory native stop in a disposable emulator process.

Foreign donor workers can outlive a stopped lifecycle call. The supervisor
terminates the whole emulator process after the journal is flushed; it never
unloads a DLL while retro_run is executing. This is diagnostic evidence only.
"""
import argparse,hashlib,json,subprocess,sys,time
from pathlib import Path
PORTING=Path(__file__).resolve().parents[1]
ROOT=PORTING/'analysis/azahar-smoke';LOG=ROOT/'Azahar/sdmc/3ds/deadspace/engine-azahar-log.txt'
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--frame',type=int,default=2);args=parser.parse_args();assert 2<=args.frame<=600
    config=LOG.parent/'capture-frame.txt';backup=config.read_bytes() if config.exists() else None;config.write_text(str(args.frame)+'\n',encoding='ascii')
    if LOG.exists():LOG.unlink()
    for stem in ('first-game-draw','first-game-frame'):
        for suffix in ('.raw','.json'):
            path=LOG.parent/(stem+suffix)
            if path.exists():path.unlink()
    output=PORTING/'analysis/native-supervised-console.txt';started=time.monotonic();text='';observed=False
    with output.open('wb') as sink:
        p=subprocess.Popen([sys.executable,str(PORTING/'tests/smoke_engine_azahar.py'),'--case','graphics','--explore','--capture-frame',str(args.frame)],stdout=sink,stderr=subprocess.STDOUT)
        try:
            while time.monotonic()-started<45:
                if LOG.exists():text=LOG.read_text(encoding='utf-8',errors='replace')
                if 'ENGINE EXPERIMENT STOPPED' in text and ('No game frame rendered.' in text or 'Completed game frame saved.' in text):observed=True;break
                if p.poll() is not None:break
                time.sleep(.1)
        finally:
            if p.poll() is None:p.terminate()
            p.wait(timeout=5)
            if backup is not None:config.write_bytes(backup)
            elif config.exists():config.unlink()
    if LOG.exists():text=LOG.read_text(encoding='utf-8',errors='replace')
    target=ROOT/'engine-supervised.log';target.write_text(text,encoding='utf-8')
    report={'observed_stop':observed,'checkpoint_validated':False,'first_game_frame_rendered':'Completed game frame saved.' in text,
        'termination':'disposable emulator process supervised externally; no in-process module unload',
        'elapsed_seconds':round(time.monotonic()-started,3),'hardware_tested':False,
        'cxi_sha256':hashlib.sha256((PORTING/'3ds/build-emulator/engine-audit.cxi').read_bytes()).hexdigest(),
        'log_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
    (ROOT/'engine-supervised-result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(text[-3000:]);print(json.dumps(report,indent=2));return 0 if observed else 1
if __name__=='__main__':raise SystemExit(main())
