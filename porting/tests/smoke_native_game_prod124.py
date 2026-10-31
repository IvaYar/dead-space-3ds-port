"""Reuse preserved native-frame checks for the isolated Prod124 namespace/title."""
import hashlib
from pathlib import Path

P=Path(__file__).resolve().parents[1]
original=P/'tests/smoke_native_game.py'
raw=original.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='9e926c6e18571a35c2862bf0ddf792c4c24bf1605f49d7aba1546339231825c3'
source=raw.decode()
assert source.count('ds-native-game-v0.1.0/')==1
source=source.replace('ds-native-game-v0.1.0/','ds-native-game-prod124-v0.1.0/')
source=source.replace('0x000400000FDE7100','0x000400000FDE7300').replace("'000400000FDE7100'","'000400000FDE7300'")
exec(compile(source,str(original)+' [Prod124 namespace/title]','exec'),{'__name__':'__main__','__file__':__file__})
