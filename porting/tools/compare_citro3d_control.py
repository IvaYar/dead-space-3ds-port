"""Compare captured SDK control with native DS34 evidence; no execution/fix."""
import hashlib,json,struct
from pathlib import Path
P=Path(__file__).resolve().parents[1]
OUT=P/'analysis/citro3d-control'
def decode(path):
    raw=path.read_bytes();w=struct.unpack('<'+'I'*(len(raw)//4),raw);state={};pos=0;packets=0
    while pos<len(w):
        assert pos+1<len(w)
        h=w[pos+1];extra=(h>>20)&2047;length=(extra+3)&~1;assert pos+length<=len(w)
        mask=(h>>16)&15;bits=sum(255<<(i*8) for i in range(4) if mask&(1<<i))
        for i,v in enumerate([w[pos],*w[pos+2:pos+2+extra]]):
            reg=(h&65535)+(i if h>>31 else 0);old=state.get(reg,{'value':0,'known_bytes':0})
            state[reg]={'value':(old['value']&~bits)|(v&bits),'known_bytes':old['known_bytes']|mask}
        pos+=length;packets+=1
    return {'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'packets':packets,'state':state}
def main():
    OUT.mkdir(exist_ok=True)
    native=P/'analysis/hardware/gpu-test-v0.1.3-user'
    control=P/'analysis/azahar-citro3d-control'
    a=decode(native/'gx-first-1.pica');b=decode(control/'stage-1-1.pica')
    registers={0x04f:'SH_OUTMAP_TOTAL',0x080:'TEXUNIT_CONFIG',0x107:'DEPTH_COLOR_MASK',0x200:'ATTRIBBUFFERS_LOC',
               0x201:'ATTRIB_FORMAT_LOW',0x202:'ATTRIB_FORMAT_HIGH',0x242:'VSH_NUM_ATTR',0x2bd:'VSH_OUTMAP_MASK'}
    states={name:{'DS34':a['state'].get(r),'control':b['state'].get(r)} for r,name in registers.items()}
    manifest=json.loads((P/'3ds/build-citro3d-control/build-manifest.json').read_text())
    old=json.loads((native/'gx-first-frame.json').read_text())
    new={str(i):json.loads((control/f'stage-{i}-queue.json').read_text()) for i in range(2)}
    assert [e['type'] for e in new['0']['entries']]==[2,3]
    assert [e['type'] for e in new['1']['entries']]==[e['type'] for e in old['entries']]==[2,1,3]
    # Fill color/depth buffers, clear values, dimensions, transfer formats must
    # match; CPU framebuffer and linear PICA/VBO pointers can legitimately differ.
    old_fill=old['entries'][0]['words'];new_fill=new['1']['entries'][0]['words']
    assert old_fill==new_fill,'Target allocation/clear changed'
    old_transfer=old['entries'][2]['words'];new_transfer=new['1']['entries'][2]['words']
    same_transfer=all(old_transfer[i]==new_transfer[i] for i in [0,1,3,4,5,6,7]);assert same_transfer
    report={'control_is_DS34_fix':False,'hardware_control_tested':False,'cause_confirmed':False,
        'same_sdk_libraries':manifest['same_SDK_library_hashes'],'same_binary_capabilities_except_program_id':manifest['same_binary_capabilities_except_program_id'],
        'same_target_clear_command_words':True,'same_display_transfer_except_CPU_destination':same_transfer,
        'queue_type_ids':{'control_clear':[2,3],'control_triangle':[2,1,3],'native_DS34':[2,1,3]},
        'control_pica':{k:v for k,v in b.items() if k!='state'},'DS34_pica':{k:v for k,v in a.items() if k!='state'},
        'register_state':states,
        'cache_flush':'Both FrameEnd(0) paths invoke the same Citro3D full-linear-heap flush; control checks VBO bytes after completion. DS34 additionally flushes its packed stream explicitly.',
        'completion':'Control uses VBlank counters + bounded FrameBegin(NONBLOCK), preserving wait-before-readback and retaining allocations until idle. DS34 v0.1.3 uses the same SDK primitives but adds an extra FrameSync-equivalent VBlank wait.',
        'memory_layout_limit':'Same 64MB Legacy/256KiB stack/capabilities; allocation layout is intentionally not identical. No DS34 8MiB runtime heap, large stream, inactive texture or GLES state are linked.',
        'candidate_differences_not_confirmed_errors':['1 position float3 array plus fixed RGBA vs DS34 four float4 arrays','Default SDK vertex base vs DS34 physical-stream base','No texture units enabled vs DS34 permanently valid unit1 dummy','Position/color outputs only vs DS34 additional texcoord outputs','Default SDK depth/blend/cull and no scissor vs DS34 GLES state'],
        'decision_tree':{'clear_fails':'PICA draw is absent: inspect basic fill/transfer, SDK/profile and completion path before DS34 shader/UV work',
                         'clear_pass_triangle_fails':'Minimal SDK PICA draw/resource path still fails; DS34-specific cause not established',
                         'both_pass':'Native basic SDK/profile path works; isolate DS34 state/resource differences one at a time; do not transplant a speculative fix'},
        'next_action':'Request permission for exactly one independent control run; no hardware execution or push performed'}
    (OUT/'comparison.json').write_text(json.dumps(report,indent=2)+'\n');print('Comparison saved; target/clear/transfer/profile match; DS34 cause remains unconfirmed')
if __name__=='__main__':main()
