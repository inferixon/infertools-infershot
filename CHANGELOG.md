# Changelog

## 1.2.1

- Fixed text entry by routing keyboard and IME input through a native multiline editor.
- Kept the visible text editor transparent with a border-only frame and red caret.
- Made `Enter` insert a newline and `Ctrl+Enter` commit the text annotation.
- Added a final eraser button that clears all annotations while preserving the capture selection.

## 1.2.0

- Added visual QA annotations inside rectangle captures.
- Added a two-click straight red line for underlining or marking an area.
- Added a two-click red arrow whose second point defines the arrow tip.
- Made capture and annotation hotkeys configurable.
- Made `Escape` cancel an unfinished annotation before cancelling the capture.
- Added spaced rounded line, arrow, freehand, and text buttons with a subtle white hover glow.
- Reordered the toolbar to freehand, line, arrow, rectangle, and text.
- Added drag-to-draw red rectangle annotations.
- Replaced the opaque text field with a transparent, border-only canvas editor.
- Made the annotation font family and size configurable, defaulting to Palatino Linotype at 24 px.
- Fixed selection resize handles, including resizing after annotations are added.

## 1.1.0

- Added two capture modes: full monitor and selectable rectangle.
- Added moving and resizing for the rectangle selection.

## 1.0.0

- Added basic numbered screenshot capture and file saving.
- Added optional clipboard copy.
