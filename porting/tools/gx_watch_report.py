"""Conservative interpretation of delivered events and independent queue state."""
import argparse
import json
from pathlib import Path


def classify(observation):
    out = {'physical_GPU_stall_proven': False,
           'note': 'Event callbacks measure delivery after SDK handling, not physical engine status.'}
    if not observation.get('armed'):
        return out | {'classification': 'setup_incomplete'}
    if observation.get('fault'):
        return out | {'classification': 'emulator_diagnostic_fault', 'native_inference_valid': False}
    sample = observation['samples'][observation['decision_index']]
    baseline = observation['samples'][0]['counts']
    delta = {name: sample['counts'].get(name, 0) - baseline.get(name, 0)
             for name in ['PSC0', 'P3D', 'PPF', 'PSC1', 'DMA']}
    out |= {'decision_before_NONBLOCK': True, 'event_deltas': delta, 'queue': sample['queue'],
            'SDK_queue_idle': sample['idle'], 'vblank_phases': observation.get('vblank_phases', 0)}
    if observation.get('overflow') or not sample['queue_stable'] or not sample['events_consistent']:
        return out | {'classification': 'inconsistent_observation'}
    submits = observation.get('submits', [])
    if len(submits) != 3 or any(not s['returned'] or s['result'] & 0x80000000 for s in submits):
        return out | {'classification': 'submission_incomplete_or_error'}
    if [s['words'][0] & 255 for s in submits] != [2, 1, 3]:
        return out | {'classification': 'unexpected_submission_set'}
    q = sample['queue']
    if q['total'] != 3 or q['submitted'] != 3 or q['completed'] > 3:
        return out | {'classification': 'dispatch_or_queue_lifecycle_mismatch'}
    missing = [name for name in ['PSC0', 'P3D', 'PPF'] if delta[name] == 0]
    out['missing_notifications'] = missing
    if delta['DMA'] or any(delta[n] > 1 for n in ['PSC0', 'P3D', 'PPF']):
        return out | {'classification': 'foreign_or_extra_completion_notifications'}
    if sample['idle'] and q['completed'] == 3:
        if missing:
            return out | {'classification': 'queue_idle_with_missing_observer_notifications'}
        return out | {'classification': 'queue_retired' if observation.get('vblank_phases') == 2 else 'queue_idle_VBlank_not_confirmed'}
    if not missing or sample['idle'] or q['completed'] == 3:
        return out | {'classification': 'queue_accounting_or_running_state_mismatch'}
    candidates = {'P3D': 'PICA_completion_or_P3D_delivery', 'PSC0': 'FILL_completion_or_PSC0_delivery',
                  'PPF': 'DISPLAY_completion_or_PPF_delivery'}
    return out | {'classification': candidates[missing[0]] if len(missing) == 1 else 'multiple_missing_completion_notifications'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('observation', type=Path)
    args = parser.parse_args()
    print(json.dumps(classify(json.loads(args.observation.read_text())), indent=2))


if __name__ == '__main__':
    main()
