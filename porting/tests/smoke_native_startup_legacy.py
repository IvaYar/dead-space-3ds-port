"""Run the preserved startup smoke test against the Legacy CIA, without editing it."""
import hashlib
import json
from pathlib import Path

P = Path(__file__).resolve().parents[1]
ROOT = P / 'analysis/azahar-native-startup-legacy-v0.1.0-r2'


def main():
    assert not ROOT.exists(), 'Preserve existing evidence'
    original = P / 'tests/smoke_native_startup.py'
    raw = original.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == 'a63765a4dfbd299df21ada761cda9c118d16582d4afec23e7edc828b56ece3ef'
    text = raw.decode()
    # Reuse all existing checks and START handling. Only host evidence/build paths
    # and CIA filename change; guest SD path and original runner remain identical.
    for old, new in [
        ("ROOT=P/'analysis/azahar-native-startup-v0.1.0'", "ROOT=P/'analysis/azahar-native-startup-legacy-v0.1.0-r2'"),
        ("b=P/'3ds/build-native-startup-v0.1.0';raw=(b/'startup.cia').read_bytes()",
         "b=P/'3ds/build-native-startup-v0.1.0-legacy';raw=(b/'startup-legacy.cia').read_bytes()"),
    ]:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    scope = {'__name__': '__main__', '__file__': __file__}
    exec(compile(text, str(original) + ' [Legacy host paths]', 'exec'), scope)
    result = json.loads((ROOT / 'result.json').read_text())
    for cycle in result['cycles']:
        ready = cycle['READY']
        assert ready['pre_heap_limit_bytes'] == 64 << 20, ready
        assert ready['APP_region_bytes'] == 64 << 20 and ready['APP_memtype_raw'] == 6, ready
        assert ready['pre_heap_current_bytes'] == 409600 and ready['heap_commit_delta_bytes'] == 4 << 20
        assert ready['declared_New3DS_mode_MiB'] == 178, 'Original guest label is intentionally unchanged'
    result.update(memory_mode_under_test='Legacy', actual_limit_MiB=64,
                  unchanged_guest_178_label_is_stale=True, same_guest_SD_path=True,
                  baseline_runner_sha256=hashlib.sha256(raw).hexdigest(),
                  runner_adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (ROOT / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Legacy CIA: three READY/START cycles PASS; actual limit64MiB; unmodified ELF, old 178 label retained.')


if __name__ == '__main__':
    main()
