"""Host-only decision cases; no ARM suite or emulator execution."""
import copy
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from gx_watch_report import classify


def main():
    base = {'armed': True, 'fault': False, 'overflow': 0, 'decision_index': 1, 'vblank_phases': 2,
        'samples': [{'counts': dict(PSC0=0, P3D=0, PPF=1, PSC1=0, DMA=0)},
                    {'counts': dict(PSC0=1, P3D=1, PPF=2, PSC1=0, DMA=0), 'queue_stable': True,
                     'events_consistent': True, 'idle': True, 'queue': dict(total=3, submitted=3, completed=3)}],
        'submits': [{'returned': True, 'result': 0, 'words': [n] + [0] * 7} for n in [2, 1, 3]]}
    cases = []
    cases.append((base, 'queue_retired'))  # Earlier TEXCOPY PPF excluded by baseline delta.
    for name, expected in [('P3D', 'PICA_completion_or_P3D_delivery'),
                           ('PSC0', 'FILL_completion_or_PSC0_delivery'), ('PPF', 'DISPLAY_completion_or_PPF_delivery')]:
        d = copy.deepcopy(base);s = d['samples'][1];s['counts'][name] = d['samples'][0]['counts'][name];s['idle'] = False;s['queue']['completed'] = 2
        cases.append((d, expected))
    d = copy.deepcopy(base);d['samples'][1]['counts']['P3D'] = 0;cases.append((d, 'queue_idle_with_missing_observer_notifications'))
    d = copy.deepcopy(base);d['samples'][1]['idle'] = False;cases.append((d, 'queue_accounting_or_running_state_mismatch'))
    d = copy.deepcopy(base);d['samples'][1]['counts']['DMA'] = 1;cases.append((d, 'foreign_or_extra_completion_notifications'))
    d = copy.deepcopy(base);d['samples'][1]['counts']['PSC1'] = 1;cases.append((d, 'queue_retired'))
    d = copy.deepcopy(base);d['submits'][1]['result'] = 0xfffffffe;cases.append((d, 'submission_incomplete_or_error'))
    d = copy.deepcopy(base);d['submits'][1]['returned'] = False;cases.append((d, 'submission_incomplete_or_error'))
    d = copy.deepcopy(base);d['samples'][1]['events_consistent'] = False;cases.append((d, 'inconsistent_observation'))
    d = copy.deepcopy(base);d['fault'] = True;cases.append((d, 'emulator_diagnostic_fault'))
    for data, expected in cases:
        got = classify(data);assert got['classification'] == expected, (expected, got)
        assert got['physical_GPU_stall_proven'] is False
    print('PASS:', len(cases), 'host interpretation cases; no IRQ-to-command-index guessing.')


if __name__ == '__main__':
    main()
