"""Build port ELF from source; commercial resources are never compiled in."""
from pathlib import Path
import argparse,json,subprocess,hashlib
p=argparse.ArgumentParser();p.add_argument('--devkitpro',type=Path,required=True);p.add_argument('--citro3d',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();root=Path(__file__).resolve().parent;src=root/'playable/src';cfg=json.loads((root/'playable/build-config.json').read_text());a.out.mkdir(parents=True,exist_ok=False)
a.devkitpro=a.devkitpro.resolve();a.citro3d=a.citro3d.resolve();a.out=a.out.resolve()
gcc=a.devkitpro/'devkitARM/bin/arm-none-eabi-gcc.exe'
if not gcc.exists():gcc=gcc.with_suffix('')
for n,h in cfg['source_sha256'].items():assert hashlib.sha256((src/n).read_bytes()).hexdigest()==h,n
obj=a.out/'lz4-fast.o';subprocess.run([str(gcc),'-march=armv6k','-mtune=mpcore','-mfloat-abi=hard','-mtp=soft','-O3','-fno-strict-aliasing','-ffunction-sections','-fdata-sections','-fstack-usage','-c',str(src/'lz4.c'),'-o',str(obj)],check=True)
cmd=[str(gcc),'-I'+str(src),'-I'+str(a.devkitpro/'libctru/include'),'-I'+str(a.citro3d/'include')]
for x in cfg['argv']:
 x=x.replace('@SRC/',str(src)+'/').replace('@LZ4',str(obj)).replace('@OUT',str(a.out/'native-game.elf')).replace('@C3DLIB','-L'+str(a.citro3d/'lib')).replace('@CTRULIB','-L'+str(a.devkitpro/'libctru/lib'));cmd.append(x)
subprocess.run(cmd,cwd=a.out,check=True)
print('ELF built; packaging and original SD resources are separate. See playable/BUILD.md.')
