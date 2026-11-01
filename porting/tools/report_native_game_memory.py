"""Summarize measured checkpoint allocator use, separately from committed heaps."""
import hashlib
import json
from pathlib import Path

P = Path(__file__).resolve().parents[1]
A = P / 'analysis/native-game-memory-v0.1.0'
RUN = P / 'analysis/azahar-native-game-v0.1.0-mem1-cxi'


def main():
    test = json.loads((RUN / 'result.json').read_text())
    assert test['passed'] and test['baseline_RGB565_exact'] and test['safe_exit']
    assert test['shutdown_proof']['kernel_joins'] == 6 and not test['shutdown_proof']['worker_handles_remaining']
    logfile = RUN / 'cycle-0001/native-game.log'
    samples = [json.loads(line.removeprefix('MEMJSON '))
               for line in logfile.read_text().splitlines() if line.startswith('MEMJSON ')]
    assert len(samples) >= test['actual_callback']
    assert all(s['query_result'] == 0 and s['limit'] == 178 << 20 for s in samples)
    assert not any(s['donor_refusals'] or s['runtime_failures'] for s in samples)
    peak = lambda name: max(s[name] for s in samples)
    other_linear = max((132 << 20) - s['linear_free'] - s['donor_arena_reserved'] for s in samples)
    static_and_stack = samples[0]['commit'] - (172 << 20)
    donor_bound = peak('donor_brk_peak') + peak('donor_map_peak_pages') * 4096
    result = {
        'emulator_only': True, 'hardware_game_memory_measured': False,
        'original_checkpoint_and_safe_exit_pass': True,
        'baseline_different_pixels': test['different_pixels'], 'donor_kernel_joins': 6,
        'sample_count': len(samples), 'actual_callback': test['actual_callback'],
        'committed_process_bytes': peak('commit'), 'requested_heaps_bytes': 172 << 20,
        'static_stack_extra_commit_bytes': static_and_stack,
        'donor_arena_reserved_bytes': 128 << 20,
        'donor_brk_exact_high_water_bytes': peak('donor_brk_peak'),
        'donor_map_exact_peak_bytes': peak('donor_map_peak_pages') * 4096,
        'donor_brk_plus_map_peaks_bound_bytes': donor_bound,
        'normal_allocated_sampled_max_bytes': peak('normal_allocated'),
        'normal_allocator_arena_sampled_max_bytes': peak('normal_allocator_arena'),
        'runtime_exact_peak_bytes_SUBSET_of_normal_heap': peak('runtime_peak'),
        'other_linear_sampled_max_bytes': other_linear,
        'nonoverlapping_sum_of_sampled_maxima_and_donor_high_water_bytes':
            peak('normal_allocated') + donor_bound + other_linear + static_and_stack,
        'sum_using_normal_allocator_arena_bytes':
            peak('normal_allocator_arena') + donor_bound + other_linear + static_and_stack,
        'not_a_proven_total_gameplay_peak': True,
        'full_arena_and_normal_heaps_were_not_reduced': True,
        'one_frame_could_fit_124_is_inference_not_tested': True,
        'candidate_for_future_validation_only': {
            'normal_heap_MiB': 20, 'linear_heap_MiB': 100, 'donor_arena_MiB': 96,
            'other_linear_budget_MiB': 4, 'total_heaps_MiB': 120,
            'changes_implemented': False, 'full_gameplay_sufficiency_proven': False},
        'log_sha256': hashlib.sha256(logfile.read_bytes()).hexdigest(),
        'CXI_sha256': test['CXI_sha256'],
        'limitations': ['normal/linear samples can miss transient between-callback peaks',
                        'donor sbrk high-water is allocator backing, not live C++ object bytes',
                        'runtime peak is already included in normal malloc use; never add twice',
                        '128MiB arena remains a real committed allocation in this run',
                        'only startup/UI checkpoint measured; later loaders/scenes may grow'],
        'samples': samples,
    }
    (A / 'measurements.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'samples'}, indent=2))


if __name__ == '__main__':
    main()
