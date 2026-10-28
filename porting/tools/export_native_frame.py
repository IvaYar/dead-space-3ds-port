"""Decode a checksum-verified CPU framebuffer captured from a donor draw."""
import argparse,json,shutil,struct,zlib,hashlib
from pathlib import Path
P=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--partial',action='store_true');parser.add_argument('--progress-frame',type=int,default=0)
    parser.add_argument('--output-directory',type=Path,default=P/'analysis/first-frame');args=parser.parse_args()
    assert not (args.partial and args.progress_frame)
    stem=f'progress-frame-{args.progress_frame}' if args.progress_frame else 'first-game-draw' if args.partial else 'first-game-frame'
    card=P/'analysis/azahar-smoke/Azahar/sdmc/3ds/deadspace';meta=json.loads((card/(stem+'.json')).read_text());raw=(card/(stem+'.raw')).read_bytes()
    journal=(card/'engine-azahar-log.txt').read_text(encoding='utf-8')
    if args.progress_frame:assert f'PROGRESS FRAME SAVED: frame={args.progress_frame}\n' in journal and meta['frame']==args.progress_frame,'Current run has no matching progress capture'
    elif args.partial:assert 'PARTIAL GAME DRAW CAPTURED' in journal,'Current run has no partial capture'
    else:
        marker=f"FIRST GAME FRAME CAPTURED: frame={meta['frame']} draws={meta['draws']} fragments={meta['fragments']} samples={meta['samples']}"
        assert marker in journal and 'Completed game frame saved.' in journal,'Stale framebuffer: current run did not complete this capture'
    w,h,layout=meta['width'],meta['height'],meta['layout'];assert 0<w<=1024 and 0<h<=1024 and layout in (0,1,2)
    assert len(raw)==meta['bytes']==w*h*(2 if layout==2 else 3)
    assert f'{zlib.crc32(raw):08x}'==meta['crc32']
    scan=bytearray()
    for row in range(h):
        scan.append(0);y=h-1-row
        for x in range(w):
            offset=(y*w+x if layout==0 else x*h+y)*(2 if layout==2 else 3)
            if layout==2:
                value=raw[offset]|raw[offset+1]<<8;scan.extend((((value>>11)&31)*255//31,((value>>5)&63)*255//63,(value&31)*255//31))
            elif layout==0:scan.extend(raw[offset:offset+3])
            else:scan.extend(raw[offset:offset+3][::-1])
    def chunk(name,value):return struct.pack('>I',len(value))+name+value+struct.pack('>I',zlib.crc32(name+value))
    data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(scan))+chunk(b'IEND',b'')
    dest=args.output_directory;dest.mkdir(parents=True,exist_ok=True)
    for suffix in ('.raw','.json'):shutil.copyfile(card/(stem+suffix),dest/(stem+suffix))
    output=dest/(stem+'.png');output.write_bytes(data)
    print(output);print(meta);print('PNG SHA256',hashlib.sha256(data).hexdigest())
if __name__=='__main__':main()
