"""打出一个自带 Python 的安装包。别人安装后不需要再装 Python。"""

import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
RUNTIME = BUILD / "runtime"
PORTABLE = BUILD / "portable"
REDIST = BUILD / "redist"
EMBED_URLS = [
    "https://mirrors.huaweicloud.com/python/3.12.13/python-3.12.13-embed-amd64.zip",
    "https://www.python.org/ftp/python/3.12.13/python-3.12.13-embed-amd64.zip",
    "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip",
]
GET_PIP = "https://bootstrap.pypa.io/get-pip.py"
WEBVIEW2 = "https://go.microsoft.com/fwlink/p/?LinkId=2124701"
PIP_INDEX = "https://pypi.tuna.tsinghua.edu.cn/simple"
PACKAGES = [
    "fastapi==0.141.1",
    "uvicorn==0.52.4",
    "pycryptodome==3.23.0",
    "requests==2.34.2",
    "pywebview==6.2.1",
    "pythonnet==3.2.1",
]


def download(url, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        print("keep", dest.name, dest.stat().st_size)
        return
    print("get", url)
    session = requests.Session()
    session.trust_env = False
    session.proxies = {"http": None, "https": None}
    try:
        response = session.get(url, timeout=120, stream=True)
        response.raise_for_status()
    except requests.RequestException:
        response = requests.get(url, timeout=120, stream=True)
        response.raise_for_status()
    with dest.open("wb") as handle:
        for chunk in response.iter_content(1024 * 256):
            if chunk:
                handle.write(chunk)


def prepare_runtime():
    if not (RUNTIME / "python.exe").exists():
        _install_embed()
    site = RUNTIME / "Lib" / "site-packages"
    if not (site / "fastapi").exists():
        run(
            [
                str(RUNTIME / "python.exe"),
                "-m",
                "pip",
                "install",
                "--no-warn-script-location",
                "-i",
                PIP_INDEX,
                "setuptools",
                "wheel",
            ]
        )
    need_pip = not (site / "fastapi").exists()
    if need_pip:
        run(
            [
                str(RUNTIME / "python.exe"),
                "-m",
                "pip",
                "install",
                "--no-warn-script-location",
                "--no-build-isolation",
                "-i",
                PIP_INDEX,
                *PACKAGES,
            ]
        )
    else:
        print("runtime packages ok")


def _install_embed():
    if RUNTIME.exists():
        shutil.rmtree(RUNTIME)
    RUNTIME.mkdir(parents=True)
    archive = BUILD / "python-embed.zip"
    last_error = None
    for url in EMBED_URLS:
        try:
            download(url, archive)
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(RUNTIME)
            last_error = None
            break
        except Exception as exc:
            last_error = exc
            if archive.exists():
                archive.unlink()
    if last_error or not (RUNTIME / "python.exe").exists():
        raise SystemExit(f"下载 Python 失败：{last_error}")
    pth = next(RUNTIME.glob("python*._pth"))
    pth.write_text(
        "python312.zip\n.\n..\nLib\\site-packages\nimport site\n",
        encoding="utf-8",
    )
    for name in ("vcruntime140.dll", "vcruntime140_1.dll"):
        source = Path(os.environ["SystemRoot"]) / "System32" / name
        if source.exists():
            shutil.copy2(source, RUNTIME / name)
    get_pip = BUILD / "get-pip.py"
    download(GET_PIP, get_pip)
    run([str(RUNTIME / "python.exe"), str(get_pip), "-i", PIP_INDEX])


def run(args):
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    print(" ".join(args[:4]))
    subprocess.check_call(args, cwd=str(RUNTIME), env=env)


def assemble():
    PORTABLE.mkdir(parents=True, exist_ok=True)
    shutil.copytree(RUNTIME, PORTABLE / "runtime", dirs_exist_ok=True)
    for name in ("answer.py", "usage_query.py", "desktop.py", "LICENSE", "README.md", "使用说明.md", "app.ico"):
        shutil.copy2(ROOT / name, PORTABLE / name)
    server = PORTABLE / "server"
    server.mkdir(exist_ok=True)
    for path in (ROOT / "server").glob("*.py"):
        shutil.copy2(path, server / path.name)
    exe = ROOT / "src-tauri" / "target" / "release" / "zhihuishu-answer.exe"
    if not exe.exists():
        raise SystemExit("还没有正式版窗口程序，请先 cargo build --release")
    shutil.copy2(exe, PORTABLE / "智慧树答题.exe")


def webview2():
    REDIST.mkdir(parents=True, exist_ok=True)
    dest = REDIST / "MicrosoftEdgeWebview2Setup.exe"
    download(WEBVIEW2, dest)
    if dest.stat().st_size < 100_000:
        raise SystemExit("WebView2 安装器下载不完整")


def compile_installer():
    iscc = Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe")
    if not iscc.exists():
        raise SystemExit("没有找到 Inno Setup")
    subprocess.check_call([str(iscc), str(ROOT / "installer.iss")], cwd=str(ROOT))


def main():
    prepare_runtime()
    assemble()
    webview2()
    compile_installer()
    setup = ROOT / "installer" / "智慧树答题-Setup.exe"
    print("setup", setup, setup.stat().st_size)


if __name__ == "__main__":
    main()
