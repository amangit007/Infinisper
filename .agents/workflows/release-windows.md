---
name: Release a Windows build
description: Build, sign, verify and publish a Windows release.
---

# Release a Windows build

Read [`AGENTS.md`](../../AGENTS.md) first. The whole point of this workflow is that `python -m` passing
tells you almost nothing about whether a release works.

## What actually breaks in built binaries

Five things, and none are visible when running from source:

1. **Path resolution.** Bundled apps resolve relative to the executable, not the working directory.
   Models live in `%APPDATA%`, Silero VAD in the install directory. Resolve through `sys._MEIPASS` or
   the executable path, never `os.getcwd()`.
2. **Missing imports.** PyInstaller's static analysis misses dynamic imports. `sherpa-onnx`,
   `litellm` and `keyring` backends are the usual suspects; add explicit hidden-imports or hooks.
3. **Code signing.** Unsigned builds trip SmartScreen and Defender, and **PyInstaller output is flagged
   more aggressively than most** because malware authors lean on it
   ([R5](../../docs/RISKS.md#r5--antivirus-and-smartscreen--h)).
4. **LGPL compliance.** Qt must ship as separate, replaceable DLLs with notices present
   ([R29](../../docs/RISKS.md#r29--lgpl-compliance-is-a-packaging-requirement--m)).
5. **Autostart.** The `HKCU\...\Run` entry and its `--hidden` flag only exist in an installed app.

## Steps

1. **Version bump** and changelog entry.

2. **Full test suite** plus the complete [manual smoke
   checklist](../../docs/PLAN.md#manual-smoke-checklist). All of it — the checklist exists because
   these paths cannot be automated, so skipping it means shipping them untested.

3. **Build with `--onedir`, never `--onefile`.** Two independent reasons: runtime self-extraction is
   the single biggest antivirus heuristic trigger, and `--onefile` breaks the dynamic linking LGPL
   requires. Check the output size — a sudden jump means model weights or PyTorch leaked in.

4. **Sign** the executable and the installer. Verify with `signtool verify /pa /v`.

5. **Verify on a fresh Windows 11 VM** — not the development machine, which has too much installed to
   be a valid test:

   - [ ] SmartScreen does not block the installer
   - [ ] Defender does not flag it
   - [ ] First launch opens the **model chooser** — remember no speech model ships with the app
     ([ADR-009](../../docs/DECISIONS.md#adr-009)), so the first-run download is on the critical path to
     the app working at all
   - [ ] The download completes, verifies and activates
   - [ ] Dictation works, then works again with the network disconnected
   - [ ] Start-with-Windows registers, and launches hidden after reboot
   - [ ] Uninstall removes the autostart entry, leaves no orphaned processes, and asks whether to
     delete downloaded models rather than orphaning ~1 GB

6. **Verify LGPL compliance in the shipped artefact:**

   - [ ] Qt DLLs present as separate files, not statically linked
   - [ ] About screen carries the LGPL-3.0 text, Qt attribution and a link to the Qt source
   - [ ] About screen carries the OpenMDW-1.1 model attribution

7. **Verify on an international keyboard layout**, or add one. Type `@ # { }` using AltGr and confirm
   no dictation is triggered ([R1](../../docs/RISKS.md#r1--altgr-is-delivered-as-ctrlalt--h)).

8. **Publish**: tag, release notes with the changelog, upload the signed installer.

## If antivirus flags the build

Do not obfuscate, do not pack, do not attempt to evade detection — that converts a false positive into
a justified one, and it is the wrong thing to do regardless of the outcome.

Instead: submit a false-positive report to the vendor, make sure the release is signed with a
certificate that has accrued reputation, and document the workaround in the release notes. If flagging
is persistent, revisit [OPEN-7](../../docs/DECISIONS.md#open-7) — Nuitka's compiled output may avoid
PyInstaller-specific detections entirely.

## Cadence note

Start the code-signing certificate process **well before** the first release, and earlier than an
Electron project would need to. OV and EV certificates take time to issue, SmartScreen reputation
accrues only after real installs, and PyInstaller starts you from a worse position. This is a timeline
item, not a build step.
