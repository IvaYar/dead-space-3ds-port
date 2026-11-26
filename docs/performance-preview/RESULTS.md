# Performance-preview results

I tested the milestone on my New Nintendo 3DS LL: HQ graphics, movement, C-Stick
camera and Render FPS HUD work. I observed roughly6-10 Render FPS and brief readings
near20, without a controlled four-mode benchmark. Stable15 FPS is not established.

Azahar CPU100/OpenGL, exact previous normal CIA versus two final ON runs: callback
median reduction5.92-5.93%, whole scripted scenario reduction1.17-1.85%, cinematic
transition reduction6.24-6.63%. These asynchronous single-host observations do not
establish physical speedup. HUD ON host time was0.52-1.22% above one OFF run; callback
median was slightly lower. There is insufficient replication for a causal overhead estimate.

Matrix logging consumed1.905ms per sampled late callback in instrumented normal,
1.624ms in diagnostic; fixed samples were0ms. These report scopes exclude log-lock
acquisition and measure emulated IO, not physical SD latency. Diagnostic64-interval
windows were6.098/s old and5.881/s clean; no convincing end-to-end diagnostic gain.
The earlier physical256-interval test completed in105.309093s at2.431 changed-image
observations/s but included synchronous logging. It is not a clean baseline for this HUD.

After logging repair, emulator profile: draw90.40% of callback; nested preparation
43.01%, emission42.23%, CPU gpu_end4.40%. This is not isolated GPU execution timing.
Normal final omits deep timers. CPU geometry remains the dominant measured scope.

Selected final payload checks:420 full draws plus150 format regressions,160 packing
cases,1000 HUD generations, failed/empty-present generation tests,26 GPU/shutdown,
72 SDK HID vectors,3 IO groups, lifetime and container/code/hash checks. Selected
ON/OFF camera/body runs passed original strict checks. Two other runs failed neutral
at step53 and recovered at54; repeats do not dismiss those failures. Cause unknown.

Application commit128110592B of130023424B; normal footprint19492864B;
linear104504320B of104857600B (345KiB margin). These are emulator scenario peaks,
not full-campaign hardware bounds. Budgets124/20/100/85.5MiB are unchanged.
Historical FRAME CRC ea733050 still FAIL; full-image fidelity remains unresolved.
