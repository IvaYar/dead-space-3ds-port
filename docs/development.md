# Development Notes

For a quick overview, read the [README](../README.md). The [current results](verification.md) distinguish hardware observations from emulator tests. [HANDOFF.md](../HANDOFF.md) contains the detailed engineering chronology in Russian; its newest entry takes precedence over older plans and readiness decisions.

## Setup

The recorded environment is Windows/PowerShell with Python, devkitARM GCC 16.1, libctru 2.7.0, Citro3D 1.7.1, Unicorn 2.1.4, and Azahar libretro 2126.2. Python dependencies are pinned in [requirements-tools.txt](../porting/requirements-tools.txt).

From a fresh development checkout:

```powershell
python -m pip install --target porting/toolchain/python -r porting/requirements-tools.txt
python porting/tools/bootstrap_toolchain.py --with-emulator
python porting/tools/bootstrap_citro3d.py
```

These commands prepare dependencies. They do not supply the game or build a playable port. The working donor is the English Android SD edition 1.1.33; the separate Russian 1.2.0 APK is not the active donor. Compatible game files must be provided privately and lawfully.

Builders can depend on earlier local preparation, private resource receipts, derived fonts, or test state. A Git clone alone cannot reproduce every saved experiment. Exact reproduction can require the matching CXI, emulator DLL, runner, resource inventory, and initial writable state. Existing baselines and evidence should be preserved; new experiments need separate output/attempt identifiers.

## Source and test paths

| Area | Entry points |
| :--- | :--- |
| Platform and graphics adapters | [3DS source](../porting/3ds/source) and [headers](../porting/3ds/include) |
| Native menu experiment | [Menu source](../porting/tests/native_game_menu.c), [input adapter](../porting/tests/native_menu_input.h), [texture-memory adapter](../porting/tests/native_menu_texture_memory.h) |
| Current menu build and validation | [Builder](../porting/tools/build_native_game_menu.py), [smoke runner](../porting/tests/smoke_native_game_menu.py), [audit](../porting/tools/audit_native_game_menu.py), [hardware report](../porting/analysis/native-game-menu-v0.1.5-hardware/report.ru.md) |
| Progress-aware shutdown | [Source](../porting/tests/native_game_progress.c), [software report](../porting/analysis/native-game-progress-v0.1.4/report.ru.md), [hardware report](../porting/analysis/native-game-progress-v0.1.4-hardware/report.ru.md) |
| Earlier memory checkpoint | [Prod124 notes](../porting/3ds/README-native-game-prod124.ru.md), [memory report](../porting/analysis/native-game-prod124-v0.1.0/report.ru.md) |
| CPU compatibility baseline | [Runtime builder](../porting/tools/build_emulator_runtime.py); the handoff lists the 26 individual suite entry points |
| Shared immutable resources | [Resource-store notes](../porting/README-shared-resources.ru.md) |

This update publishes the current port source and selected reports without merging generated builds, the SDK, emulator SD contents, or private runtime diagnostics. The source files were copied byte-for-byte from the working development tree. Saved manifests and raw baselines were not regenerated.

The historical 552-test CPU result belongs to its recorded build. Run the suite scripts as documented rather than assuming generic test discovery. Older progress checkers may still expect an earlier count or checkpoint. Some audits rewrite summary JSON, and builders update manifests; they are not all read-only checks. Native scenarios sharing emulator/SD state must run sequentially.

The limited Menu 0.1.5 package intentionally stops shortly after confirmation. Its separate scene probes are emulator-only. The latest hardware report says not to repeat the existing CIA for more data; a future hardware candidate requires a new validation decision.

## Technical reading

- [First original frame](../porting/FIRST-FRAME.ru.md), [headphone screen](../porting/HEADPHONE-SCREEN.ru.md), and [historical CPU difficulty menu](../porting/MENU-BOOTSTRAP.ru.md).
- [Lighting](../porting/LIGHTING.ru.md) and [default-surface handling](../porting/DEFAULT-SURFACE.ru.md); [lighting results](../porting/analysis/lighting-result.json) and [engine-progress summary](../porting/analysis/engine-progress.json) retain their historical scope.
- [HID sensor backend](../porting/SENSOR-BACKEND.ru.md) and [JNI integration](../porting/SENSOR-JNI.ru.md). Forty readings were obtained in a separate Azahar experiment; hardware axes and calibration remain unverified.
- [Native startup](../porting/3ds/README-native-startup-prod124.ru.md), [target initialization](../porting/3ds/README-native-game-target-init.ru.md), and [Close 0.1.3](../porting/3ds/README-native-game-close.ru.md) preserve earlier milestones. Read the latest handoff before using old installation instructions.

## Publication and private inputs

[check_staged_private_files.py](../porting/tools/check_staged_private_files.py) checks index blobs for private paths, binary content, and private object/stack structures. Its [synthetic tests](../porting/tests/test_private_publication_guard.py) run in disposable temporary Git repositories. The hook in [.githooks/pre-commit](../.githooks/pre-commit) remains opt-in; this update does not change local hook configuration.

The guard's text-only policy flags images for separate review. The selected [documentation images](images/README.md) were reviewed individually, including their dimensions, metadata, provenance, and visible content. The guard was not broadened to accept arbitrary images or binaries.

Do not publish APKs, original libraries, extracted assets or fonts, saves, private SD contents, memory/object dumps, or raw capture archives. Some engineering-report links point to deliberately unpublished local evidence. Numerical conclusions and reports do not include those artifacts.

Selected official devkitPro simple_tri/immediate examples retain upstream provenance and Public Domain notices. Citro3D is recorded under the Zlib license. Those terms do not grant rights to the game or establish a blanket license for this repository.
