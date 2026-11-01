# Development Notes

This page preserves setup context and technical pointers from the previous project overview. For current status, read the [verification summary](verification.md), prepared from the latest local handoff and verified reports. The published [HANDOFF.md](../HANDOFF.md) retains earlier history. Historical reports describe the builds they tested and can contain superseded next steps.

## Environment and prerequisites

The recorded development environment is Windows/PowerShell with Python, devkitARM GCC 16.1, libctru 2.7.0, Citro3D 1.7.1, Unicorn 2.1.4, and Azahar libretro 2126.2. Python dependencies are pinned in [requirements-tools.txt](../porting/requirements-tools.txt). Toolchain bootstrapping is implemented in [bootstrap_toolchain.py](../porting/tools/bootstrap_toolchain.py); Citro3D has a separate [bootstrap helper](../porting/tools/bootstrap_citro3d.py).

The working donor is the English Android SD edition 1.1.33. The separate Russian 1.2.0 APK is not the active donor. Original game binaries, resources, derived fonts, saves, emulator SD contents, and test snapshots remain private. A Git clone alone cannot reproduce every recorded experiment. Exact reproduction can also require the matching CXI, emulator DLL, runner, resource inventory, and initial writable state.

This publication updates documentation only. Newer native checkpoint sources remain on development branches or in the local workspace; `main` does not contain every experiment described here. Pinned links preserve already published technical references without merging those source changes.

In a fresh checkout, prepare dependencies from the repository root:

```powershell
python -m pip install --target porting/toolchain/python -r porting/requirements-tools.txt
python porting/tools/bootstrap_toolchain.py --with-emulator
python porting/tools/bootstrap_citro3d.py
```

These are dependency setup commands, not a complete build recipe. The builders depend on private inputs and earlier preparation steps. Do not overwrite a saved build or its manifests just to reproduce a historical command.

## Choosing a build and test path

| Path | Entry points and constraints |
| :--- | :--- |
| CPU compatibility baseline | [build_emulator_runtime.py](../porting/tools/build_emulator_runtime.py) builds the computer-only runtime experiment. [HANDOFF.md](../HANDOFF.md) lists the 26 suite entry points; run the individual scripts as documented rather than assuming generic test discovery. Preserve the old CPU evidence before rebuilding. |
| Native 124 MiB checkpoint | [Prod124 documentation](https://github.com/IvaYar/dead-space-3ds-port/blob/8b1839c207ca51e2afbd73c93639b97ab8bf08b5/porting/3ds/README-native-game-prod124.ru.md) explains the memory-reduction steps, build profiles, and original frame verification. Its hardware instructions are historical; consult the latest handoff first. |
| Shutdown and late-loader work | [Close 0.1.3 documentation](verification.md#shutdown-work) describes isolated software attempts and the saved validation matrix. The [latest hardware report](verification.md#hardware-results) supersedes the original readiness decision. Do not repeat the current CIA for more data. |
| Shared immutable assets | [Resource-store pilot](verification.md#resource-store-pilot) documents the opt-in Windows/NTFS layout. Only selected read-only runs use it; mutating runners still require independent copies. |

Some audits regenerate summary JSON, and builders update manifests. They are not all read-only documentation checks. Native scenarios using the same emulator/SD state must run sequentially. New experiments need distinct output/attempt identifiers; existing evidence and baselines should be retained.

The recorded 552-test CPU result predates later GPU and shutdown work. The original CPU binary and newer sources must not be represented as the same verified build. Historical progress checkers can still expect older test totals or checkpoints; inspect their scope before interpreting a result.

## Earlier milestones retained for context

- The strict import preflight recorded 154 bindings, 234 unresolved required symbols, and four weak symbols at its documented checkpoint. Experimental runtime overlays are explicit; that count does not mean all later game paths are supported.
- Real hardware has executed all 209 original constructors, passed native executable-memory checks, and run original callbacks. These observations do not prove the full game lifecycle.
- The DS34 GPU hardware fixture completed the RGBA8-to-RGB8 path, GPU completion and pixel checks, and return to HOME. It is separate from validation of the full game.
- Startup-only tests reached main/READY/START/HOME in Legacy64 and New 3DS Prod124 profiles. The older Dev1 178 MiB configuration stalled before observable READY; the exact cause was not established.
- The early Prod124 software checkpoint recorded 120.746 MiB process commit. Later loading increased the normal allocator footprint to about 18.33 MiB of its 20 MiB heap. These are checkpoint measurements, not a guarantee that a gameplay scene fits.
- A one-time color-target clear removed the uninitialized background seen in earlier hardware frames. The remaining 9,231-pixel hardware/reference difference is still unresolved.
- The sensor JNI experiment obtained 40 readings in a separate Azahar test. Hardware axis mapping and calibration remain unverified.
- Partial geometry and completed black frames are retained as different outcomes. A returned callback is not proof of working gameplay.

The latest hardware test adds successful manual recovery after START retry. Automatic shutdown and HOME → X still require further work. Consult the main [README](../README.md#current-development-status) and [verification summary](verification.md) before using any older installation or test instructions.

## Public documentation boundaries

Only the three reviewed screenshots in [docs/images](images/README.md) were prepared for this presentation. Their source captures and all existing evidence remain unchanged. The screenshots do not include emulator desktop UI, file paths, personal data, or diagnostic overlays.

The repository uses a narrow ignore allowlist. the local staged-file publication guard examines staged blobs for private paths, binary content, and private diagnostic structures. Its text-only policy deliberately flags PNG files as requiring separate publication review. The three selected image files received separate visual and decoded-pixel review before publication. The local guard and its optional hook configuration were not changed. The guard itself is part of the local development work and is not included in this documentation-only update.

Selected official devkitPro simple_tri/immediate examples preserve their upstream URL, commit, hashes, and Public Domain notices. Citro3D is recorded under the Zlib license. These third-party terms do not grant rights to the proprietary game or establish a blanket license for this repository.
