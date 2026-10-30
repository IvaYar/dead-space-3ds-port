"""Decode existing CLEAR evidence and check static bounds; never run GPU code."""
import hashlib,json,re
from pathlib import Path
P=Path(__file__).resolve().parents[1]
OUT=P/'analysis/gpu-clear-audit'
def main():
    folder=P/'analysis/hardware/citro3d-control-v0.1.0-user'
    entries=json.loads((folder/'stage-0-queue.json').read_text())['entries']
    assert [e['type'] for e in entries]==[2,3]
    fill,transfer=[e['words'] for e in entries];assert len(fill)==len(transfer)==8
    assert fill[0]==0x01000102 and transfer[0]==0x01000103
    width,height=transfer[3]&65535,transfer[3]>>16
    flags=transfer[5]
    assert (width,height)==(240,400) and transfer[3]==transfer[4]
    assert (flags>>8)&7==1 and (flags>>12)&7==2
    color_bytes=width*height*3;depth_bytes=width*height*4;output_bytes=width*height*2
    assert fill[3]-fill[1]==color_bytes and fill[6]-fill[4]==depth_bytes
    assert fill[7]&65535==0x0101 and fill[7]>>16==0x0201
    assert 0x1f000000<=fill[1]<fill[3]<=fill[4]<fill[6]<=0x1f600000
    assert transfer[1]==fill[1]
    assert all(a%128==0 for a in [fill[1],fill[3],fill[4],fill[6],transfer[2]])
    assert width%8==height%8==0
    # gfxInitDefault allocates double-height BGR8 buffers before RGB565 is set.
    allocated=240*800*3;assert output_bytes<=allocated
    assembly=(OUT/'gspEventThreadMain.asm.txt').read_text()
    assert re.search(r'10aa58:.*\bbl\s+106b28\s+<gxCmdQueueInterrupt>',assembly)
    manifest=json.loads((P/'3ds/build-citro3d-control/build-manifest.json').read_text())
    for name,h in manifest['inputs_sha256'].items():assert hashlib.sha256((P/name).read_bytes()).hexdigest()==h,name
    for name,h in manifest['outputs_sha256'].items():assert hashlib.sha256((P/'3ds/build-citro3d-control'/name).read_bytes()).hexdigest()==h,name
    report={
        'audit_cycles':2,'hardware_executed':False,'new_CIA_created':False,'renderer_or_SDK_modified':False,'root_cause_proven':False,
        'existing_hardware_result':'CLEAR queue submitted=2, SDK event count=1; event types not logged',
        'arguments':{'GX_MemoryFill':[f'0x{x:08x}' for x in [fill[1],fill[2],fill[3],fill[7]&65535,fill[4],fill[5],fill[6],fill[7]>>16]],
                     'GX_DisplayTransfer':[f'0x{x:08x}' for x in [transfer[1],transfer[3],transfer[2],transfer[4],transfer[5]]]},
        'bounds':{'width':width,'height':height,'color_bytes':color_bytes,'depth_bytes':depth_bytes,'destination_write_bytes':output_bytes,
                  'destination_start':f'0x{transfer[2]:08x}','destination_write_end':f'0x{transfer[2]+output_bytes:08x}',
                  'destination_allocation_bytes_from_pinned_gfx_source':allocated,'addresses_128_aligned':True,'VRAM_ranges_nonoverlapping':True,
                  'all_checks_are_static_not_runtime_memory_queries':True},
        'flags':{'raw':f'0x{flags:08x}','input':'RGB8','output':'RGB565','output_tiled':bool(flags&2),'flip':bool(flags&1),'raw_copy':bool(flags&8),'scaling':flags>>24},
        'binary_dispatch':{'event_call_site':'0x0010aa58','real_GX_handler':'0x00106b28','weak_stub_excluded':True},
        'completion':{'counted_events':['PSC0','PPF','P3D','DMA'],'ignored_events':['PSC1','VBlank0','VBlank1'],
                      'command_ID_matching':False,'wait_tests_global_isRunning':True,'wait_timeout_values_used':[0,-1],
                      'event_wait_can_undo_prior_queue_increment':False,'FILL_vs_DISPLAY_identifiable_from_current_log':False,
                      'physical_GPU_hang_proven':False,'unambiguous_counterexamples':['PSC0 only => 1/2','PPF only => 1/2']},
        'proven_project_errors_causing_CLEAR':[],
        'unrelated_SDK_observation':'Positive gxCmdQueueWait timeout is documented ns but added to ticks in v2.7.0; current path uses only 0/-1, so not causal and not patched',
        'hypotheses_remaining':['Missing PPF/transfer completion or delivery','Missing PSC0/fill completion or delivery','GSP IRQ delivery or queue lifecycle/accounting','Shared format/profile/service handling difference vs unmodified official example'],
        'next_minimal_test':'One identical CLEAR-only queue with passive PSC0/PSC1/PPF callbacks and SDK queue snapshots; preserve VBlank callbacks, command ordering and formats; no IRQ linker wrap',
        'next_test_limit':'Identifies delivered event type and accounting disagreement, not necessarily physical GPU completion if an event is absent',
        'next_build_ready':False,'permission_required_for_next_build_and_hardware_test':True,
        'reports':['analysis/gpu-clear-audit/audit.md','analysis/gpu-clear-audit/sources.json'],
        'baseline_tested_inputs_and_outputs_unchanged':True,'commit_or_push_performed':False
    }
    (OUT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Static argument/bounds/dispatch and preserved-input checks: PASS')
    print('No causal project bug proven. No code fix, CIA build or runtime test.')
if __name__=='__main__':main()
