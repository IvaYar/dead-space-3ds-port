"""Decode a checksum-verified CPU framebuffer captured from a donor draw."""
import argparse,json,shutil,struct,zlib,hashlib
from pathlib import Path
P=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--partial',action='store_true');args=parser.parse_args()
    stem='first-game-draw' if args.partial else 'first-game-frame'
    card=P/'analysis/azahar-smoke/Azahar/sdmc/3ds/deadspace';meta=json.loads((card/(stem+'.json')).read_text());raw=(card/(stem+'.raw')).read_bytes()
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
    dest=P/'analysis/first-frame';dest.mkdir(exist_ok=True)
    for suffix in ('.raw','.json'):shutil.copyfile(card/(stem+suffix),dest/(stem+suffix))
    output=dest/(stem+'.png');output.write_bytes(data)
    print(output);print(meta);print('PNG SHA256',hashlib.sha256(data).hexdigest())
if __name__=='__main__':main()
