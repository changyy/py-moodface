---
name: moodface
description: Make watch faces for Xiaomi smart bands and watches with the moodface CLI — faces that switch pictures and captions by stress level, time of day, season, weekday, battery or heart rate. Use when the user asks to create, change, preview or build a watch face (錶盤) in this workspace.
---

# moodface

moodface turns a folder with a `face.yaml` and PNG pictures into a watch face. You write the
YAML and draw the pictures; moodface handles layout, digits, dates, captions, previews and
building the `.bin`.

## Workflow

1. **Check the setup** — `moodface --version`. Building also needs Docker running and
   `moodface compiler status` to show a compiler; if it is missing, tell the user to run
   `moodface compiler setup` themselves — it downloads a third-party program.
2. **Pick device and layout** — `moodface devices` (default `band9`), `moodface layouts -v`.
3. **Create the face** in `faces/<name>/`: a `face.yaml` plus pictures in `faces/<name>/assets/`.
   Start from `faces/example/` or a bundled example:
   `python -c "import moodface, pathlib; print(pathlib.Path(moodface.__file__).parent / 'examples')"`.
4. **Draw the pictures** — write a small Pillow script, or use pictures the user provides.
   One picture per state (e.g. `calm.png`, `normal.png`, `medium.png`, `high.png`), all the same size.
5. **Check** — `moodface validate faces/<name>` and fix every error.
6. **Preview** — `moodface preview faces/<name>`, then look at `faces/<name>/preview/overview.png`
   (and the GIFs) and fix anything that overlaps, is clipped or is hard to read.
7. **Build** — `moodface build faces/<name>` → `faces/<name>/build/<name>.bin`.
   Try other devices with `--device` (e.g. `watchs4` for a round watch).

## Building runs in Docker

The compiler is a third-party Windows program. moodface always runs it inside a Docker
container (Wine on `linux/amd64`), so it never touches the host system — keep it that way.

- The workspace `Dockerfile` defines that container. `moodface build` creates the image
  (`moodface-wine`) on first use; rebuild it with `moodface compiler docker-build`, or
  `docker build --platform linux/amd64 -t moodface-wine -f Dockerfile .`.
- Do not install Wine, Mono or the compiler on the host, and do not use `--runner wine/native`.
- If a build fails: check `docker info` (Docker running?), `moodface compiler status`, then read
  the compiler output (`moodface build -v`). "Preview has wrong size" is retried automatically.
- On Apple Silicon the image is emulated: the first build takes a few minutes, later builds ~10 s.

## face.yaml in short

```yaml
name: my_face
device: band9
background: "#161210"
layout: classic                       # classic, scene, corner, big-time, stats, minimal, photo
style: {accent: "#F0A060"}
slots:
  character:
    source: stress_level              # calm 0-39, normal 40-59, medium 60-79, high 80-100
    images: {calm: assets/calm.png, normal: assets/normal.png, medium: assets/medium.png, high: assets/high.png}
  caption:
    texts: {calm: 好放鬆, normal: 狀態不錯, medium: 深呼吸, high: 休息一下}
  stats: [stress, steps, heart_rate]
```

- Other switching sources: `time_of_day`, `season`, `weekday`, `weekpart`, `battery_level`,
  `hr_level`, or a raw source (`hour`, `month`, …) with thresholds or ranges like `"22-5"`.
  Run `moodface rules` for the keys.
- `slots:` entries can be hidden with `false`; `variants: {round: {...}}` adjusts a face per screen shape.
- `id:` (9-12 digits, not starting with 0) is optional: by default it is derived from `name`
  (`id_length: 9` or `12`); `id: time` takes a new 12-digit id from the build time on every build. The band will not install a face whose id is already installed, so to
  update a face the old one must be removed from the band first (or build with another `--id`).
- Low-level `widgets:` (image, imagelist, number, text, bar, animation) are drawn on top of a layout.
- Full reference: https://github.com/changyy/py-moodface/blob/main/docs/reference.md

## Fonts

moodface draws digits and text with two openly licensed fonts — Nunito and Noto Sans TC —
downloaded once into `~/.cache/moodface/fonts` (`moodface fonts setup`; needs network).
To use another font, pass a file: `--font path/to.ttf` / `--text-font path/to.ttf`, the env vars
`MOODFACE_FONT` / `MOODFACE_TEXT_FONT`, or `style: {font: ..., text_font: ...}` in face.yaml.
Only use fonts whose license allows this (e.g. SIL Open Font License); never system fonts such
as SF or PingFang, whose licenses do not.

## Rules

- **Original artwork only.** Do not draw or trace existing characters, logos or brands, and do not use
  photos unless the user owns them. Landmarks and scenery are fine when drawn from scratch.
- Text on the face is rendered by moodface from `texts:` / `text:` — don't paint captions into pictures.
- Keep pictures in one list the same size; draw full-screen art for the largest target screen.
- Always look at the preview images before saying a face is done.
- Never install anything on the user's device; hand over the `.bin` path and let the user install it.
