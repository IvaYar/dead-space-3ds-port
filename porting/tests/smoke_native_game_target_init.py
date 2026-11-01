"""Unmodified frame/shutdown checks; own host namespace and mismatch screenshot."""
import hashlib
from pathlib import Path
P=Path(__file__).resolve().parents[1];original=P/'tests/smoke_native_game.py';raw=original.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='9e926c6e18571a35c2862bf0ddf792c4c24bf1605f49d7aba1546339231825c3'
source=raw.decode().replace('native-game-v0.1.0','native-game-v0.1.1')
source=source.replace('0x000400000FDE7100','0x000400000FDE7400').replace("'000400000FDE7100'","'000400000FDE7400'")
needle="if frame_report['status']=='blocked':"
assert source.count(needle)==1
source=source.replace(needle,needle+"\n                f.save_frame(ROOT/'blocked-screen.png')")
exec(compile(source,str(original)+' [target initialization host paths]','exec'),{'__name__':'__main__','__file__':__file__})
