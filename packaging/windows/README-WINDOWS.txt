zygo-dataX for Windows
======================

zygo-dataX analyzes Zygo DATX files, generates wavefront/fringe reports,
and exports Zemax Grid Sag / Extended Polynomial files.

Portable Usage
--------------

1. Unzip the package to a folder with write permission, for example:

   C:\Tools\zygo-dataX

2. Double-click:

   zygo-dataX.exe

3. The launcher starts a local web service and opens your browser.

4. Upload a DATX file and run analysis.

Default local URL:

   http://127.0.0.1:8017

If port 8017 is busy, the launcher tries ports 8020-8099.

Data and Results
----------------

Runs are saved to a local runs folder. Each run includes:

- input DATX
- structure summary JSON
- wavefront/fringe/Zernike outputs
- Zemax Grid Sag DAT
- Extended Polynomial TXT/CSV
- full ZIP bundle

Uninstall Portable Version
--------------------------

Close zygo-dataX, then delete the folder.

Troubleshooting
---------------

- If Windows Defender asks for confirmation, allow the app only if you trust
  the build source.
- If the browser does not open automatically, copy the URL from the launcher.
- If the app cannot start, check whether another service is using the selected
  port.
