# Technical Architecture

This document describes how the port runs the original Dead Space Mobile engine on New Nintendo 3DS hardware. For the high-level overview see the [README](../README.md); for measured results see [verification.md](verification.md).

## Execution model

The working donor is the **English Android SD edition 1.1.33**. The port loads the game's original ARM32 shared library, applies its relocations, and executes the code **natively on the 3DS ARM11 CPU** — both platforms are ARM, so no instruction-set emulation happens at runtime. The original engine source is unavailable; the engine binary is treated as an opaque, unmodified component. Its integrity is tracked by hash (selected library SHA-256 `dd422723…d3c1eb`).

The port does **not** boot Android and does not emulate a phone. Instead, it recreates only the platform surface the game actually uses.

Unicorn is used in the tooling layer (offline ARM analysis and instruction-level fixtures), not in the on-device execution path.

## Compatibility layer

The Android environment is recreated as a set of native modules in [porting/3ds/source](../porting/3ds/source) with headers in [porting/3ds/include](../porting/3ds/include):

| Subsystem | Role | Modules |
| :--- | :--- | :--- |
| Core runtime | Bionic-style libc services, stdio, time, C++ runtime support | ds6, ds8 |
| Threading | Worker threads used by the original job/audio systems, on libctru | ds7 |
| JNI bridge | The original JNI entry points the game calls and exports | ds10 |
| Platform services | Android platform glue and 3DS-backed implementations | ds11, ds17 |
| Sensors | Accelerometer path into the original sensor JNI contract | ds12 |
| Assets and files | Asset/directory/file access mapped onto the 3DS filesystem | ds19, ds20, ds24, ds25 |
| Touch | Android MotionEvent-compatible pointer delivery (module 1000, pointer 0) | ds23 |
| Strings | Android string resources expected by the game | ds18 |
| Allocator | Donor arena and bounded runtime allocation | ds29 |

Input preserves the original contract end to end: a HID collector samples the Circle Pad and buttons, the touch adapter converts them into Android-style pointer events (DOWN/MOVE/UP, 320×240 source scaled to the 400×240 surface), and those events enter the engine through its own JNI pointer callback. The game's HUD-owned virtual joystick, character controller, and physics then drive movement — the port never writes character state directly. This chain is verified in Azahar (gameplay07), including capture/release of the pointer by the original joystick and movement stop on release.

## Graphics

The game speaks **OpenGL ES 1.x**. The port translates those calls onto the **PICA200** fixed-function GPU through **Citro3D** command buffers:

- GLES state (matrices, arrays, textures, fog, lighting, texture combiners) is mapped onto PICA200 combiner stages — ds13–ds16, ds21–ds22, ds30–ds32, ds33.
- The PICA shader backend handles the geometry path (ds34, with its `.v.pica` shader).
- Required fog and texture COMBINE states were added as the original scenes exercised them; projective texturing is supported for the reached path (sampler 1 supports the tested constant positive `q` case; variable `q` is an explicit rejection). Unsupported states **fail closed** rather than rendering incorrectly; no blanket GLES compatibility is claimed.
- A separate **CPU software renderer** is kept as a debugging and pixel-comparison reference.

The sticky framebuffer CRC gate (`FRAME FAIL`, reference CRC `ea733050`) is an intentional regression oracle: rendered frames are compared against a frozen reference, and the current mismatch is recorded honestly rather than disabled.

## Texture pipeline

Game textures are converted ahead of use and stored in a **lossless Morton-ordered, LZ4-compressed** backing (unmodified LZ4 v1.10.0, BSD license, in [porting/3ds/vendor](../porting/3ds/vendor)):

- Textures are materialized only after clipping/culling proves them visible, removing repeated conversion of invisible draws (about **32×** faster early-prologue callbacks in the documented Azahar experiment).
- The compressed backing is paged within fixed budgets — 6 MiB CPU texture residency, 8 MiB GPU cache with 32 entries — against a late-scene working set of ~34 MB. Matched late-station windows improved about **2.24×**.
- Encoded and decoded CRC checks, bounded scratch space, and existing invalidation/lifetime rules keep the backing lossless; a NumPy Morton reference and independent LZ4/zlib decoders verified the late texture set byte-for-byte.

## Memory layout

The application runs in the New 3DS **124 MiB** profile with fixed reservations:

| Region | Budget |
| :--- | :--- |
| Normal heap | 20 MiB |
| Linear heap | 100 MiB |
| Donor arena (original engine) | 85.5 MiB |

The recorded global linear peak leaves **222,336 bytes** of headroom. This is enough for the documented scene runs, but it does not establish a sustained gameplay memory budget. Original 3DS models are outside this memory profile; New 3DS XL / New 2DS XL validation is pending.

## Audio

The original Java-side audio contract requires a native audio Init with an AudioTrack-like object before the game lifecycle calls. The adapter provides typed short arrays and the required play/stop/write interfaces, and the **original mixer runs into a bounded, timed PCM sink**. There is no audible NDSP output yet.

## Shutdown behavior

Shutdown is phased and audited: workers are joined before the subsystems they depend on are torn down, I/O is balanced (opens/closes), the GPU queue is drained before GPU teardown, and the process returns to the HOME Menu only after cleanup completes. HW05 recorded a fully cooperative exit (shutdown phases, GPU drain, zero remaining handles, `PROCESS return … cleanup=complete`).

## Validation approach

- Saved ARM fixtures and linked-SDK checks exercise individual compatibility behaviors (the historical CPU baseline passed 552 ARM tests across 26 suites; newer suites are recorded per milestone).
- CPU/PICA pixel comparisons within 2/255 per channel, dirty/FBO eviction and reload checks, and exact ARM CRC vectors guard the rendering path.
- Hardware runs write bounded journals and machine-readable results to SD; each run's evidence is preserved locally.
- Publication is guarded: [check_staged_private_files.py](../porting/tools/check_staged_private_files.py) blocks private paths, binaries, and private dumps from staged commits. Game resources, memory dumps, raw captures, and build artifacts stay local.

## Source map

| Area | Paths |
| :--- | :--- |
| Platform and graphics adapters | [porting/3ds/source](../porting/3ds/source), [porting/3ds/include](../porting/3ds/include) |
| Tests and runners | [porting/tests](../porting/tests) |
| Builders and analysis tools | [porting/tools](../porting/tools) |
| Engineering reports (mostly Russian) | [porting/analysis](../porting/analysis), [HANDOFF.md](../HANDOFF.md) |
