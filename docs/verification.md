# Current Results and Known Limits

Reviewed **November 2, 2026**, against the latest [HANDOFF.md](../HANDOFF.md), saved software reports, and user-supplied hardware results. The newest scene milestone is **Azahar-only**. No new console run or scene CIA was produced for it.

## Current status

| Area | Status | Verified scope |
| :--- | :--- | :--- |
| Original engine and intro | Hardware milestone | Original ARM32 code and both intro animations run on real New 3DS hardware. |
| Difficulty selection | Hardware milestone | HID 0.1.7 verified physical D-pad navigation, Normal/Easy selection, original A confirmation, and its intended safe exit. |
| Chapter I corridor | Emulator milestone | The original game reached callback 5106, with a character in RIG and the MOVEMENT CONTROLS tutorial visible in Azahar. |
| Movement and camera | Unfinished | Gameplay input has not been connected or confirmed. Menu input alone does not establish it. |
| Scene audio initialization | Experimental | Original audio Init and mixer run through the compatibility layer into a timed PCM sink. No audible NDSP backend yet. |
| Scene graphics | Experimental | Required fog/COMBINE and projective-texture paths have been exercised. Unsupported states still fail closed; visual and reference differences remain. |
| Texture residency | Experimental | Invisible-draw uploads were avoided; lossless Morton/LZ4 backing reduced later reload cost. Full GPU cache thrashing remains. |
| Shutdown | Version-specific milestones | Successful scene runs cleaned up in Azahar; hardware HOME → X was verified in 0.1.4, and bounded confirmation exit in 0.1.7. |
| Playable release | Unfinished | No stable, player-controlled gameplay or general playable package. |

## Latest scene checkpoint

The original game progressed through its opening prologue and into **Chapter I — Honorable Intentions**, showing a character in RIG in the corridor. The latest normal run reached **callback 5106** and the original **MOVEMENT CONTROLS** tutorial. The visible character is established by the image; a particular resource/model identity such as `isaac.m3g` was not independently proven.

The [public capture](images/azahar-chapter-one.png) is from `azahar-native-menu-v0.1.7-morton06-chapter/screen-5106.png`. Its upper-screen preview is used in the README. It is output of the original engine through the port in Azahar, not a hardware photograph or a synthetic scene. Scene state, character position, and the original timestep were not manually changed to reach it.

The `morton05:long2` run reached callback 4951; `morton06:chapter` reached 5106, with 784 callbacks after the original confirmation at 4322. Both returned at their explicit guest-time budgets and completed cleanup. The chapter run included roughly 180 callbacks in the first corridor. These are observed engine callbacks, not gameplay FPS or proof of input.

The current adapter admits menu pointer events while the original difficulty layer is ready. It does not yet deliver the scene's movement/camera contract. The next task is to identify and use the original touch/analog events, rather than writing character state directly.

Source: [regional residency and Morton report](../porting/analysis/regional-texture-residency/report.ru.md), [numerical result](../porting/analysis/regional-texture-residency/result.json).

## Texture work and performance

All measurements below are from the documented **Azahar CPU100/OpenGL** experiments, not hardware benchmarks. Each comparison concerns its stated phase; different scenes must not be treated as the same frame.

| Phase | Observation | Limits |
| :--- | :--- | :--- |
| Early prologue | Callback time fell from 14.429 s to about 0.451 s, approximately 32×, after moving texture materialization past clipping/culling. Steady page loads, uploads, and GPU allocations fell from 17 to zero. | This removed work for invisible draws; it did not eliminate later visible working-set pressure. |
| Late station, matched window 4420–4435 | Median callback fell from 19.935 s to 8.889 s, approximately 2.24×, using lossless compressed Morton backing. Reads fell from 51,003,396 to 18,405,917 bytes. | There are still 29 GPU allocations/evictions and 29 full-image Morton loads per callback. |
| Chapter I corridor | Approximately 5.61 s per callback, with 14 GPU allocations and 14 Morton loads. | A different scene, with no reached old-backend control; no speedup or gameplay FPS is claimed for it. |

The late visible working set contains 25 textures totaling 34,226,432 bytes, exceeding the 8 MiB GPU cache. Storing the verified full Morton image after its first upload avoids re-reading canonical pages and repeating conversion on later misses. The backing uses lossless **LZ4 v1.10.0**, with bounded metadata and scratch space, safe decode, encoded/decoded CRC checks, and existing texture invalidation/lifetime rules.

Regional cropping was **not deployed**. Whole-draw rectangle models increased pressure; a later selective hybrid model could not reduce GPU misses below 29. It reduced compressed reads by at most 7.8% without adding misses, before unmodelled runtime overhead. That did not justify a regional runtime rewrite. The implementation retains full-image Morton backing.

Sources: [texture working-set report](../porting/analysis/native-scene-textures/report.ru.md), [Morton report](../porting/analysis/regional-texture-residency/report.ru.md), [selective hybrid model](../porting/analysis/regional-texture-residency/hybrid-4430.json).

## Audio, graphics, and memory

The original Java-side audio contract required native audio Init with an AudioTrack-like compatibility object before the game lifecycle calls. The corrected adapter provides typed short arrays and the required play/stop/write interfaces; the original mixer feeds a bounded, timed PCM sink. **This is not audible console sound.** The earlier NULL audio reads are absent on the successful scene path, and audio workers are stopped before the job workers they depend on.

Required fog and texture COMBINE states were added through the existing PICA backend. Projective sampler 0 is supported on the reached path; sampler 1 supports the tested constant positive q case, while variable q remains an explicit rejection. No blanket GLES compatibility is claimed.

Normal heap, linear heap, and donor arena reservations remain **20 MiB / 100 MiB / 85.5 MiB**; CPU texture residency remains 6 MiB and GPU cache 8 MiB with 32 entries. The recorded global linear peak leaves **222,336 bytes** of headroom. Morton scratch and diagnostics increased process commit, but did not raise the application limit or these reservations. Boundary free-space observations do not guarantee space for later transients or a complete gameplay scene.

Successful Morton runs reported no donor/runtime allocation refusals, GL errors, or failed submissions. Earlier failed trials and recovered allocator-pressure retries remain separately recorded. The first long attempt hit an old host frame cap and is **not** counted as a safe exit; successful reruns used the corrected independent deadline.

Sources: [first-scene report](../porting/analysis/native-first-scene/report.ru.md), [texture report](../porting/analysis/native-scene-textures/report.ru.md), [Morton audit results](../porting/analysis/regional-texture-residency/result.json).

## Validation scope

Saved successful runs include 16 CPU/PICA pixel comparisons within 2/255 per channel, dirty/FBO eviction and reload checks, 21 store checks including 14 rejected corruptions, and 73 exact ARM CRC vectors. Independent LZ4/zlib decoding and a NumPy Morton reference compared all 25 late textures byte-for-byte with canonical pixels, covering 34,226,432 bytes. The chapter snapshot had 27 decoded images, with 26 compared to disk canonical backing; one canonical image remained resident.

Eight successful audited runs covered 855 capture CRC checks with no reported GX truncation. Successful scene/START/HOME cases joined the five workers, left no worker handles, balanced I/O, and completed cooperative cleanup. Three early menu frames in a HOME fixture did not equal the baseline and remain explicitly recorded. The old sticky **FRAME FAIL / `ea733050`** gate and EA/headphone artifact were not weakened or declared fixed.

These saved software checks do not prove the scene on hardware, arbitrary callback cancellation, audible output, complete rendering equivalence, or sustained gameplay. Original compatibility and texture checks remain separate from the new screenshot's visual milestone.

## Latest hardware milestone: HID 0.1.7

The user verified physical D-pad Normal → Easy → Normal → Easy and A confirmation through original pointer callbacks, followed by the limited package's intended safe exit. The input queue preserved a recorded A press even when the main SDK snapshot was already zero. Circle Pad was not separately tested, and this was not a gameplay scene test.

Earlier 0.1.5 menu-admission and 0.1.6 capture failures are historical; they no longer describe the latest verified menu state. The physical HOME → X proof remains the separate **0.1.4** result, not a claim about every later version. Loading and scheduling delays on hardware remain relevant, and the new texture optimizations have no new hardware measurements.

Sources: [HID hardware report](../porting/analysis/native-game-hid-v0.1.7-hardware/report.ru.md), [HID numerical result](../porting/analysis/native-game-hid-v0.1.7-hardware/hardware-result.json), [Progress 0.1.4 hardware report](../porting/analysis/native-game-progress-v0.1.4-hardware/report.ru.md).

## Historical context and publication

The historical CPU baseline passed 552 ARM tests across 26 suites; that number belongs to its recorded build. The shared-resource pilot established a preparation/storage layout, not a gameplay or shutdown fix. Earlier hardware intro/reference differences remain tracked, and readable console text is a visual observation rather than proof of byte equality.

Only the explicitly selected screenshot was added to the public gallery. Raw capture collections, game resources, private datasets, SD state, memory/object dumps, and builds remain local. Some links in engineering reports intentionally refer to unpublished evidence. The LZ4 source is included with its BSD license and source provenance.
