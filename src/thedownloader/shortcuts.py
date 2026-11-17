"""Start menu and desktop shortcuts, so the app opens like any other Windows app.

The shortcuts start the window without a terminal, show the mushroom icon, and carry
the same app ID as the running window (see window.APP_ID). That ID is what makes a
pinned taskbar shortcut and the open window share one button.

Windows offers no simple way to put an app ID on a shortcut from Python, so a short
piece of C# is compiled by PowerShell (built into Windows) to write the shortcut.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from . import APP_NAME
from .window import APP_ID, ICON

_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;

namespace TheDownloader {
  [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("000214F9-0000-0000-C000-000000000046")]
  interface IShellLinkW {
    void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder file, int size, IntPtr data, uint flags);
    void GetIDList(out IntPtr list);
    void SetIDList(IntPtr list);
    void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder name, int size);
    void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string name);
    void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder dir, int size);
    void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string dir);
    void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder args, int size);
    void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string args);
    void GetHotkey(out short key);
    void SetHotkey(short key);
    void GetShowCmd(out int show);
    void SetShowCmd(int show);
    void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path, int size, out int index);
    void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string path, int index);
    void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string path, uint reserved);
    void Resolve(IntPtr window, uint flags);
    void SetPath([MarshalAs(UnmanagedType.LPWStr)] string file);
  }

  [ComImport, InterfaceType(ComInterfaceType.InterfaceIsIUnknown), Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]
  interface IPropertyStore {
    void GetCount(out uint count);
    void GetAt(uint index, out PropertyKey key);
    void GetValue(ref PropertyKey key, out PropVariant value);
    void SetValue(ref PropertyKey key, ref PropVariant value);
    void Commit();
  }

  [StructLayout(LayoutKind.Sequential, Pack = 4)]
  struct PropertyKey { public Guid Format; public uint Id; }

  [StructLayout(LayoutKind.Explicit)]
  struct PropVariant { [FieldOffset(0)] public ushort Type; [FieldOffset(8)] public IntPtr Text; }

  [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
  class ShellLink {}

  public static class Shortcut {
    public static void Create(string file, string target, string arguments, string folder, string icon, string appId, string description) {
      var link = (IShellLinkW)new ShellLink();
      link.SetPath(target);
      link.SetArguments(arguments);
      link.SetWorkingDirectory(folder);
      link.SetIconLocation(icon, 0);
      link.SetDescription(description);
      // System.AppUserModel.ID
      var key = new PropertyKey { Format = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), Id = 5 };
      var value = new PropVariant { Type = 31, Text = Marshal.StringToCoTaskMemUni(appId) };  // 31 = text
      try {
        var store = (IPropertyStore)link;
        store.SetValue(ref key, ref value);
        store.Commit();
      } finally {
        Marshal.FreeCoTaskMem(value.Text);
      }
      ((IPersistFile)link).Save(file, true);
    }
  }
}
'@
foreach ($folder in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) {
  $file = Join-Path $folder ($env:TD_NAME + '.lnk')
  if ($env:TD_REMOVE) {
    if (Test-Path -LiteralPath $file) { Remove-Item -LiteralPath $file; "removed $file" }
  } else {
    [TheDownloader.Shortcut]::Create($file, $env:TD_TARGET, $env:TD_ARGUMENTS, $env:TD_FOLDER, $env:TD_ICON, $env:TD_APPID, $env:TD_DESCRIPTION)
    "created $file"
  }
}
"""


def launcher() -> Path:
    """The project's own windowless Python, which starts the window without a terminal.

    Not the thedownloader-app.exe that uv makes: uv replaces that file on every update,
    and cannot while the app is open. pythonw.exe itself is never replaced by an update.
    """
    return Path(sys.executable).parent / "pythonw.exe"


def _run(remove: bool) -> list[str]:
    target = launcher()
    if not remove and not target.is_file():
        raise FileNotFoundError(f"{target} is missing. Run 'uv sync' in the project folder first.")
    environment = {
        **os.environ,
        "TD_NAME": APP_NAME,
        "TD_TARGET": str(target),
        "TD_ARGUMENTS": "-m thedownloader.window",
        "TD_FOLDER": str(Path(__file__).resolve().parents[2]),
        "TD_ICON": str(ICON),
        "TD_APPID": APP_ID,
        "TD_DESCRIPTION": "Download music and videos from YouTube and your Spotify playlists",
        "TD_REMOVE": "1" if remove else "",
    }
    # Values travel as environment variables, so no path or name is ever pasted into the script.
    # The script goes into a file of its own: PowerShell reads multi-line text from a pipe line by line.
    with tempfile.TemporaryDirectory() as folder:
        script = Path(folder) / "shortcuts.ps1"
        script.write_text(_SCRIPT, encoding="utf-8-sig")
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            env=environment, capture_output=True, text=True, timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    if result.returncode != 0:
        raise OSError(result.stderr.strip() or "PowerShell could not write the shortcut.")
    return [line for line in result.stdout.splitlines() if line.strip()]


def install() -> list[str]:
    return _run(remove=False)


def remove() -> list[str]:
    return _run(remove=True)
