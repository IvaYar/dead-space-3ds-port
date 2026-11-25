# Build / recovery

Python 3; devkitARM GCC with ARMv6K hard-float support; libctru and Citro3D development headers/libraries; makerom and bannertool for local packaging. Obtain SDK tools from their upstream projects, not game archives. Pinned SDK package versions and archive hashes are in dependencies.json; checked compiler/library hashes are also retained in the private recovery manifest. Different SDK versions may change output; no universal byte-identical build promise.

```
python -B playable_build.py --devkitpro /path/to/devkitpro --citro3d /path/to/citro3d --out /new/output
```

This public source-only build is actually compile-tested. It builds LZ4 from the included BSD-licensed source, then the complete port ELF. The output directory must be fresh. No LAB paths, old binary object, game data or private keys are needed for ELF compilation. Source hashes are verified against build-config.json.

For a local CIA, supply your own legally usable SMDH icon and BNR banner. With makerom:

```
makerom -f cia -o DeadSpace-3DS-Playable-v0.1.0.cia -rsf playable/native-game.rsf -target t -exefslogo -elf OUTPUT/native-game.elf -icon YOUR-ICON.smdh -banner YOUR-BANNER.bnr -ver 1
```

No public binary is supplied because the inherited banner/icon rights are unresolved. Generated CIA/ELF/SMDH/BNR are ignored by Git. Compatibility is tied to the specific private donor described in README. Original APK/assets and the licensed font are separate user inputs; there is no download or protection bypass. The existing porting tools/documentation describe earlier asset preparation, but are not advertised as a complete fresh-install pipeline for this snapshot. Never fabricate verification markers.

Recovery: clone the release branch, use the source build above and your private resources. The maintainer also retains a separate private recovery archive containing exact local build scripts/configuration and packaging inputs, plus a manifest pointing to existing sealed game/cache archives. That private recovery archive must never be committed.
