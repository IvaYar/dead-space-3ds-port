"""Preserved startup smoke test against actual Prod124 CIA payload."""
import hashlib
import json
from pathlib import Path

P = Path(__file__).resolve().parents[1]
ROOT = P / 'analysis/azahar-native-startup-prod124-v0.1.0'


def main():
    assert not ROOT.exists(), 'Preserve existing evidence'
    original = P / 'tests/smoke_native_startup.py'
    raw = original.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == 'a63765a4dfbd299df21ada761cda9c118d16582d4afec23e7edc828b56ece3ef'
    text = raw.decode()
    for old, new in [
        ("ROOT=P/'analysis/azahar-native-startup-v0.1.0'", "ROOT=P/'analysis/azahar-native-startup-prod124-v0.1.0'"),
        ("b=P/'3ds/build-native-startup-v0.1.0';raw=(b/'startup.cia').read_bytes()",
         "b=P/'3ds/build-native-startup-v0.1.0-prod124';raw=(b/'startup-prod124.cia').read_bytes()"),
    ]:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    exec(compile(text, str(original) + ' [Prod124 host paths]', 'exec'),
         {'__name__': '__main__', '__file__': __file__})
    result = json.loads((ROOT / 'result.json').read_text())
    try:
        for cycle in result['cycles']:
            r = cycle['READY']
            assert r['pre_heap_limit_bytes'] == r['APP_region_bytes'] == 124 << 20, r
            assert r['APP_memtype_raw'] == 6 and r['pre_heap_current_bytes'] == 409600
            assert r['heap_commit_delta_bytes'] == 4 << 20
            assert r['declared_New3DS_mode_MiB'] == 178, 'Guest ELF is unchanged'
    except BaseException as error:
        result.update(passed=False, adapter_validation_failed=True, error=str(error))
        (ROOT / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        raise
    result.update(memory_mode_under_test='Prod124', actual_limit_MiB=124,
                  unchanged_guest_178_label_is_stale=True, same_guest_SD_path=True,
                  baseline_runner_sha256=hashlib.sha256(raw).hexdigest(),
                  runner_adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (ROOT / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print('Prod124 CIA: three READY/START cycles PASS; actual limit124MiB; same ELF.')


if __name__ == '__main__':
    main()
