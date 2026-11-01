# Current Results and Known Limits

Reviewed **November 2, 2026**, against the latest [HANDOFF.md](../HANDOFF.md), the saved software reports, and user-supplied hardware results. These are development checkpoints, not validation of a playable game.

## Current status

| Area | Status | What has actually been verified |
| :--- | :--- | :--- |
| Original engine and intro | Completed milestone | Original ARM32 code and both intro animations run on real New 3DS hardware. |
| Original difficulty menu | Completed milestone | Select Difficulty is visible on hardware in 0.1.5, supported by a photograph and independently decoded capture. |
| Menu navigation | Experimental | Original Normal/Easy selection and confirmation work in Azahar. The 0.1.5 hardware test sent no accepted navigation events. |
| Automatic cleanup | Completed milestone | The 0.1.4 hardware test exited automatically after frame FAIL; 0.1.5 also completed cleanup at its callback limit. |
| HOME → X | Completed milestone, version-specific | Confirmed on hardware in 0.1.4. Not reverified on 0.1.5. |
| Rendering | Experimental | Native PICA200 output is visible. The frozen reference mismatch remains; readable hardware text is a separate visual observation. |
| Player-controlled gameplay | Unfinished | No controllable gameplay scene has been demonstrated on hardware. |
| Audio | Unfinished | Working sound is unconfirmed; exploratory scene probes encountered audio initialization failures. |
| Loading and performance | Experimental | A stable menu has been measured; loading still takes minutes. No gameplay FPS benchmark exists. |

## Menu 0.1.5 hardware

One real-console run reached the original **Select Difficulty** screen, with Normal highlighted. The user reported approximately eight minutes to the menu, DOWN without a visible response, and return to HOME roughly five to seven minutes later. Those are approximate observations, not precise timings.

The run completed at its **12,000-callback limit**, without registered START, HOME, or A-confirm events. Cleanup completed in one attempt: the five remaining workers terminated, no worker handles remained after joining, I/O was balanced, and the process returned. The loader had already finished earlier. This is a successful bounded menu-test exit, not a hardware confirmation of selecting difficulty or of HOME → X in this version.

The menu adapter admits navigation only after recognizing one of three full-frame fingerprints observed in Azahar. Hardware produced a different menu fingerprint, so it never admitted input or sent an original pointer DOWN event. The physical HID held mask was not logged, so this run does not independently prove button capture. The next fix must recognize menu readiness and selection without requiring whole-frame equality to the emulator, while preserving protections against repeated taps on the selected row, fading frames, and stale observations.

### Performance and memory

Stable hardware menu windows measured **24.02 FPS including diagnostics**. Average time per callback was 16.10 ms in original code, 17.00 ms in presentation, and 8.29 ms in diagnostics. Queue and VBlank waits are already included in those intervals. These numbers describe a static menu with readbacks and logging, not gameplay performance.

One 120-callback loading window took **473.286 seconds**, of which 470.513 seconds were inside original callbacks. The current aggregation cannot identify a single responsible call or separate font/atlas work from other engine activity. The summed loop windows reach the first saved menu capture at 722.046 seconds; this excludes preflight/shutdown and is not the timestamp of the first visible LCD menu. It should not replace the user's approximate observation.

The profile remains **124 MiB**, with 20 MiB normal and 100 MiB linear heap. The menu version uses an **85.5 MiB donor arena**, reduced from the earlier 92 MiB checkpoint, and an 8 MiB GPU texture cache. Recorded linear peak was 104,635,264 of 104,857,600 bytes: only **222,336 bytes** of temporary headroom. Normal allocator peak was 19,746,816 bytes. No donor refusals or runtime allocation failures were recorded; that does not prove a gameplay scene will fit.

The hardware report explicitly says not to repeat this CIA for more data. Further hardware testing requires a new software validation decision.

Sources: [hardware report](../porting/analysis/native-game-menu-v0.1.5-hardware/report.ru.md), [numerical results](../porting/analysis/native-game-menu-v0.1.5-hardware/hardware-result.json), [software report](../porting/analysis/native-game-menu-v0.1.5/report.ru.md).

## Progress 0.1.4 hardware

Two real-console runs verified the improved shutdown path:

- The first completed the intro checkpoint and automatically cleaned up after CRC FAIL, with one shutdown attempt and no STOPPED state. All six workers joined, I/O closed, and the process returned. Although the user called it the START test, the guest log did not record START; physical START registration is not separately established by that run.
- The second recorded a deferred HOME request, waited for worker quiescence, handed control to the real HOME Menu, and returned through APT close after the user chose X. This is a physical HOME → X result, beyond the earlier emulator-only test shim.

Late-loader waits were approximately **76.6 and 81.7 seconds**, with I/O progress. They are not full startup/exit timings or SD throughput measurements. Cancellation waits for the original in-flight native work; it cannot interrupt an arbitrary foreign callback or read. Forced idle/hard-deadline failures and retained-state recovery remain software-fixture results, not hardware guarantees.

Sources: [hardware report](../porting/analysis/native-game-progress-v0.1.4-hardware/report.ru.md), [numerical results](../porting/analysis/native-game-progress-v0.1.4-hardware/hardware-result.json), [software report](../porting/analysis/native-game-progress-v0.1.4/report.ru.md).

## Rendering and photographs

The intro frame remains different from the frozen software checkpoint in **9,231 of 96,000 pixels**: hardware CRC `bf2a6bfd` versus reference `ea733050`. Successful cleanup does not turn this frame failure into a pass, and menu-admission fingerprints are not a replacement for that oracle.

The user confirmed that the headphone text is readable on the console. The [hardware photographs](images/README.md) support that visual observation, without proving byte identity. An older Azahar PICA200 screenshot has distorted small text; this is not sufficient evidence of a hardware text defect. GPU textures, UVs, shaders, or filtering should not be changed solely to make those two emulator images match.

The README's intro photograph comes from **Close 0.1.3**, whose first cleanup attempt timed out. A later START retry recovered; Progress 0.1.4 subsequently improved automatic cleanup. The failure message visible in that older photo must not be interpreted as the latest shutdown result.

## First scene and remaining work

Separate emulator probes began the first scene, but encountered two NULL reads in the EAAudioCore area and an unsupported fog state. Their safety result was false even though cleanup was reached. These were exploratory tests, not stable gameplay, and the scene-probe mode is excluded from the limited hardware package.

The next priorities are hardware menu readiness/input, loading attribution, original audio initialization, required scene graphics states, and scene memory. Movement, camera, and actions follow a working scene. Working sound, sustained gameplay, and a release date are not established.

## Historical checks and resource storage

The historical CPU baseline passed **552 ARM tests across 26 suites**. This applies to its recorded build and was not rerun for every later change. Older CPU menu images used a separate emulator-only 178 MiB profile and elevated CPU setting.

The shared-resource pilot passed one isolated normal native CXI cycle in Azahar. Only read-only `assets` and `apk-assets` were shared through NTFS junctions; other initial files and writable state stayed independent. It avoided copying 552.004 MiB of assets per compatible new run, but creating the store added a copy and no old datasets were removed. It is a storage/preparation result, not a shutdown or gameplay fix.

See [the resource-store report](../porting/analysis/shared-resource-store-pilot/report.ru.md) and [usage notes](../porting/README-shared-resources.ru.md). Raw captures, private archives, dataset inventories, snapshots, and game files remain local; some links in historical engineering reports intentionally refer to those unpublished artifacts.
