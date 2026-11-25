# Validation scope

Phase9 v0.1.0 is based on the preceding Phase8 build the user reports working well on a physical New 3DS LL. **The new CIA has no physical test yet.** Stable 15 FPS and hardware input latency are unknown.

The final packaged CIA, not only its ELF, was exercised through a private Azahar/libretro scenario. It reached genuine readiness without the manual HID/X preflight, delivered original Xperia camera events, passed directional camera and angular-stop checks, kept the body stationary during camera-only input, moved the original physics body during two simultaneous stick groups, returned the controller to neutral, and exited cooperatively through START. Separate developer-mode ELF regression retained the original opposite-direction body/stop oracle.

The CIA container was checked with CTRTool; decompressed ExeFS code equals the ELF load segments, hashes/permissions/TitleID match, and there is no RomFS. Expected homebrew signature warnings are recorded privately. GPU failed submits and GL errors were zero; worker/file ownership, drain-before-free and cleanup checks passed. These checks do not prove every possible gameplay path.

Linked ARM checks cover buffered-read guards, fullscreen fixes, camera/IRRST delivery, cache invalidation/differential behavior and prepared cache rejection. Normal-mode watchdog policy was tested on ARM: no manual-marker timeout at 120 seconds, with startup and finite-session limits retained. A fresh public-source ELF build succeeded with the pinned local SDK. Debug paths and rebuilt dependencies can change binary hashes; byte-identical public rebuilds are not promised.

The inherited full-image CRC target remains FAIL and full image fidelity is unresolved. Private screenshots, game data, raw SD logs and crash dumps are deliberately excluded. The public history/diff audit checked donor/APK/key/token candidates; it is not a rights clearance of every inherited historical artifact. No public CIA is attached while the inherited banner/icon distribution rights are unresolved.
