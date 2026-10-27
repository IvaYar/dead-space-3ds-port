"""Read the selected APK's DEX sensor signatures without executing Java code."""
import hashlib,json,struct
from pathlib import Path
PORTING=Path(__file__).resolve().parents[1]

class Dex:
    def __init__(self,data):
        self.data=data
        assert data[:8]==b'dex\n035\0' and self.u32(32)==len(data)
        self.strings=[]
        for i in range(self.u32(56)):
            p=self.u32(self.u32(60)+i*4);_,p=self.uleb(p)
            end=data.index(0,p);self.strings.append(data[p:end].decode('utf-8',errors='replace'))
        self.types=[self.strings[self.u32(self.u32(68)+i*4)] for i in range(self.u32(64))]
        self.protos=[]
        for i in range(self.u32(72)):
            p=self.u32(76)+i*12;ret=self.u32(p+4);params=self.u32(p+8)
            args=[] if not params else [self.types[self.u16(params+4+j*2)] for j in range(self.u32(params))]
            self.protos.append('('+''.join(args)+')'+self.types[ret])
        self.fields=[]
        for i in range(self.u32(80)):
            p=self.u32(84)+i*8
            self.fields.append({'class':self.types[self.u16(p)],'name':self.strings[self.u32(p+4)],'type':self.types[self.u16(p+2)]})
        self.methods=[]
        for i in range(self.u32(88)):
            p=self.u32(92)+i*8
            self.methods.append({'class':self.types[self.u16(p)],'name':self.strings[self.u32(p+4)],'signature':self.protos[self.u16(p+2)]})
    def u16(self,p):return struct.unpack_from('<H',self.data,p)[0]
    def u32(self,p):return struct.unpack_from('<I',self.data,p)[0]
    def uleb(self,p):
        value=0
        for shift in range(0,35,7):
            b=self.data[p];p+=1;value|=(b&127)<<shift
            if b<128:return value,p
        raise ValueError('bad ULEB128')
    def inspect(self,name):
        for i in range(self.u32(96)):
            row=self.u32(100)+i*32
            if self.types[self.u32(row)]!=name:continue
            p=self.u32(row+24);counts=[]
            for _ in range(4):n,p=self.uleb(p);counts.append(n)
            fields=[];methods=[]
            for n in counts[:2]:
                index=0
                for _ in range(n):
                    delta,p=self.uleb(p);index+=delta;flags,p=self.uleb(p)
                    fields.append({**self.fields[index],'access_flags':flags})
            for n in counts[2:]:
                index=0
                for _ in range(n):
                    delta,p=self.uleb(p);index+=delta;flags,p=self.uleb(p);code,p=self.uleb(p)
                    method={**self.methods[index],'access_flags':flags,'native':bool(flags&0x100)}
                    if code:
                        size=self.u32(code+12)*2;body=self.data[code+16:code+16+size]
                        method.update(code_offset=code,instruction_bytes=size,code_sha256=hashlib.sha256(body).hexdigest())
                    methods.append(method)
            return {'class':name,'fields':fields,'methods':methods}
        raise KeyError(name)

def main():
    source=PORTING/'analysis/android-abi/candidate-sd-classes.dex';data=source.read_bytes();dex=Dex(data)
    origin=json.loads((source.parent/'candidate-sd-dex-source.json').read_text())
    assert len(data)==origin['bytes'] and hashlib.sha256(data).hexdigest()==origin['sha256']
    names=['AccelerometerAndroidDelegate','DeviceOrientationHandlerAndroidDelegate']
    report={'source':str(source.relative_to(PORTING)),'dex_sha256':hashlib.sha256(data).hexdigest(),
        'scope':'static declarations only; Java code not executed; no native sensor implementation claimed',
        'classes':[dex.inspect('Lcom/ea/blast/'+n+';') for n in names]}
    target=PORTING/'analysis/android-abi/candidate-sd-sensors.json'
    target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    for cls in report['classes']:
        print(cls['class'])
        for m in cls['methods']:print(' ',m['name']+m['signature'],'native' if m['native'] else '')
if __name__=='__main__':main()
