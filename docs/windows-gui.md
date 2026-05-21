# Windows GUI Executable

Stage 4 uses a local web GUI launcher. The executable starts the zygo-dataX FastAPI web service on `127.0.0.1`, opens the default browser, and provides buttons to reopen/copy the URL or stop the service.

This keeps the Windows GUI and the container/web service on the same analysis engine and same UI. Rebuilt Windows executables inherit the current CLI/Web behavior: DATX upload auto-fills suggested aperture/crop inputs, report maps use the Zygo/PDF-style rainbow color scale, the summary image has the three image panels across the top row, and Zemax export writes raw, tilt-removed, and irregularity maps without a UI map selector.

## Build On Windows

Requirements:

- Windows 10/11
- Python 3.10 or newer
- Internet access for first-time Python package installation

From the project root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\build_windows_launcher.ps1
```

Output:

```text
dist\zygo-dataX\zygo-dataX.exe
```

## Use

1. Double-click `zygo-dataX.exe`.
2. The launcher starts a local service, usually at:

   ```text
   http://127.0.0.1:8017
   ```

3. The browser opens automatically.
4. Upload a DATX file and run analysis.

## Notes

- If port `8017` is busy, the launcher tries ports `8020` through `8099`.
- Results are written to a local `runs` folder next to the working directory.
- This is a Windows executable build recipe. Cross-building a real Windows `.exe` from Linux is not reliable with PyInstaller; build the final `.exe` on Windows.

## Troubleshooting

### Unable to configure formatter 'default'

Older builds could fail at startup with:

```text
ValueError: Unable to configure formatter 'default'
AttributeError: 'NoneType' object has no attribute 'isatty'
```

This happens when PyInstaller runs the GUI without a console and Uvicorn's default logging formatter tries to inspect a missing stderr stream. Rebuild from current source; the launcher now starts Uvicorn with `log_config=None` and `access_log=False`.
