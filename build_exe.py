"""Build a single-file Windows exe with PyInstaller.

    pip install pyinstaller
    python build_exe.py

Output lands in dist/. Assets/, Templates/ and Recordings/ are deliberately
NOT bundled -- they are user data and must live beside the exe so they
survive a rebuild and stay editable (a onefile build's temp extraction dir
is recreated fresh every launch).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NAME = "Macro Studio"


def _version_file() -> str:
    """Generate a VS_VERSION_INFO resource. Unsigned exes with no version
    metadata trip antivirus heuristics far more often."""
    try:
        with open(os.path.join(HERE, "VERSION"), encoding="utf-8") as fh:
            version = fh.read().strip()
    except OSError:
        version = "0.1.0"
    parts = [int(p) for p in (version.split(".") + ["0", "0", "0"])[:4] if p.isdigit()]
    while len(parts) < 4:
        parts.append(0)
    tup = tuple(parts[:4])

    build_dir = os.path.join(HERE, "build")
    os.makedirs(build_dir, exist_ok=True)
    path = os.path.join(build_dir, "version_info.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(
            "VSVersionInfo(\n"
            "  ffi=FixedFileInfo(filevers=%s, prodvers=%s, mask=0x3f, flags=0x0,\n"
            "                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),\n"
            "  kids=[StringFileInfo([StringTable('040904B0', [\n"
            "      StringStruct('FileDescription', 'Macro Studio'),\n"
            "      StringStruct('FileVersion', '%s'),\n"
            "      StringStruct('ProductName', 'Macro Studio'),\n"
            "      StringStruct('ProductVersion', '%s')])]),\n"
            "    VarFileInfo([VarStruct('Translation', [1033, 1200])])]\n"
            ")\n" % (tup, tup, version, version))
    return path


def main() -> int:
    sep = os.pathsep  # ';' on Windows, ':' elsewhere -- never hardcode
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--windowed", "--noconfirm",
        "--noupx",                       # UPX trips AV heuristics
        "--name", NAME,
        "--distpath", os.path.join(HERE, "dist"),
        "--workpath", os.path.join(HERE, "build"),
        "--specpath", os.path.join(HERE, "build"),
        "--add-data", "%s%sui" % (os.path.join(HERE, "ui"), sep),
        "--add-data", "%s%s." % (os.path.join(HERE, "VERSION"), sep),
        # pywebview picks its backend at runtime, so PyInstaller's static
        # analysis never sees these imports.
        "--hidden-import", "webview.platforms.winforms",
        "--hidden-import", "webview.platforms.edgechromium",
        # winsdk is a lazy WinRT namespace package: without collect-submodules
        # Windows OCR silently degrades to Tesseract in the built exe.
        "--collect-submodules", "winsdk",
        "--hidden-import", "pynput.keyboard._win32",
        "--hidden-import", "pynput.mouse._win32",
    ]
    if sys.platform == "win32":
        cmd += ["--version-file", _version_file()]
    cmd.append(os.path.join(HERE, "main.py"))

    print(" ".join(cmd))
    result = subprocess.run(cmd, cwd=HERE)
    if result.returncode != 0:
        print("Build failed.")
        return 1
    print("\nBuilt: dist/%s.exe" % NAME)
    print("Copy Assets/, Templates/ and Recordings/ next to the exe if you "
          "already have any -- they are not bundled on purpose.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
