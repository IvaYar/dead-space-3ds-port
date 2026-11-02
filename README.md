# Dead Space Mobile for New Nintendo 3DS

A homebrew port of the original Android game, running its native engine on New Nintendo 3DS hardware.

The original engine now gets through the opening prologue and into **Chapter I — Honorable Intentions** in Azahar, with the character on screen and the game's own movement tutorial. On real hardware, the intro, difficulty selection, and confirmation are working.

<p align="center">
  <a href="docs/images/azahar-chapter-one.png"><img src="docs/images/azahar-chapter-one-top.png" width="400" height="240" alt="Original Chapter I corridor and MOVEMENT CONTROLS tutorial rendered by the port in Azahar at callback 5106"></a>
</p>

*Chapter I in Azahar, through the port's Citro3D/PICA200 backend. This is an emulator capture, not a console photograph. The original tutorial is visible; movement and camera control have not been confirmed. [Full capture](docs/images/azahar-chapter-one.png).*

**Work in progress.** There is no playable release yet. Scene rendering is still very slow, gameplay controls are not connected, and there is no audible sound output.

<details>
<summary>Earlier photographs from real New Nintendo 3DS hardware</summary>

<p align="center">
  <img src="docs/images/hardware-menu.jpg" width="46%" alt="Real New Nintendo 3DS showing the original difficulty menu in the 0.1.5 hardware test">
  <img src="docs/images/hardware-intro.jpg" width="46%" alt="Real New Nintendo 3DS showing the original headphone intro in the earlier 0.1.3 hardware test">
</p>

*The difficulty menu in 0.1.5 and the intro in 0.1.3. The older intro photo includes that build's cleanup failure message; later tests improved exit handling. Menu controls were subsequently verified in 0.1.7. [Image notes](docs/images/README.md).*

</details>

## Where it is now

On a real New 3DS, **0.1.7 verified D-pad navigation, Normal/Easy selection, and A confirmation through the original engine**, followed by the intended safe exit. Circle Pad and in-scene controls are separate work; a working menu does not prove movement or camera input.

The newer **Azahar-only** scene work goes beyond that hardware checkpoint. The game itself plays the prologue, enters the Chapter I corridor, and displays **MOVEMENT CONTROLS**. Scene state and character position were not set manually. These changes have not been tested on a console, and no new scene CIA is being offered.

Texture work has reduced repeated paging and conversion costs, using lossless Morton/LZ4 backing within the same memory budgets. It is a substantial improvement, but measured scene callbacks still take seconds in Azahar. The original audio mixer now runs into a timed PCM sink; audible NDSP output is still missing.

The successful long scene runs completed cooperative cleanup. Earlier hardware exit milestones remain version-specific: **0.1.4 verified HOME → X**, and 0.1.7 verified its limited post-confirmation exit. Other shutdown paths, older reference-frame failures, and remaining rendering differences are still tracked.

[Latest results and known limits](docs/verification.md) · [Development log](HANDOFF.md)

## Can I play it?

Not yet. The old diagnostic CIAs are not game releases; please do not install them expecting a working port.

The target is the **New Nintendo 3DS family** with an existing homebrew/CFW setup. Separate New 3DS XL and New 2DS XL validation is still pending. Original 3DS, 3DS XL, and 2DS are outside the current memory profile.

## Under the hood

The port loads the original ARM32 game library and runs its native code on the 3DS CPU. A compatibility layer supplies Android/Bionic and JNI services, file access, threading, memory allocation, and input bridges. It does not boot Android.

Graphics calls are translated from OpenGL ES 1.x to **Citro3D/PICA200**, with a separate CPU renderer for debugging. The current scene experiment retains the **124 MiB application profile**, with very little memory to spare. Reaching the corridor does not establish a sustained gameplay memory budget.

The working donor is the English Android SD edition **1.1.33**. The original engine source is unavailable, and the game library and assets are not included here.

## What's next

- Connect the game's original touch/analog input contract and verify movement, camera, and actions in the scene.
- Add audible sound output beyond the working original mixer and timed PCM sink.
- Reduce the remaining texture reload cost and measure sustained scene performance and memory use before another hardware step.

There is no release date. Progress depends on what the next original engine path needs.

## For developers

Development uses Windows/PowerShell, Python, devkitARM, libctru, Citro3D, Unicorn, and Azahar. Reproducing an experiment needs privately supplied compatible game files and the appropriate local setup.

Start with [Development Notes](docs/development.md), then the [3DS source](porting/3ds/source), [tests](porting/tests), and [tools](porting/tools). Detailed reports are mostly in Russian; this overview and the [public status summary](docs/verification.md) are in English.

Bug reports with a build version and clear reproduction steps are useful. Please do not attach APKs, game libraries, extracted assets, saves, or private memory dumps to public issues.

## Thanks

To the original Dead Space Mobile team, the devkitPro/libctru/Citro3D contributors, the Azahar and Unicorn developers, and everyone documenting the 3DS for homebrew. Port development and hardware testing by [IvaYar](https://github.com/IvaYar).

---

This is an unofficial fan project, not affiliated with or endorsed by EA or Nintendo. Dead Space, Nintendo names, and related content belong to their respective rights holders. You must supply your own lawfully obtained game files; this repository grants no rights to the original game. Third-party components retain their respective licenses.
