# Infershot

Infershot is a lightweight Windows screenshot tool for fast capture and visual QA.
It runs in the background, saves numbered screenshots, copies them to the clipboard,
and adds straight red lines or arrows before saving a selected region.

## Features

- Rectangle capture across the Windows virtual desktop
- Full-monitor capture for the monitor under the cursor
- Movable and resizable selection rectangle
- Two-click red line and arrow annotations
- Automatic numbered filenames
- Optional clipboard copy
- Configurable capture, annotation, save, and cancel hotkeys

## Requirements

- Windows 10 or Windows 11
- Python 3.9 or newer
- [Pillow](https://pypi.org/project/pillow/)
- Tkinter, normally included with the standard Windows Python installer

The global PrintScreen hook and clipboard integration use Windows APIs, so the
application is not cross-platform.

## Installation

```powershell
git clone https://github.com/inferixon/infertools-infershot.git
cd infertools-infershot
python -m pip install -r requirements.txt
```

Review `config.json`, then launch:

```powershell
.\run-infershot.bat
```

Stop the background process with:

```powershell
.\stop-infershot.ps1
```

## Default hotkeys

| Action | Hotkey |
| --- | --- |
| Select a rectangle | `PrintScreen` |
| Capture the monitor under the cursor | `Ctrl+PrintScreen` |
| Start a red line | `Ctrl+LeftMouse` |
| Finish the active line | `LeftMouse` |
| Start a red arrow | `Ctrl+RightMouse` |
| Finish the active arrow | `RightMouse` |
| Save the selected capture | `Enter` |
| Cancel the capture | `Escape` |

For a rectangle capture, drag with the left mouse button. Before adding an
annotation, the selection can be moved from its interior or resized with its handles.
The second arrow click marks the arrow tip. Completed annotations are included in
both the saved image and the clipboard image.

## Configuration

`config.json` is loaded when Infershot starts. Restart the application after edits.

```json
{
  "save_path": "C:\\SCREENSHOTS",
  "format": "jpg",
  "quality": 95,
  "filename_mask": "ScreenShot-{nnn}",
  "copy_to_clipboard": true,
  "hotkeys": {
    "rectangle": "PrintScreen",
    "fullscreen": "Ctrl+PrintScreen",
    "line_start": "Ctrl+LeftMouse",
    "line_finish": "LeftMouse",
    "arrow_start": "Ctrl+RightMouse",
    "arrow_finish": "RightMouse",
    "save": "Enter",
    "cancel": "Escape"
  }
}
```

Supported selector combinations use `Ctrl`, `Shift`, or `Alt` with
`LeftMouse`, `RightMouse`, `Enter`, `Escape`, or a single keyboard character.
Capture shortcuts currently use PrintScreen with optional modifier keys.

If a config field is missing, the built-in default from `infershot.py` is used.

## License

Infershot is released under the [MIT License](LICENSE). You may use, modify,
distribute, sublicense, or sell copies of the software while preserving the
license and copyright notice.
