# Dead Space Mobile for New Nintendo 3DS

A homebrew port of the original Android game, running its native engine on New Nintendo 3DS hardware.

The intro runs, and the original difficulty menu now appears on a real console. The goal is to get the game playable on the handheld, keeping its original engine.

<p align="center">
  <img src="docs/images/hardware-menu.jpg" width="46%" alt="Real New Nintendo 3DS showing the original difficulty menu in the 0.1.5 hardware test">
  <img src="docs/images/hardware-intro.jpg" width="46%" alt="Real New Nintendo 3DS showing the original headphone intro in the earlier 0.1.3 hardware test">
</p>

*Photographed on real hardware: the difficulty menu in 0.1.5 and the intro in 0.1.3. The older intro photo includes that build's cleanup failure message; later tests improved exit handling. [Image notes](docs/images/README.md).*

**Work in progress.** There is no playable release yet: hardware menu input needs fixing, loading is very slow, and a controllable gameplay scene and working sound are still missing.

## Where it is now

The original engine boots, plays the EA and Isaac/headphone animations, and reaches **Select Difficulty** on a New 3DS. In Azahar, the menu experiment can switch between Normal and Easy and send the original confirmation input.

On hardware, the port's menu-readiness check currently blocks navigation. The menu is real, but physical controls have not passed that test. Loading it also takes several minutes.

Exiting has improved since the intro photograph was taken. **0.1.4 passed automatic cleanup and HOME → X on hardware.** The 0.1.5 menu test also exited automatically at its test limit; HOME → X has not been reverified for that version. Other shutdown paths and frame-reference differences remain under investigation.

[Latest results and known limits](docs/verification.md) · [Development log](HANDOFF.md)

## Can I play it?

Not yet. The old diagnostic CIAs are not game releases; please do not install them expecting a working port.

The target is the **New Nintendo 3DS family** with an existing homebrew/CFW setup. Separate New 3DS XL and New 2DS XL validation is still pending. Original 3DS, 3DS XL, and 2DS are outside the current memory profile.

## Under the hood

The port loads the original ARM32 game library and runs its native code on the 3DS CPU. A compatibility layer supplies Android/Bionic and JNI services, file access, threading, memory allocation, and input bridges. It does not boot Android.

Graphics calls are translated from OpenGL ES 1.x to **Citro3D/PICA200**, with a separate CPU renderer for debugging. The native menu fits a **124 MiB application profile**, with very little memory to spare. Fitting a gameplay scene is a separate problem.

The working donor is the English Android SD edition **1.1.33**. The original engine source is unavailable, and the game library and assets are not included here.

## What's next

- Fix hardware menu navigation without depending on an exact emulator framebuffer match, and find where the long loading delay is spent.
- Get through the first scene's audio initialization and missing graphics states, then bring up movement, camera, and actions.
- Measure and improve scene memory use, loading, and performance on hardware while keeping the exit checks intact.

There is no release date. Progress depends on what the next original engine path needs.

## For developers

Development uses Windows/PowerShell, Python, devkitARM, libctru, Citro3D, Unicorn, and Azahar. Reproducing an experiment needs privately supplied compatible game files and the appropriate local setup.

Start with [Development Notes](docs/development.md), then the [3DS source](porting/3ds/source), [tests](porting/tests), and [tools](porting/tools). Detailed reports are mostly in Russian; this overview and the [public status summary](docs/verification.md) are in English.

Bug reports with a build version and clear reproduction steps are useful. Please do not attach APKs, game libraries, extracted assets, saves, or private memory dumps to public issues.

## Thanks

To the original Dead Space Mobile team, the devkitPro/libctru/Citro3D contributors, the Azahar and Unicorn developers, and everyone documenting the 3DS for homebrew. Port development and hardware testing by [IvaYar](https://github.com/IvaYar).

---

This is an unofficial fan project, not affiliated with or endorsed by EA or Nintendo. Dead Space, Nintendo names, and related content belong to their respective rights holders. You must supply your own lawfully obtained game files; this repository grants no rights to the original game. Third-party components retain their respective licenses.
