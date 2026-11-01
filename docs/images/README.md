# Public Documentation Images

These three existing Azahar captures were visually reviewed and selected for the project README. They contain game output only, without desktop UI, personal information, file paths, or private diagnostic overlays. No hardware photograph was available locally during this review; none of these images represents a photograph of a console.

| Public image | Original capture | What it demonstrates |
| :--- | :--- | :--- |
| [azahar-intro-cpu.png](azahar-intro-cpu.png) | [headphone-frame/first-game-frame.png](../../porting/analysis/headphone-frame/first-game-frame.png) | Original Isaac/headphone screen through the CPU renderer in Azahar. |
| [azahar-intro-pica200.png](azahar-intro-pica200.png) | [gpu-engine-first/first-game-frame.png](../../porting/analysis/gpu-engine-first/first-game-frame.png) | Original intro through Citro3D/PICA200 in Azahar, with remaining small-text differences. This is a separate capture, not a synchronized frame comparison. |
| [azahar-difficulty-menu.png](azahar-difficulty-menu.png) | [menu-frame/easy.png](../../porting/analysis/menu-frame/easy.png) | Easy selected through the touch bridge in the historical CPU-rendered menu experiment. |

Each image retains its original **400 × 240** resolution and decoded pixels. The documentation copies were re-encoded as optimized, lossless RGB PNGs with metadata removed. No cropping, retouching, generated content, upscaling, or color correction was applied. The original captures were not modified.

The menu experiment used an emulator-only 178 MiB profile and an elevated CPU setting. It does not demonstrate hardware speed or compatibility. Intro captures likewise show rendering milestones, not player-controlled gameplay or working sound.

Source context: [headphone screen](../../porting/HEADPHONE-SCREEN.ru.md), [menu verification](../../porting/MENU-BOOTSTRAP.ru.md), and [GPU development history](https://github.com/IvaYar/dead-space-3ds-port/blob/8b1839c207ca51e2afbd73c93639b97ab8bf08b5/HANDOFF.md). Current hardware claims are supported separately by the [Close 0.1.3 hardware report](../verification.md#hardware-results).

Game imagery remains the property of its respective rights holders and is included only to document this unofficial development project. These files are not a license to redistribute the game or its resources. The local publication guard flags binary images for separate review. These three files received visual, metadata, size, and decoded-pixel review; the guard was not weakened for them.
