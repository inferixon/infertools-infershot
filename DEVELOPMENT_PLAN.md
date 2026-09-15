# Infershot Development Plan

## Goal

Ship a stable Windows application and installer without changing the current
annotation workflow or overwriting user configuration during upgrades.

## Baseline evidence

- Text size mismatch – text looks larger in the live selector than in the saved image.
- Keyboard layout – the active input language cannot be changed while editing text.
- Caps Lock – capitalization state is not respected reliably by the text editor.
- Runtime reliability – one background process disappeared after a successful save;
  the log contained no traceback, so the cause remains unproven.
- Distribution – no executable installer or published binary release exists yet.

## Implementation status

- Text pixel parity – implemented locally; automated metric check passes, installed
  runtime visual confirmation remains required.
- Keyboard input – native Caps Lock case changes verified; layout switching already
  works, while the Windows taskbar indicator remains stale over the borderless overlay.
- Input feedback – live in-editor `EN`, `NO`, `UA`, and Caps Lock status implemented;
  installed runtime visual confirmation remains required.

## Phase 1 – Text rendering parity

### Investigation

- Compare the Tk canvas font metrics with the Pillow font metrics used by
  `draw_annotations()`.
- Verify behavior at Windows scaling levels of 100%, 150%, and 200%.
- Confirm the exact Palatino font file and fallback behavior on a clean Windows system.
- Treat the current unit mismatch as a hypothesis: Tk receives a positive size in
  points while Pillow receives the same number as pixels.

### Implementation direction

- Define annotation font size once in pixels.
- Use an explicit pixel-sized Tk font for preview, caret, and text-box measurement.
- Use the same font file and pixel size for Pillow output.
- Keep multiline layout, `Enter` for newline, and `Ctrl+Enter` for commit.

### Acceptance

- Preview and saved-image glyph dimensions differ by no more than 5% at each tested
  scaling level.
- Line spacing and multiline wrapping match between preview and saved output.
- Missing configured fonts fall back visibly and log the selected fallback.

## Phase 2 – Native keyboard input

### Investigation

- Capture focused-widget identity, `event.keysym`, `event.char`, modifier state, and
  active Windows keyboard layout during a local diagnostic run.
- Verify whether the hidden 1x1 Tk `Text` widget remains the native input target.
- Check both Windows layout shortcuts used on the machine without intercepting them
  globally.

### Implementation direction

- Keep text entry in a native focused Tk text control so Windows produces characters.
- Do not implement a manual key-to-character map.
- Allow Windows keyboard-layout switching and Caps Lock to pass through unchanged.
- Keep selector hotkeys isolated from the focused editor except for `Escape`,
  `Enter`, and `Ctrl+Enter`.

### Acceptance

- Switch English ↔ Ukrainian while one text box remains open and enter both scripts.
- Caps Lock and Shift produce correct upper/lowercase characters in each layout.
- Backspace, arrows, Home, End, multiline Enter, Ctrl+Enter, and Escape remain correct.
- Saved text exactly matches the previewed Unicode string.

## Phase 3 – Runtime failure diagnostics

- Route uncaught Python and Tk callback exceptions into the application log.
- Record clean startup, selector open/close, save completion, shutdown reason, and PID.
- Remove a PID file only after verifying that its process no longer exists.
- Run repeated rectangle/fullscreen capture, annotation, clipboard, and save cycles.
- Do not claim the earlier crash is fixed until a reproducible cause is found or the
  pressure test passes without disappearance.

### Acceptance

- No orphan PID after normal shutdown or failed startup.
- Any unhandled exception produces a traceback in the local log.
- Background runtime remains alive after repeated saves and cancelled captures.

## Phase 4 – Installer-ready storage

- Application binaries – `%LOCALAPPDATA%\Programs\Infershot`.
- User state – `%LOCALAPPDATA%\Infershot` for config, PID, and logs.
- Screenshot default – a portable user-owned Pictures/Screenshots location.
- First run – create the default config only when no user config exists.
- Upgrade – preserve the user's config and merge missing schema defaults at runtime.
- Uninstall – remove binaries and startup shortcuts; retain user config unless the
  user explicitly chooses to remove it.

### Acceptance

- A standard user can install, run, update, and uninstall without administrator rights.
- Upgrade does not change save path, hotkeys, font, cross size, or clipboard preference.
- Runtime files never appear beside the installed executable or in the Git repository.

## Phase 5 – Windows executable and installer

- PyInstaller – build a windowed `onedir` bundle from a pinned build environment.
- Inno Setup – produce `Infershot-Setup-<version>.exe` with a stable `AppId`.
- Startup – offer an optional per-user “Start Infershot with Windows” task.
- Upgrade – stop the running Infershot process safely before replacing binaries.
- Shortcuts – add Start Menu launch and uninstall entries.
- Metadata – embed product name, version, publisher, icon, license, and repository URL.

### Required repository artifacts

```text
VERSION
packaging/infershot.spec
packaging/installer.iss
scripts/build-release.ps1
.github/workflows/release.yml
```

### Acceptance

- Clean Windows VM installs and launches without Python being installed.
- PrintScreen hook, fullscreen/rectangle capture, clipboard, every annotation tool,
  Unicode text, resize handles, and save behavior pass from the installed build.
- Reinstall/upgrade preserves configuration and leaves one running instance.
- Uninstall removes the application and startup entry without orphan processes.

## Phase 6 – Release automation

- Trigger the Windows build from an explicit semantic version tag.
- Run source checks and installer smoke tests before publication.
- Build the PyInstaller bundle and Inno Setup installer on Windows.
- Generate SHA-256 checksums and attach them with the installer to a GitHub Release.
- Keep build outputs out of Git history.
- Add code signing when a trusted signing route is available; document SmartScreen
  behavior honestly for unsigned preview releases.

### Release gate

- Local source checks – PASS.
- Installed-build smoke test – PASS.
- Upgrade and uninstall test – PASS.
- Public config safety review – PASS.
- Version, changelog, tag, binary metadata, and GitHub Release agree.
- Published installer checksum matches the locally verified release artifact.

## Execution order

1. Fix and verify text pixel parity.
2. Fix and verify native layout switching and Caps Lock.
3. Add crash diagnostics and run the stability pressure test.
4. Separate installed binaries from user state.
5. Build and test the local executable and installer.
6. Add release automation and publish only after the release gate passes.
