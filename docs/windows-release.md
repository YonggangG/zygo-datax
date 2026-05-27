# Windows Release Packaging

This document describes the two Windows release formats for `zygo-dataX`.

## Release Formats

### Portable ZIP

Best for engineering/internal use.

- No installer.
- Unzip anywhere.
- Run `zygo-dataX.exe`.
- Delete the folder to uninstall.

Output:

```text
dist\release\zygo-dataX-0.1.1-portable.zip
```

### Installer

Best for normal Windows users.

- Uses Inno Setup.
- Installs to Program Files by default.
- Creates Start Menu shortcut.
- Optional desktop shortcut.
- Includes uninstaller.

Output:

```text
dist\installer\zygo-dataX-Setup-0.1.1.exe
```

## Build Order On Windows

From the project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\build_windows_launcher.ps1
powershell -ExecutionPolicy Bypass -File scripts\release\build_windows_portable.ps1
```

Optional installer build:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\release\build_windows_installer.ps1
```

The installer build requires Inno Setup 6.

## Release Checklist

1. Build `dist\zygo-dataX\zygo-dataX.exe`.
2. Run the executable.
3. Confirm browser opens.
4. Upload Side 1 DATX and run analysis.
5. Upload Side 4 DATX and run analysis.
6. Confirm maps/fringe image render.
7. Confirm Grid Sag DAT download exists.
8. Confirm full ZIP download contains analysis and Zemax files.
9. Build portable ZIP.
10. Extract portable ZIP to a clean folder and run again.
11. Build installer if needed.
12. Install on a clean Windows machine or VM.
13. Confirm Start Menu shortcut launches the app.
14. Uninstall and confirm app folder is removed.

## Notes

Build the Windows `.exe` on Windows. PyInstaller cross-building from Linux to Windows is not reliable.
