# Verification Notes

Status reviewed on **November 1, 2026**. This English summary was prepared from the current local `HANDOFF.md` and the verified project reports listed below. It publishes conclusions and selected numerical results, without raw game captures, save state, worker/object dumps, or private resource inventories.

This is a documentation-only update to `main`. Some experiments described here exist in development branches or the local workspace; their presence in this summary does not mean their source or build artifacts have been merged into `main`. The published [HANDOFF.md](../HANDOFF.md) preserves earlier engineering history.

## Hardware results

Real New Nintendo 3DS hardware executes original Android engine code and has displayed both the EA and Isaac/headphone intro animations. **Stable player-controlled gameplay has not been demonstrated.**

The latest recorded test is **Close 0.1.3, run-0001**:

| Observation | Result and scope |
| :--- | :--- |
| Original callbacks | 600 callbacks returned; the intro animations were observed by the user. |
| Frame verification | Frame remains FAIL: hardware CRC `bf2a6bfd` differs from the frozen software checkpoint `ea733050`. |
| Remaining image difference | 9,231 of 96,000 pixels differ from the reference; the final capture is byte-identical to the preceding Stable 0.1.2 hardware capture. |
| First automatic cleanup | Timed out after approximately 60 seconds while the late loader continued making I/O progress; all six workers were still live at the timeout. |
| Manual recovery | After a later START retry, the loader had completed, all six workers terminated, worker handles were joined, I/O closed, GPU cleanup ran, and the process returned. The user confirmed return to normal console operation/HOME. |
| Final scope | Manual recovery succeeded. Automatic shutdown did not pass. HOME → X and POWER were not tested in this run. |

The successful retry preserves the frame failure; cleanup success does not turn a failed frame into a rendering pass. Separate hardware measurement of heap release was not recorded. The test does not directly exercise the newly added pending-delegate pump because no delegate was pending at the observed timeout.

The observed I/O counters measure application progress, not the physical throughput of the SD card. These results do not establish a GPU hang, an out-of-memory failure, or a complete gameplay memory budget.

**Do not repeat the current diagnostic CIA to collect more data.** It is not a playable release. The next candidate depends on software work and a new validation decision.

Evidence basis: local `porting/analysis/native-game-close-v0.1.3-hardware/report.ru.md`, `hardware-result.json`, and the latest handoff entry. The underlying private archive and diagnostics are not part of this publication.

## Software validation

The separate Close 0.1.3 software report records ten completed processes and one retained negative case. Completed cases exercised normal checkpoint exit, frame-failure cleanup, the reproduced late-loader state, selected HOME/cancel paths, and the actual CIA payload in Azahar. The retained negative case kept resources live and reported incomplete cleanup rather than freeing memory still in use.

The normal checkpoint and eight-frame sequence retained exact 96,000-pixel agreement with the frozen GPU reference. Completed cases checked six kernel joins, zero worker handles, balanced I/O, GPU/GSP release, and heap cleanup. These results apply to that saved software validation matrix, not to arbitrary future scenes or hardware runs.

The HOME request was injected at a safe main-thread boundary. A test-only SDK object replaced Azahar's unsupported wait for HOME screenshot readiness; the normal CXI and CIA did not contain that shim. This is a limited software proof, not validation of the physical HOME button, real HOME Menu/Luma behavior, or HOME → X on the console.

The later hardware result supersedes the earlier readiness decision: automatic cleanup remains unresolved, and the current CIA should not be repeated. Earlier emulator reload crashes remain unexplained.

Evidence basis: local `porting/analysis/native-game-close-v0.1.3/report.ru.md`, its saved release gate, and the later hardware result. No runtime tests were run for this documentation publication.

## Shutdown work

The next step is a software fixture that reproduces slow but progressing late-loader I/O. Automatic cleanup needs bounded additional time when progress is proven, an inactivity limit, and an overall hard deadline. Input/close reasons and per-attempt snapshots also need clearer diagnostics.

Worker lifetime and GPU lifetime checks must remain intact, as must the frame FAIL result. A future hardware test should verify automatic exit and then HOME → X before proceeding toward a controlled gameplay scene. No release date or new hardware readiness is claimed here.

## Memory and earlier milestones

The native checkpoint uses a 124 MiB application profile: 20 MiB normal heap and 100 MiB linear heap, with a 92 MiB donor arena inside the linear allocation. The early software checkpoint recorded 120.746 MiB process commit; later hardware loading reached about 18.33 MiB normal allocator footprint. Neither measurement guarantees that later gameplay scenes will fit.

Earlier DS34 fixture tests validated the RGBA8-to-RGB8 path, GPU completion, pixel checks, and return to HOME. Separate startup tests reached main/READY/START/HOME in Legacy64 and New 3DS Prod124 profiles. Those are narrower milestones than a full original-game lifecycle pass.

The historical CPU baseline passed 552 ARM tests across 26 suites. That number belongs to its recorded build and is not a claim that the entire suite was rerun after every GPU or shutdown change. The menu screenshot comes from a separate, older emulator experiment with a 178 MiB profile and elevated CPU setting.

Already published technical context is preserved in the [Prod124 memory report](https://github.com/IvaYar/dead-space-3ds-port/blob/8b1839c207ca51e2afbd73c93639b97ab8bf08b5/porting/analysis/native-game-prod124-v0.1.0/report.ru.md), [Prod124 startup hardware report](https://github.com/IvaYar/dead-space-3ds-port/blob/8b1839c207ca51e2afbd73c93639b97ab8bf08b5/porting/analysis/native-startup-prod124-v0.1.0/hardware-report.ru.md), and [target-init hardware report](https://github.com/IvaYar/dead-space-3ds-port/blob/8b1839c207ca51e2afbd73c93639b97ab8bf08b5/porting/analysis/native-game-target-init-v0.1.1/hardware-report.ru.md). These pinned reports retain their original historical limits.

## Resource-store pilot

One isolated normal native CXI cycle passed in Azahar with shared read-only assets and separate writable run state. Only `assets` and `apk-assets` were shared through NTFS junctions; the donor library, receipts, font subset, saves, and other writable files remained independent copies. No hard links were used.

The private content-addressed dataset was checked against a complete inventory and protected by NTFS ACLs. The original runner's frame, CRC, worker-join, GPU, and I/O checks were preserved; the adapter changed preparation and import-root handling only. The original resource sets and saved evidence were retained.

This pilot reduced per-run initial copying from 556.340 MiB to 4.336 MiB, avoiding duplication of 552.004 MiB of assets for each new compatible run. Initial store creation added a copy; no old datasets were deleted and no disk space was claimed as already recovered. Mutating runners were not switched globally to shared assets.

This is a storage/preparation result. It does not fix hardware rendering or shutdown, prove save/restore compatibility, or authorize another hardware run. The full dataset manifest and private runtime state are not published.

Evidence basis: local `porting/analysis/shared-resource-store-pilot/report.ru.md`, its numerical results and storage metrics, and `porting/README-shared-resources.ru.md`.
