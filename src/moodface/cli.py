"""moodface command line."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import List, Optional

from . import compiler as C
from ._version import __version__
from .devices import DEVICES, get_device
from .fprj import write_project
from .render import write_previews
from .rules import RULES
from .sources import SOURCES
from .spec import SpecError, load_face, validate


def _device_args(p: argparse.ArgumentParser) -> None:
    g = p.add_argument_group("device (overrides face.yaml)")
    g.add_argument("--device", help=f"device profile: {', '.join(DEVICES)}")
    g.add_argument("--width", type=int)
    g.add_argument("--height", type=int)
    g.add_argument("--radius", type=int)
    g.add_argument("--device-type", help="DeviceType id written into the project")
    g.add_argument("--shape", choices=["band", "square", "round"], help="layout variant to use")
    f = p.add_argument_group("fonts (override face.yaml; also MOODFACE_FONT / MOODFACE_TEXT_FONT)")
    f.add_argument("--font", help="font file for digits and Latin text (default: Nunito, downloaded once)")
    f.add_argument("--text-font", help="font file for Chinese text (default: Noto Sans TC, downloaded once)")


def _load(args):
    dev = None
    if any(getattr(args, k, None) is not None for k in ("device", "width", "height", "radius", "device_type", "shape")):
        import yaml
        spec = Path(args.face) / "face.yaml" if Path(args.face).is_dir() else Path(args.face)
        fallback = None
        if spec.is_file():
            fallback = (yaml.safe_load(spec.read_text(encoding="utf-8")) or {}).get("device")
        dev = get_device(args.device or fallback, width=args.width, height=args.height,
                         radius=args.radius, device_type=args.device_type, shape=args.shape)
    return load_face(args.face, device=dev, style_override={"font": args.font, "text_font": args.text_font},
                     face_id=getattr(args, "id", None), id_length=getattr(args, "id_length", None))


def _report(face) -> bool:
    errors, warnings = validate(face)
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    return not errors


def cmd_devices(args) -> int:
    print(f"{'key':<18} {'name':<32} {'shape':<7} {'type':>5} {'size':>9}  compile")
    for d in DEVICES.values():
        if args.shape and d.shape != args.shape:
            continue
        status = {"ok": "ok", "fails": "FAILS", "untested": "untested"}[d.compile_status]
        print(f"{d.key:<18} {d.name:<32} {d.shape:<7} {d.device_type:>5} {d.width:>4}x{d.height:<4}  {status}"
              f"{'  (' + d.note + ')' if d.note else ''}")
    return 0


def cmd_sources(args) -> int:
    dev = get_device(args.device) if args.device else None
    for name, (sid, desc) in SOURCES.items():
        if dev and sid in dev.missing_sources:
            continue
        print(f"{name:<17} {sid:>9}  {desc}")
    return 0


def cmd_layouts(args) -> int:
    from .layouts import list_layouts, load_layout
    for name, desc in list_layouts().items():
        print(f"{name:<10} {desc}")
        if args.verbose:
            for slot, d in (load_layout(name, Path(".")).get("slots") or {}).items():
                print(f"    {slot:<11} {d.get('kind'):<8} {'(default)' if d.get('default') else ''}")
    return 0


def cmd_rules(args) -> int:
    print("Rule sources (use as `source:` in an imagelist, caption or art slot):\n")
    for name, (real, table) in RULES.items():
        keys = ", ".join(f"{k} {'+'.join(f'{a}-{b}' if a != b else str(a) for a, b in v)}" for k, v in table.items())
        print(f"  {name:<14} -> {real:<10} {keys}")
    print("""
Keys in images/texts mappings:
  40        threshold: from 40 until the next key
  "6-11"    inclusive range; values outside every range show nothing
  "22-5"    wrapping range (22..23 and 0..5)
  spring    named key of a rule source (season also takes hemisphere: south)
Rule bands can be moved with `boundaries:`, e.g. {calm: 0, normal: 35, medium: 55, high: 75}.""")
    return 0


def cmd_fonts(args) -> int:
    from . import fonts
    print(f"Nunito:       {fonts.download_font('rounded')}")
    print(f"Noto Sans TC: {fonts.download_font('sans')}")
    return 0


CLAUDE_MD = """\
# Watch faces with moodface

This workspace makes watch faces with the `moodface` CLI. Follow the `moodface` skill
(`.claude/skills/moodface/SKILL.md`).

- Faces live in `faces/<name>/` (`face.yaml` + `assets/`); `faces/example/` is a starting point.
- Default device: `{device}` (see `moodface devices`).
- Check with `moodface validate`, look at `moodface preview` output, then `moodface build`.
- The compiler always runs in Docker (see `Dockerfile`); never install it or Wine on this machine.
"""


def cmd_init(args) -> int:
    """Set up a workspace for making faces with Claude Code: skill, CLAUDE.md and an example face."""
    from importlib import resources

    ws = Path(args.workspace or ".").expanduser().resolve()
    get_device(args.device)  # validate the key early
    pkg = Path(str(resources.files("moodface")))
    files = {
        ws / ".claude" / "skills" / "moodface" / "SKILL.md": (pkg / "resources" / "skill" / "SKILL.md").read_text(encoding="utf-8"),
        ws / "CLAUDE.md": CLAUDE_MD.format(device=args.device),
        ws / ".gitignore": "build/\npreview/\n__pycache__/\n.DS_Store\n",
        ws / "Dockerfile": C.dockerfile_text(),
    }
    for path, text in files.items():
        if path.exists() and not args.force:
            print(f"skip    {path.relative_to(ws)} (exists; --force to overwrite)")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"create  {path.relative_to(ws)}")

    example = ws / "faces" / "example"
    if example.exists() and not args.force:
        print("skip    faces/example (exists)")
    else:
        if example.exists():
            shutil.rmtree(example)
        shutil.copytree(pkg / "examples" / "classic_bun", example)
        spec = example / "face.yaml"
        text = spec.read_text(encoding="utf-8")
        text = text.replace("name: classic_bun", "name: example").replace("device: band9", f"device: {args.device}")
        spec.write_text(text, encoding="utf-8")
        print("create  faces/example/ (the stress bun)")

    print(f"\nworkspace ready: {ws}")
    print("next:  cd into it and run `claude`, or try `moodface preview faces/example`")
    return 0


def cmd_validate(args) -> int:
    face = _load(args)
    ok = _report(face)
    print(f"{face.name}: {'OK' if ok else 'FAILED'} ({face.device.name}, {len(face.widgets)} widgets, id {face.id})")
    return 0 if ok else 1


def cmd_preview(args) -> int:
    face = _load(args)
    if not _report(face):
        return 1
    out = Path(args.output) if args.output else face.base / "preview"
    for p in write_previews(face, out, vary=args.vary):
        print(p)
    return 0


def cmd_build(args) -> int:
    face = _load(args)
    if not _report(face):
        return 1
    if face.device.compile_status == "fails":
        print(f"warning: {face.device.name} is known to fail with the bundled compiler ({face.device.note})")
    out = Path(args.output) if args.output else face.base / "build"
    fprj = write_project(face, out)
    print(f"project: {fprj} (id {face.id})")
    if args.no_compile:
        return 0

    comp = C.find_compiler(args.compiler)
    if not comp:
        print("compiler not found — run `moodface compiler setup` (or pass --compiler / set MOODFACE_COMPILER)")
        return 2
    runner = args.runner or C.default_runner()
    if runner == "docker":
        if not C.docker_available():
            print("Docker is not running; start Docker Desktop (moodface runs the compiler in a container)")
            return 2
        if not C.docker_image_exists(args.image):
            print(f"Docker image '{args.image}' missing — building it once (this takes a few minutes)...")
            if C.build_docker_image(args.image) != 0:
                return 2

    print(f"compiling with {runner} ...")
    res = C.compile_project(fprj, comp, runner=runner, image=args.image)
    want = C.expected_preview_size(res.output)
    if not res.ok and want:
        print(f"compiler expects a {want[0]}x{want[1]} preview for {face.device.name}; retrying "
              f"(add preview_size: [{want[0]}, {want[1]}] to the device profile to skip this)")
        write_project(face, out, thumb_size=want)
        res = C.compile_project(fprj, comp, runner=runner, image=args.image)
    if args.verbose or not res.ok:
        print(res.output.rstrip())
    if not res.ok:
        print("compile failed")
        return 1
    C.stamp_id(res.face_file, face.id)
    target = out / f"{face.name}.bin"
    shutil.copyfile(res.face_file, target)
    print(f"built: {target} ({target.stat().st_size} bytes, id {face.id})")
    return 0


def cmd_compiler(args) -> int:
    if args.action == "status":
        comp = C.find_compiler()
        print(f"compiler: {comp or 'not installed'}")
        print(f"runner:   {C.default_runner()}")
        if C.default_runner() == "docker":
            up = C.docker_available()
            print(f"docker:   {'running' if up else 'not available'}")
            if up:
                print(f"image:    {C.DOCKER_IMAGE} {'present' if C.docker_image_exists() else 'missing'}")
        return 0 if comp else 1
    if args.action == "docker-build":
        return C.build_docker_image(args.image, args.file)
    # setup
    print("moodface needs compile.exe, a closed-source compiler shipped with Mi Create:")
    print(f"  {C.MI_CREATE_REPO}")
    print(f"It will be downloaded to {C.home() / 'compiler'} and is not part of moodface.")
    if not args.yes:
        if input("Download it now? [y/N] ").strip().lower() not in ("y", "yes"):
            print("cancelled")
            return 1
    path = C.download_compiler()
    print(f"installed: {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="moodface", description="Stress-driven animated watch faces for Xiaomi Smart Bands")
    ap.add_argument("--version", action="version", version=f"moodface {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("devices", help="list device profiles")
    p.add_argument("--shape", choices=["band", "square", "round"])
    p.set_defaults(func=cmd_devices)

    p = sub.add_parser("layouts", help="list built-in layouts")
    p.add_argument("-v", "--verbose", action="store_true", help="show slots")
    p.set_defaults(func=cmd_layouts)

    sub.add_parser("rules", help="list rule sources and key syntax").set_defaults(func=cmd_rules)

    p = sub.add_parser("init", help="set up a workspace for Claude Code (skill, CLAUDE.md, example face)")
    p.add_argument("--workspace", help="folder to set up (default: current folder)")
    p.add_argument("--device", default="band9", help="default device for the workspace (default: band9)")
    p.add_argument("--force", action="store_true", help="overwrite existing files")
    p.set_defaults(func=cmd_init)
    p = sub.add_parser("fonts", help="download the fonts (Nunito, Noto Sans TC; SIL Open Font License)")
    p.add_argument("action", choices=["setup"])
    p.set_defaults(func=cmd_fonts)

    p = sub.add_parser("sources", help="list data sources")
    p.add_argument("--device")
    p.set_defaults(func=cmd_sources)

    for name, func, helptext in (("validate", cmd_validate, "check a face.yaml"),
                                 ("preview", cmd_preview, "render preview PNG/GIFs"),
                                 ("build", cmd_build, "build the .fprj project and compile it to .bin")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("face", nargs="?", default=".", help="face folder or face.yaml (default: .)")
        _device_args(p)
        if name in ("preview", "build"):
            p.add_argument("-o", "--output", help="output folder (default: <face>/preview or <face>/build)")
        if name == "preview":
            p.add_argument("--vary", action="append", metavar="SOURCE",
                           help="data source to simulate (repeatable; default: every source the face switches on)")
        if name == "build":
            p.add_argument("--no-compile", action="store_true", help="only write the .fprj project")
            p.add_argument("--compiler", help="path to compile.exe")
            p.add_argument("--runner", choices=["docker", "wine", "native"],
                           help="how to run the compiler (default: docker, isolated from your system)")
            p.add_argument("--image", default=C.DOCKER_IMAGE, help="Docker image with Wine")
            p.add_argument("-v", "--verbose", action="store_true")
            g = p.add_argument_group("face id (overrides face.yaml)")
            g.add_argument("--id", help="face id: 9-12 digits not starting with 0, or `time` for a new "
                                        "12-digit id from the build time (the band refuses an id that is "
                                        "already installed)")
            g.add_argument("--id-length", help="length of the id derived from the face name: 9 (default) or 12")
        p.set_defaults(func=func)

    p = sub.add_parser("compiler", help="manage the third-party compiler")
    p.add_argument("action", choices=["setup", "status", "docker-build"])
    p.add_argument("-y", "--yes", action="store_true", help="download without asking")
    p.add_argument("--image", default=C.DOCKER_IMAGE)
    p.add_argument("--file", help="Dockerfile for docker-build (default: the one bundled with moodface)")
    p.set_defaults(func=cmd_compiler)
    return ap


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (SpecError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
