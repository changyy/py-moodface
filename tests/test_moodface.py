import shutil
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image

from moodface import get_device, load_face, validate
from moodface.cli import main
from moodface.compiler import stamp_id
from moodface.fprj import flat_name, write_project
from moodface.render import pick_index, render_frame, stress_samples
from moodface.sources import resolve
from moodface.spec import SpecError, derive_id

EXAMPLE = Path(__file__).resolve().parent.parent / "src" / "moodface" / "examples" / "stress_test"


def make_face(tmp: Path, yaml_text: str, images=None) -> Path:
    for rel, size in (images or {}).items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", size, (255, 0, 0, 255)).save(p)
    (tmp / "face.yaml").write_text(yaml_text, encoding="utf-8")
    return tmp


class DevicesTest(unittest.TestCase):
    def test_known_and_override(self):
        self.assertEqual(get_device("band9").device_type, "366")
        self.assertEqual(get_device("Band-10").width, 212)
        custom = get_device("band9", width=200)
        self.assertEqual(custom.width, 200)
        self.assertEqual(custom.compile_status, "untested")

    def test_custom_device(self):
        d = get_device("band11", width=220, height=540, device_type="999", radius=110)
        self.assertEqual((d.width, d.height, d.device_type), (220, 540, "999"))
        with self.assertRaises(ValueError):
            get_device("band11")

    def test_shapes(self):
        self.assertEqual(get_device("band9").shape, "band")
        self.assertEqual(get_device("redmiwatch5").shape, "square")
        self.assertEqual(get_device("watchs4").shape, "round")
        self.assertEqual(get_device("x", width=400, height=400, radius=200, device_type="1").shape, "round")
        self.assertEqual(get_device("band9", shape="square").shape, "square")

    def test_thumbnail(self):
        self.assertEqual(get_device("band9").thumbnail_size, (122, 310))
        self.assertEqual(get_device("watchs4").thumbnail_size, (326, 326))
        self.assertEqual(get_device("redmiwatch5active").compile_status, "fails")


class SpecTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_example_is_valid(self):
        face = load_face(EXAMPLE)
        errors, _ = validate(face)
        self.assertEqual(errors, [])
        self.assertEqual(face.device.key, "band9")
        anim = [w for w in face.widgets if w.type == "animation"][0]
        self.assertEqual(len(anim.images), 8)
        self.assertEqual(anim.images[0][1], "assets/anim/0.png")

    def test_source_names(self):
        self.assertEqual(resolve("stress"), "0826")
        self.assertEqual(resolve("0822"), "0822")
        with self.assertRaises(ValueError):
            resolve("mood")

    def test_mismatched_imagelist_sizes(self):
        make_face(self.tmp, """
widgets:
  - type: imagelist
    source: stress
    images: {0: a.png, 50: b.png}
""", {"a.png": (10, 10), "b.png": (12, 10)})
        errors, _ = validate(load_face(self.tmp))
        self.assertTrue(any("same size" in e for e in errors))

    def test_missing_source_on_device(self):
        make_face(self.tmp, """
device: band10
widgets:
  - type: number
    source: steps_km
    images: d{n}.png
""", {f"d{n}.png": (8, 10) for n in range(10)})
        errors, _ = validate(load_face(self.tmp))
        self.assertTrue(any("not available" in e for e in errors))

    def test_bad_spec(self):
        make_face(self.tmp, "widgets:\n  - type: circle\n")
        with self.assertRaises(SpecError):
            load_face(self.tmp)


class FaceIdTest(unittest.TestCase):
    YAML = "name: {name}\n{extra}widgets:\n  - {{type: image, image: a.png}}\n"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def face(self, name="my_face", extra="", **kw):
        make_face(self.tmp, self.YAML.format(name=name, extra=extra), {"a.png": (4, 4)})
        return load_face(self.tmp, **kw)

    def test_derive_id(self):
        for length in (9, 12):
            ids = {derive_id(f"face_{i}", length) for i in range(200)}
            self.assertEqual(len(ids), 200)
            for fid in ids:
                self.assertRegex(fid, r"^[1-9]\d{%d}$" % (length - 1))
        self.assertEqual(derive_id("classic_bun"), derive_id("classic_bun"))
        self.assertEqual(derive_id("classic_bun"), "%d" % (10 ** 8 + int.from_bytes(
            __import__("hashlib").sha256(b"classic_bun").digest(), "big") % (9 * 10 ** 8)))
        with self.assertRaises(SpecError):
            derive_id("x", 10)

    def test_derived_by_default(self):
        face = self.face()
        self.assertEqual(face.id, derive_id("my_face"))
        self.assertEqual(validate(face)[0], [])
        self.assertNotEqual(self.face("other_face").id, face.id)
        self.assertEqual(self.face(extra="id_length: 12\n").id, derive_id("my_face", 12))

    def test_time_id(self):
        from datetime import datetime
        from moodface.spec import time_id
        self.assertEqual(time_id(datetime(2026, 11, 19, 21, 30, 45)), "261119213045")
        before = datetime.now().strftime("%y%m%d%H%M%S")
        fid = self.face(extra="id: time\n").id
        after = datetime.now().strftime("%y%m%d%H%M%S")
        self.assertRegex(fid, r"^[1-9]\d{11}$")
        self.assertTrue(before <= fid <= after, (before, fid, after))
        self.assertEqual(validate(self.face(extra="id: TIME\n"))[0], [])
        self.assertRegex(self.face(face_id="time").id, r"^[1-9]\d{11}$")

    def test_explicit_id_wins(self):
        self.assertEqual(self.face(extra="id: 120917399901\nid_length: 9\n").id, "120917399901")
        self.assertEqual(self.face(extra="id: '167210077'\n").id, "167210077")
        self.assertEqual(self.face(extra="id: 167210077\n", face_id="987654321").id, "987654321")
        self.assertEqual(self.face(extra="id: 167210077\n", id_length=12).id, "167210077")
        self.assertEqual(self.face(id_length="12").id, derive_id("my_face", 12))

    def test_bad_id(self):
        for extra in ("id: 12345678\n", "id: 1234567890123\n", "id: '012345678'\n", "id: 12345678a\n",
                      "id_length: 10\n", "id_length: abc\n"):
            with self.assertRaisesRegex(SpecError, r"id must be 9-12 digits|id_length must be 9 or 12"):
                self.face(extra=extra)
        with self.assertRaises(SpecError):
            self.face(face_id="12345")

    def test_fprj_id(self):
        face = self.face(extra="id: 120917399901\n")
        root = ET.parse(write_project(face, self.tmp / "build")).getroot()
        self.assertEqual(root.get("Id"), "120917399901")


class RenderTest(unittest.TestCase):
    def test_threshold_pick(self):
        face = load_face(EXAMPLE)
        bg = face.widgets[0]
        self.assertEqual(pick_index(bg, 0), "assets/bg/a.png")
        self.assertEqual(pick_index(bg, 39), "assets/bg/a.png")
        self.assertEqual(pick_index(bg, 40), "assets/bg/b.png")
        self.assertEqual(pick_index(bg, 100), "assets/bg/d.png")

    def test_frame_size_and_samples(self):
        face = load_face(EXAMPLE)
        self.assertEqual(render_frame(face, {"stress": 70}, 3).size, (192, 490))
        self.assertEqual(stress_samples(face), [19, 49, 69, 90])


class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_write_project(self):
        face = load_face(EXAMPLE)
        fprj = write_project(face, self.tmp)
        root = ET.parse(fprj).getroot()
        self.assertEqual(root.get("DeviceType"), "366")
        widgets = root.find("Screen").findall("Widget")
        bg = widgets[0]
        self.assertEqual(bg.get("Index_Src"), "0826")
        self.assertEqual(bg.get("BitmapList").split("|")[1], "(40):assets__bg__b.png")
        stress = [w for w in widgets if w.get("Name") == "stress_value"][0]
        self.assertEqual((stress.get("Alignment"), stress.get("Blanking"), stress.get("Width")), ("1", "1", "54"))
        self.assertEqual(widgets[-1].get("Name"), "anim_[0@120]")
        self.assertTrue((self.tmp / "images" / flat_name("assets/anim/7.png")).is_file())
        with Image.open(self.tmp / "images" / "_preview.png") as im:
            self.assertEqual(im.size, (122, 310))

    def test_stamp_id(self):
        for fid in ("123456789", "120917399901"):
            p = self.tmp / "x.face"
            p.write_bytes(b"\xee" * 0x68 + b"Title" + b"\xee" * 8)
            stamp_id(p, fid)
            data = p.read_bytes()
            self.assertEqual(data[:0x28], b"\xee" * 0x28)
            self.assertEqual(data[0x28:0x68], fid.encode() + bytes(0x40 - len(fid)))
            self.assertEqual(data[0x68:], b"Title" + b"\xee" * 8)
        for bad in ("12345678", "1234567890123", "12345678x"):
            with self.assertRaises(ValueError):
                stamp_id(p, bad)


class CliTest(unittest.TestCase):
    def test_validate_and_no_compile_build(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            self.assertEqual(main(["validate", str(EXAMPLE)]), 0)
            self.assertEqual(main(["build", str(EXAMPLE), "-o", str(tmp), "--no-compile"]), 0)
            self.assertTrue((tmp / "stress_test.fprj").is_file())
            self.assertEqual(main(["validate", str(EXAMPLE), "--device", "band10"]), 0)
        finally:
            shutil.rmtree(tmp)

    def test_build_id_override(self):
        import contextlib
        import io
        tmp = Path(tempfile.mkdtemp())
        try:
            for extra, want in ((["--id", "120917399901"], "120917399901"),
                                (["--id-length", "12"], derive_id("stress_test", 12)),
                                ([], derive_id("stress_test"))):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(main(["build", str(EXAMPLE), "-o", str(tmp), "--no-compile"] + extra), 0)
                self.assertIn(f"(id {want})", out.getvalue())
                self.assertEqual(ET.parse(tmp / "stress_test.fprj").getroot().get("Id"), want)
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(main(["build", str(EXAMPLE), "-o", str(tmp), "--no-compile", "--id", "0123456789"]), 1)
                self.assertEqual(main(["build", str(EXAMPLE), "-o", str(tmp), "--no-compile", "--id-length", "10"]), 1)
            self.assertIn("id must be 9-12 digits", err.getvalue())
            self.assertIn("id_length must be 9 or 12", err.getvalue())
        finally:
            shutil.rmtree(tmp)


class RulesTest(unittest.TestCase):
    def test_season_north_and_south(self):
        from moodface.rules import build_thresholds
        m = {"spring": "sp", "summer": "su", "autumn": "au", "winter": "wi"}
        self.assertEqual(build_thresholds(m, "1012", "season"),
                         [(1, "wi"), (3, "sp"), (6, "su"), (9, "au"), (12, "wi")])
        south = dict(build_thresholds(m, "1012", "season", "south"))
        self.assertEqual(south[1], "su")

    def test_ranges_wrap_and_gaps(self):
        from moodface.rules import build_thresholds
        self.assertEqual(build_thresholds({"22-5": "night"}, "0811"), [(0, "night"), (6, None), (22, "night")])
        self.assertEqual(build_thresholds({"9-17": "work"}, "0811"), [(0, None), (9, "work"), (18, None)])

    def test_thresholds_insert_leading_gap(self):
        from moodface.rules import build_thresholds
        self.assertEqual(build_thresholds({40: "b"}, "0826"), [(0, None), (40, "b")])

    def test_boundaries_and_errors(self):
        from moodface.rules import build_thresholds
        out = build_thresholds({"calm": "c", "high": "h"}, "0826", "stress_level",
                               boundaries={"calm": 0, "normal": 30, "high": 70})
        self.assertEqual(out, [(0, "c"), (30, None), (70, "h")])
        with self.assertRaises(ValueError):
            build_thresholds({"winter": "w"}, "0826", "stress_level")
        with self.assertRaises(ValueError):
            build_thresholds({"1-5": "a", "4-8": "b"}, "0811")


LAYOUT_FACE = """
name: lay
device: {device}
layout: classic
style: {{text_font: rounded}}
slots:
  character:
    source: stress_level
    images: {{calm: a.png, normal: a.png, medium: b.png, high: b.png}}
  caption:
    texts: {{calm: relax, normal: fine, medium: tense, high: rest}}
  date: {{format: "MM/DD WWW"}}
  bar: {{}}
  stats:
    - {{source: steps, label: Steps}}
    - {{source: heart_rate, label: HR}}
"""


class LayoutTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _face(self, device="band9"):
        make_face(self.tmp, LAYOUT_FACE.format(device=device), {"a.png": (100, 80), "b.png": (100, 80)})
        return load_face(self.tmp)

    def test_classic_expands_and_validates(self):
        face = self._face()
        errors, _ = validate(face)
        self.assertEqual(errors, [])
        kinds = {w.name.split("_")[0] for w in face.widgets}
        self.assertTrue({"time", "date", "character", "caption", "bar", "stats"} <= kinds)
        char = [w for w in face.widgets if w.name == "character"][0]
        self.assertEqual(face.widget_size(char), (round(192 * 0.96), round(490 * 0.39)))
        self.assertEqual(char.source, "0826")

    def test_same_face_other_device(self):
        face = self._face("band9pro")
        char = [w for w in face.widgets if w.name == "character"][0]
        self.assertEqual(face.widget_size(char)[0], round(336 * 0.96))
        self.assertEqual(validate(face)[0], [])

    def test_round_variant(self):
        face = self._face("watchs4")
        char = [w for w in face.widgets if w.name == "character"][0]
        self.assertEqual(face.widget_size(char), (round(466 * 0.40), round(466 * 0.32)))
        errors, warnings = validate(face)
        self.assertEqual(errors, [])
        self.assertFalse([w for w in warnings if "round screen" in w], warnings)

    def test_face_variant_overrides(self):
        make_face(self.tmp, """
layout: minimal
style: {text_font: rounded}
slots: {date: {format: "MM/DD"}}
variants:
  round:
    style: {color: "#FF0000"}
    slots: {date: false}
""")
        band = load_face(self.tmp)
        self.assertTrue(any(w.name.startswith("date") for w in band.widgets))
        rnd = load_face(self.tmp, device=get_device("watchs3"))
        self.assertFalse(any(w.name.startswith("date") for w in rnd.widgets))
        self.assertEqual(rnd.style["color"], "#FF0000")

    def test_round_clipping_warning(self):
        make_face(self.tmp, "device: watchs4\nwidgets:\n  - {type: image, image: a.png, x: 0, y: 0}\n",
                  {"a.png": (60, 60)})
        self.assertTrue(any("round screen" in w for w in validate(load_face(self.tmp))[1]))

    def test_time_is_centered(self):
        face = self._face()
        hours = [w for w in face.widgets if w.name == "time_0"][0]
        minutes = [w for w in face.widgets if w.name == "time_2"][0]
        left, right = hours.x, 192 - (minutes.x + face.widget_size(minutes)[0])
        self.assertLessEqual(abs(left - right), 2)

    def test_disable_slot_and_unknown_slot(self):
        make_face(self.tmp, "layout: minimal\nstyle: {text_font: rounded}\nslots: {date: false}\n")
        face = load_face(self.tmp)
        self.assertFalse(any(w.name.startswith("date") for w in face.widgets))
        make_face(self.tmp, "layout: minimal\nslots: {nope: {}}\n")
        with self.assertRaises(SpecError):
            load_face(self.tmp)

    def test_preview_varies_sources(self):
        from moodface.render import samples_for, varying_sources
        face = self._face()
        self.assertEqual(varying_sources(face), ["stress"])
        self.assertEqual(samples_for(face, "stress"), [19, 49, 69, 90])


class SceneLayoutTest(unittest.TestCase):
    def test_scene_icon_unit_badge_and_vertical_bar(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            make_face(tmp, """
layout: scene
style: {text_font: rounded}
slots:
  weekday: {lang: en}
  steps:
    items: [{source: steps, icon: icon.png}]
    card: {fill: "#FFFFFF22", outline: "#FFFFFF88"}
""", {"icon.png": (32, 32)})
            face = load_face(tmp)
            self.assertEqual(validate(face)[0], [])
            names = {w.name for w in face.widgets}
            self.assertTrue({"steps_0_icon", "steps_0_value", "steps_0_card", "card_value_0_unit",
                             "battery_bar", "weekday"} <= names)
            self.assertNotIn("card_value_0_label", names)
            week = [w for w in face.widgets if w.name == "weekday"][0]
            self.assertEqual(week.source, "2012")
            self.assertEqual(len({face.image(k).size for _, k in week.images}), 1)  # badges share one size
            bar = [w for w in face.widgets if w.name == "battery_bar"][0]
            full = face.image(bar.images[-1][1])
            empty = face.image(bar.images[0][1])
            # vertical bar: top pixel is filled only when full
            self.assertGreater(full.getpixel((full.width // 2, 2))[3], empty.getpixel((empty.width // 2, 2))[3] + 50)
            for dev in ("redmiwatch5", "watchs4"):
                self.assertEqual(validate(load_face(tmp, device=get_device(dev)))[0], [])
        finally:
            shutil.rmtree(tmp)


class GeneratedTest(unittest.TestCase):
    def test_text_number_bar_fill(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            make_face(tmp, """
style: {text_font: rounded}
widgets:
  - {type: image, fill: "#00000080", w: 50%, h: 40, radius: 8}
  - {type: text, text: Hello, size: 20, x: 50%, y: 10, anchor: top, stroke: 2}
  - {type: number, source: steps, digits: 5, size: 5%, x: 10, y: 100}
  - {type: bar, source: battery, w: 80, h: 6, x: 10, y: 200, steps: 4}
  - {type: imagelist, source: time_of_day, texts: {night: zzz, day: sun}, size: 18, x: 10, y: 300}
""")
            face = load_face(tmp)
            self.assertEqual(validate(face)[0], [])
            fill, text, number, bar, tod = face.widgets
            self.assertEqual(face.widget_size(fill), (96, 40))
            tw = face.widget_size(text)[0]
            self.assertEqual(text.x, 96 - round(tw / 2))
            self.assertEqual(len(bar.images), 5)
            self.assertEqual([t for t, _ in tod.images], [0, 5, 8, 17, 19])
            fprj = write_project(face, tmp / "build")
            self.assertTrue(fprj.is_file())
        finally:
            shutil.rmtree(tmp)


class FontOverrideTest(unittest.TestCase):
    def test_font_override_from_cli_and_env(self):
        import os
        from moodface.fonts import font_path
        nunito = str(font_path("rounded"))
        face = load_face(EXAMPLE, style_override={"font": nunito, "text_font": None})
        self.assertEqual(face.style["font"], nunito)
        os.environ["MOODFACE_TEXT_FONT"] = nunito
        try:
            self.assertEqual(load_face(EXAMPLE).style["text_font"], nunito)
        finally:
            del os.environ["MOODFACE_TEXT_FONT"]
        self.assertEqual(main(["validate", str(EXAMPLE), "--font", nunito]), 0)
        with self.assertRaises(ValueError):
            font_path("/no/such/font.ttf")


class InitTest(unittest.TestCase):
    def test_init_workspace(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            self.assertEqual(main(["init", "--workspace", str(tmp), "--device", "watchs4"]), 0)
            skill = (tmp / ".claude" / "skills" / "moodface" / "SKILL.md").read_text(encoding="utf-8")
            self.assertTrue(skill.startswith("---\nname: moodface\n"))
            self.assertIn("watchs4", (tmp / "CLAUDE.md").read_text(encoding="utf-8"))
            self.assertIn("wine", (tmp / "Dockerfile").read_text(encoding="utf-8"))
            self.assertIn("Building runs in Docker", skill)
            face = load_face(tmp / "faces" / "example")
            self.assertEqual((face.name, face.device.key), ("example", "watchs4"))
            # existing files are kept unless --force
            (tmp / "CLAUDE.md").write_text("mine", encoding="utf-8")
            self.assertEqual(main(["init", "--workspace", str(tmp)]), 0)
            self.assertEqual((tmp / "CLAUDE.md").read_text(encoding="utf-8"), "mine")
            self.assertEqual(main(["init", "--workspace", str(tmp), "--force"]), 0)
            self.assertNotEqual((tmp / "CLAUDE.md").read_text(encoding="utf-8"), "mine")
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
