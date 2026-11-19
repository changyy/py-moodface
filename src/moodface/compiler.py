"""Run the third-party face compiler (compile.exe from Mi Create).

The compiler is closed source and is never bundled. `moodface compiler setup` downloads it
from the Mi Create repository after the user agrees. By default it runs inside a Docker
container (Wine on linux/amd64) on every platform, so it never touches the host system;
`--runner wine` or `--runner native` (Windows) are explicit opt-ins.
"""
from __future__ import annotations

import io
import os
import platform
import shutil
import subprocess
import urllib.request
import zipfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import List, Optional

MI_CREATE_REPO = "https://github.com/ooflet/Mi-Create"
MI_CREATE_ZIP = MI_CREATE_REPO + "/archive/refs/heads/main.zip"
DOCKER_IMAGE = os.environ.get("MOODFACE_WINE_IMAGE", "moodface-wine")
COMPILE_KEY = "1461256429"  # passed by Mi Create to compile.exe


def home() -> Path:
    return Path(os.environ.get("MOODFACE_HOME", Path.home() / ".cache" / "moodface"))


def find_compiler(explicit: Optional[str] = None) -> Optional[Path]:
    for cand in (explicit, os.environ.get("MOODFACE_COMPILER"), home() / "compiler" / "compile.exe"):
        if cand and Path(cand).is_file():
            return Path(cand).resolve()
    return None


def download_compiler(dest: Optional[Path] = None) -> Path:
    """Fetch src/compiler/* from the Mi Create repository zip into <home>/compiler."""
    dest = dest or home() / "compiler"
    with urllib.request.urlopen(MI_CREATE_ZIP, timeout=120) as r:
        data = r.read()
    dest.mkdir(parents=True, exist_ok=True)
    found = False
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            parts = info.filename.split("/")
            if len(parts) >= 4 and parts[1:3] == ["src", "compiler"] and parts[-1] and not info.is_dir():
                target = dest.joinpath(*parts[3:])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(info))
                found = found or parts[-1] == "compile.exe"
    if not found:
        raise RuntimeError("compile.exe was not found in the Mi Create archive")
    (dest / "SOURCE.txt").write_text(
        f"Downloaded from {MI_CREATE_REPO}\n"
        "compile.exe is third-party, closed-source software shipped with Mi Create. Do not redistribute.\n",
        encoding="utf-8")
    return dest / "compile.exe"


# ---------- runners ----------

def default_runner() -> str:
    """Docker on every platform: the third-party compiler stays isolated from the host.
    `wine` and `native` remain available as explicit opt-ins (--runner)."""
    return os.environ.get("MOODFACE_RUNNER", "docker")


def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def docker_image_exists(image: str = DOCKER_IMAGE) -> bool:
    return subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode == 0


def dockerfile_text() -> str:
    return resources.files("moodface").joinpath("resources/Dockerfile").read_text(encoding="utf-8")


def build_docker_image(image: str = DOCKER_IMAGE, dockerfile: Optional[str] = None) -> int:
    text = Path(dockerfile).read_text(encoding="utf-8") if dockerfile else dockerfile_text()
    return subprocess.run(["docker", "build", "--platform", "linux/amd64", "-t", image, "-"],
                          input=text.encode()).returncode


@dataclass
class CompileResult:
    ok: bool
    output: str
    face_file: Path
    command: List[str]


def compile_project(fprj: Path, compiler: Path, runner: Optional[str] = None,
                    image: str = DOCKER_IMAGE) -> CompileResult:
    fprj = Path(fprj).resolve()
    proj = fprj.parent
    name = fprj.stem
    face_file = proj / "output" / f"{name}.face"
    if face_file.exists():
        face_file.unlink()
    runner = runner or default_runner()

    if runner == "native":
        cmd = [str(compiler), "-b", str(fprj), str(proj / "output"), f"{name}.face", COMPILE_KEY]
    elif runner == "wine":
        win = lambda p: "Z:" + str(p).replace("/", "\\")  # noqa: E731
        cmd = ["wine", str(compiler), "-b", win(fprj), win(proj / "output"), f"{name}.face", COMPILE_KEY]
    elif runner == "docker":
        cmd = ["docker", "run", "--rm", "--platform", "linux/amd64",
               "-v", f"{proj}:/work", "-v", f"{compiler.parent}:/compiler", image,
               "wine", f"/compiler/{compiler.name}", "-b",
               f"Z:\\work\\{fprj.name}", "Z:\\work\\output", f"{name}.face", COMPILE_KEY]
    else:
        raise ValueError(f"unknown runner '{runner}' (native, wine, docker)")

    p = subprocess.run(cmd, capture_output=True)
    out = (p.stdout + p.stderr).decode("utf-8", "replace")
    has_error = any(line.strip().startswith("Error") for line in out.splitlines())
    return CompileResult(face_file.is_file() and not has_error, out, face_file, cmd)


def expected_preview_size(output: str):
    """Parse 'Preview has wrong size: AxB, expected: CxD' from the compiler output."""
    import re
    m = re.search(r"Preview has wrong size: \d+x\d+, expected: (\d+)x(\d+)", output)
    return (int(m.group(1)), int(m.group(2))) if m else None


ID_FIELD = slice(0x28, 0x68)                # face id field; title from 0x68


def stamp_id(face_file: Path, face_id: str) -> None:
    """Write the face id into the compiled .bin: a NUL-terminated ASCII field at 0x28..0x67
    (the title starts at 0x68). Mi Create stamps it after compiling; ids are 9-12 digits."""
    face_id = str(face_id)
    if not (9 <= len(face_id) <= 12 and face_id.isdigit() and face_id.isascii()):
        raise ValueError(f"face id must be 9-12 digits, got '{face_id}'")
    data = bytearray(Path(face_file).read_bytes())
    data[ID_FIELD] = bytes(ID_FIELD.stop - ID_FIELD.start)
    data[ID_FIELD.start:ID_FIELD.start + len(face_id)] = face_id.encode("ascii")
    Path(face_file).write_bytes(bytes(data))
