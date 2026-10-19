"""Build a self-contained Windows x64 application and per-user NSIS installer."""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def run(command, **options):
    print("+ " + subprocess.list2cmdline(list(map(str, command))), flush=True)
    return subprocess.run(list(map(str, command)), check=True, creationflags=0x08000000, **options)


def native_core(destination, compiler):
    compiler = compiler or shutil.which("gcc")
    if not compiler:
        for candidate in (r"C:\msys64\ucrt64\bin\gcc.exe", r"C:\msys64\mingw64\bin\gcc.exe"):
            if Path(candidate).is_file():
                compiler = candidate; break
    if not compiler:
        raise SystemExit("Install MinGW-w64 GCC for development, or pass --core with a built Windows x64 executable.")
    windres = Path(compiler).with_name("windres.exe")
    if not windres.is_file():
        windres = shutil.which("windres")
    if not windres:
        raise SystemExit("The MinGW-w64 windres resource compiler is required.")
    resource = destination.with_suffix(".res")
    run([windres, "-I" + str(HERE), HERE / "core.rc", "-O", "coff", "-o", resource])
    # GNU stdio supplies C17 formats; prevent MSVCRT built-in format assumptions.
    run([compiler, "-municode", "-std=c17", "-O2", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
         "-fno-builtin", "-D__USE_MINGW_ANSI_STDIO=1", "-D_WIN32_WINNT=0x0A00", "-static",
         "-I" + str(ROOT / "include"), *sorted((ROOT / "src").glob("*.c")), resource,
         "-lws2_32", "-lm", "-o", destination])
    return destination


def check_core(path):
    data = path.read_bytes()
    if data[:2] != b"MZ" or len(data) < 64:
        raise SystemExit("The core must be a Windows executable.")
    pe = struct.unpack_from("<I", data, 60)[0]
    if data[pe:pe+4] != b"PE\0\0" or struct.unpack_from("<H", data, pe+4)[0] != 0x8664:
        raise SystemExit("The core must target Windows x64.")


def icon(path):
    from PIL import Image, ImageDraw, ImageFont
    import matplotlib
    image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, 252, 252), radius=52, fill="#142630")
    draw.rounded_rectangle((22, 22, 234, 234), radius=40, fill="#087f8c")
    font = ImageFont.truetype(str(Path(matplotlib.get_data_path()) / "fonts/ttf/DejaVuSans-Bold.ttf"), 170)
    box = draw.textbbox((0, 0), "R", font=font)
    draw.text(((256-(box[2]-box[0]))/2-box[0], (256-(box[3]-box[1]))/2-box[1]-4),
              "R", fill="white", font=font)
    image.save(path, sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])


def notices(folder, extra):
    folder.mkdir(parents=True, exist_ok=True)
    lines = ["Third-party components in Rigol Transient Analyzer", ""]
    packages = ["pyinstaller", "matplotlib", "numpy", "pillow", "contourpy", "cycler",
                "fonttools", "kiwisolver", "packaging", "pyparsing", "python-dateutil", "six"]
    for name in packages:
        dist = importlib.metadata.distribution(name)
        lines.append(name + " " + dist.version)
        for file in dist.files or []:
            if not ("license" in str(file).lower() or file.name.upper().startswith(("COPYING", "NOTICE"))):
                continue
            source = Path(dist.locate_file(file))
            if not source.is_file():
                continue
            relative = Path(*[part for part in file.parts if part not in ("..", ".")])
            destination = folder / name / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        shutil.copy2(python_license, folder / "Python-LICENSE.txt")
    for extra_folder in [HERE / "licenses", *extra]:
        if extra_folder.is_dir():
            shutil.copytree(extra_folder, folder / extra_folder.name, dirs_exist_ok=True)
    lines += ["", "Python " + sys.version, "", "See the accompanying license texts for each component."]
    (folder / "NOTICE.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def nsis_escape(value):
    return str(value).replace("$", "$$").replace('"', '$\\"')


def installer_inputs(bundle, output):
    manifest = output / "uninstall-files.nsh"
    files = sorted(path for path in bundle.rglob("*") if path.is_file())
    dirs = sorted((path for path in bundle.rglob("*") if path.is_dir()), key=lambda p: len(p.parts), reverse=True)
    lines = ['Delete "$INSTDIR\\' + nsis_escape(path.relative_to(bundle)) + '"' for path in files]
    lines += ['RMDir "$INSTDIR\\' + nsis_escape(path.relative_to(bundle)) + '"' for path in dirs]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/windows")
    parser.add_argument("--core", type=Path)
    parser.add_argument("--compiler")
    parser.add_argument("--makensis", type=Path)
    parser.add_argument("--extra-licenses", type=Path, action="append", default=[])
    parser.add_argument("--skip-installer", action="store_true")
    args = parser.parse_args()
    if os.name != "nt" or struct.calcsize("P") != 8:
        parser.error("Run this builder using 64-bit Python on Windows.")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    core = args.core.resolve() if args.core else native_core(output / "carac_transientes.exe", args.compiler)
    check_core(core)
    app_icon = output / "app.ico"; icon(app_icon)
    licenses = output / "third-party-licenses"; notices(licenses, args.extra_licenses)
    version_info = output / "version-info.txt"
    version_tuple = tuple(map(int, VERSION.split("."))) + (0,)
    version_info.write_text(
        "VSVersionInfo(ffi=FixedFileInfo(filevers=" + repr(version_tuple) +
        ",prodvers=" + repr(version_tuple) + ",mask=0x3f,flags=0,OS=0x40004,fileType=1,subtype=0,date=(0,0)),"
        "kids=[StringFileInfo([StringTable('040904B0',[StringStruct('CompanyName','Icaro Ramos Rodrigues dos Santos'),"
        "StringStruct('FileDescription','Rigol Transient Analyzer'),StringStruct('ProductName','Rigol Transient Analyzer'),"
        "StringStruct('FileVersion','" + VERSION + "'),StringStruct('ProductVersion','" + VERSION +
        "')])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])", encoding="utf-8")
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
        "--name", "RigolTransientAnalyzer", "--distpath", output / "app", "--workpath", output / "pyinstaller",
        "--specpath", output, "--paths", ROOT, "--manifest", HERE / "app.manifest",
        "--icon", app_icon, "--version-file", version_info,
        "--add-binary", str(core) + os.pathsep + "core",
        "--add-data", str(ROOT / "interface/static") + os.pathsep + "interface/static",
        "--add-data", str(ROOT / "include/rigol_models.def") + os.pathsep + "include",
        "--add-data", str(ROOT / "VERSION") + os.pathsep + ".",
        "--add-data", str(ROOT / "README.md") + os.pathsep + ".",
        "--add-data", str(licenses) + os.pathsep + "third-party-licenses",
        "--hidden-import", "matplotlib.backends.backend_agg",
        "--copy-metadata", "matplotlib", "--copy-metadata", "numpy"]
    for name in ("tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "IPython", "pytest"):
        command += ["--exclude-module", name]
    run([*command, HERE / "launcher.py"])
    bundle = output / "app/RigolTransientAnalyzer"
    shutil.copy2(ROOT / "README.md", bundle / "README.md")
    uninstall = installer_inputs(bundle, output)
    executable = bundle / "RigolTransientAnalyzer.exe"
    run([executable, "--self-test", output / "self-test.json"], timeout=120)
    if not args.skip_installer:
        compiler = args.makensis or shutil.which("makensis")
        if not compiler:
            compiler = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "NSIS/makensis.exe"
        if not Path(compiler).is_file():
            raise SystemExit("NSIS compiler not found. The verified app bundle is ready; install NSIS or use --skip-installer.")
        run([compiler, "/V2", "/DAPP_DIR=" + str(bundle), "/DOUTPUT_DIR=" + str(output),
            "/DVERSION=" + VERSION, "/DICON=" + str(app_icon), "/DUNINSTALL_LIST=" + str(uninstall),
            HERE / "installer.nsi"])
        setup = output / ("RigolTransientAnalyzer-" + VERSION + "-windows-x64-setup.exe")
        (output / "SHA256SUMS.txt").write_text(hashlib.sha256(setup.read_bytes()).hexdigest() + "  " + setup.name + "\n", encoding="utf-8")
    print("Windows bundle ready: " + str(bundle), flush=True)


if __name__ == "__main__":
    main()
