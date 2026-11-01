"""Run the content installed by official Azahar, reusing all native-game checks."""
import hashlib
import json
import runpy
import sys
from pathlib import Path

P=Path(__file__).resolve().parents[1]
install=json.loads((P/'analysis/native-game-cia-v0.1.0/CIA-install.json').read_text())
installed=P/install['installed_content']
sha=lambda q:hashlib.sha256(q.read_bytes()).hexdigest()
assert install['passed'] and sha(installed)==install['CIA_payload_sha256']
sys.argv=['smoke_native_game','--revision','h2','--container','cia','--attempt','installed','--cycles','3']
state=runpy.run_path(str(P/'tests/smoke_native_game.py'),run_name='native_game_validation')
main=state['main'];scope=main.__globals__;original=scope['run_cycle']
def cycle(core,app,source,controls,index,evidence):
    assert sha(app)==sha(installed),'Installed content differs from this CIA'
    result=original(core,installed,source,controls,index,evidence)
    result['loaded_installed_content']=True
    result['installed_content_sha256']=sha(installed)
    (evidence/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
scope['run_cycle']=cycle
main()
