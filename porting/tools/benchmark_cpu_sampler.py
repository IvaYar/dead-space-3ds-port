"""Count actual ARM instructions for a fixed textured draw, not host FPS."""
import argparse, hashlib, json, sys
from pathlib import Path
from unicorn import UC_HOOK_CODE

P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(P/'tests'))
import test_first_frame as draw

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    draw.DrawTests.setUpClass()
    case=draw.DrawTests('test_nearest_textured_quad_uses_actual_rgba_store')
    case.setUp()
    try:
        assert case.arm.call('ds15_test_limits',128,2*1024*1024)==0
        # A texture near the end of a real scene's name table. Reserved names
        # require no image allocations and do not change the sampled pixels.
        case.call('glGenTextures',70,draw.DATA+1024)
        case.quad();name=case.texture()
        case.call('glDrawArrays',5,0,4)
        expected=case.pixels();before=case.stats()
        count=[0]
        def instruction(uc,address,size,user):count[0]+=1
        hook=case.arm.uc.hook_add(UC_HOOK_CODE,instruction)
        # Previously translated blocks may predate this hook in Unicorn.
        case.arm.uc.ctl_flush_tb()
        try:
            for _ in range(8):case.call('glDrawArrays',5,0,4)
        finally:case.arm.uc.hook_del(hook)
        after=case.stats()
        assert case.pixels()==expected and case.call('glGetError')==0
        assert after[0]-before[0]==8 and after[2]-before[2]==96 and count[0]>1000
        result={'core_sha256':hashlib.sha256((P/'3ds/build-emulator/core-test.elf').read_bytes()).hexdigest(),
            'scope':'Unicorn ARM instruction count, 8 identical 4x3 nearest textured quads; not hardware FPS',
            'texture_name':name,'draws':8,'fragments':96,'instructions':count[0],
            'pixels_sha256':hashlib.sha256(expected).hexdigest(),'hardware_tested':False}
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2))
    finally:case.tearDown()

if __name__=='__main__':main()
