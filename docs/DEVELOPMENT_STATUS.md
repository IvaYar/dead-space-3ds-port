# Development Status

Current snapshot of the port, with the milestone history that led here. For measured numbers and validation scope see [verification.md](verification.md); for the full engineering chronology (in Russian) see [HANDOFF.md](../HANDOFF.md).

**Overall state: experimental port — work in progress. No playable release.**

## Where the project stands (November 2026)

**Latest hardware milestone — HW05 (real New Nintendo 3DS).** The original engine ran on the console for approximately 75 minutes: original menu rendering and input, native GPU rendering of real game visuals, 5,312 completed engine callbacks, 39,738 GPU draw calls, 15,542 GPU submits with zero recorded failed submits. The run stopped at an intentional `SCENE_BUDGET` limit — a planned boundary, not a crash — with no GPU timeout or memory allocation failure recorded, and completed a fully cooperative shutdown and safe exit.

**Latest emulator milestone — gameplay07 (Azahar).** The original movement chain is verified end to end: Circle Pad → original JNI pointer events → the game's own virtual joystick → character controller → physics, with confirmed forward/backward movement and stopping in Chapter I.

**Still open:** interactive gameplay on hardware, physical character movement on hardware, playable frame rate, camera/shooting/full audio, complete progression, and the unresolved framebuffer CRC mismatch (`FRAME FAIL`, reference `ea733050`). Hardware scene performance is extremely low — approximately one rendered frame per five seconds (informal observation, not a benchmark).

## Milestone history

Newest first. "Hardware" means a real New Nintendo 3DS; "Azahar" means the emulator.

| Milestone | Platform | Result |
| :--- | :--- | :--- |
| HW05 | Hardware | First sustained original-engine run: menu, native GPU visuals, ~75 minutes, zero failed submits, cooperative safe exit at an intentional scene budget. |
| HW04 | Hardware | Two short diagnostic runs blocked in an early failure path (recorded GL error, no safe exit). Superseded by HW05. |
| HW03 | Hardware | Bounded GPU diagnostics; cleanup blocked at the final GPU drain, power-off required. Evidence preserved; direct precursor of the HW04/HW05 shutdown work. |
| HW02 | Hardware | SD preflight fixed and passing; early GPU synchronization failure in the engine phase, no safe exit. |
| HW01 | Hardware | First gameplay-candidate test; stopped at SD preflight. Root cause identified and fixed in HW02. |
| gameplay07 | Azahar | Movement PASS through the original input chain. |
| gameplay02–06 | Azahar | Input-chain development: admission guards, event freshness, HUD joystick capture/release confirmed; movement not yet achieved (Movement FAIL in 06, root-caused and fixed in 07). |
| morton05/06 | Azahar | Chapter I corridor reached (callback 5,106) with MOVEMENT CONTROLS visible; lossless Morton/LZ4 texture backing landed (~32× early prologue, ~2.24× late station, unchanged budgets). |
| HID 0.1.7 | Hardware | Physical D-pad navigation, Normal/Easy selection, and A confirmation through the original engine; intended safe exit. |
| Menu 0.1.5 / 0.1.6 | Hardware | Menu admission verified (0.1.5); a capture-path failure in 0.1.6 is historical. |
| Close 0.1.3 / Progress 0.1.4 | Hardware | Original intro rendering (0.1.3); verified HOME → X cooperative exit (0.1.4). |
| Stable 0.1.2 and earlier | Hardware/Azahar | Native startup, memory profile (Prod124), first original frames, CPU compatibility baseline (552 ARM tests, 26 suites — historical, tied to its recorded build). |

## Performance notes

All performance numbers come from the documented Azahar CPU100/OpenGL experiments unless stated otherwise:

- Early prologue callbacks: ~14.4 s → ~0.45 s (about 32×) after invisible-draw texture work was eliminated.
- Late station, matched window: median callback ~19.9 s → ~8.9 s (about 2.24×) with lossless Morton/LZ4 backing.
- Chapter I corridor (Azahar): ~5.6 s per callback in the observed window.
- Hardware (HW05): approximately one rendered frame per five seconds in the observed scene — informal observation, not a benchmark.

## Evidence policy

Hardware-run journals, SD contents, raw captures, memory dumps, game resources, and build artifacts are preserved locally and are **not** published. Public documentation contains selected reviewed images and numerical summaries only; some engineering-report links intentionally point to unpublished local evidence. The staged-file guard ([check_staged_private_files.py](../porting/tools/check_staged_private_files.py)) blocks private material from commits.

## Next steps

No fixed order, no release date:

- Reproduce interactive Chapter I gameplay on real hardware.
- Investigate and reduce scene rendering cost on the PICA200 path.
- Resolve the framebuffer CRC mismatch against the frozen reference.
- Add audible NDSP audio output behind the working original mixer.
- Validate New 3DS XL / New 2DS XL.
