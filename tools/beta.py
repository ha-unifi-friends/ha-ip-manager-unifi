"""Beta channel: the app «IP Manager for UniFi Beta» (folder dhcp_reservations_beta/) next to the stable app.

Both apps live in this repository, so Home Assistant shows them side by side. The beta has its own slug
(dhcp_reservations_beta): it installs next to the stable app with its own data (/data), and its icon carries an
orange «BETA» band. New features go into dhcp_reservations_beta/ first.

    python3 tools/beta.py import <path to a dhcp_reservations folder>
        replace the beta with that folder (e.g. from the former beta repository) and make it a beta app
    python3 tools/beta.py fix
        re-apply the beta settings (name, slug, panel title, icon) after editing dhcp_reservations_beta/
    python3 tools/beta.py promote
        release the beta as stable: dhcp_reservations/ gets the beta code, stable name/slug/icon are kept

Home Assistant offers an update when the `version` in the app's config.yaml changes.
Needs Pillow for the icon (pip install pillow).
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STABLE, BETA = ROOT / "dhcp_reservations", ROOT / "dhcp_reservations_beta"
URL = "https://github.com/ha-unifi-friends/ha-ip-manager-unifi"
ORANGE = (255, 146, 43, 255)
FONTS = ["/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"]
BETA_NOTE = ("> **Beta** – this is the test channel of IP Manager for UniFi. It installs next to the stable app with its "
             "own settings and data. New features land here first.\n\n")


def set_keys(cfg: Path, values: dict[str, str]) -> None:
    text = cfg.read_text(encoding="utf-8")
    for key, value in values.items():
        text, n = re.subn(rf"^{key}:.*$", f"{key}: {value}", text, count=1, flags=re.M)
        assert n, f"{cfg} has no '{key}'"
    cfg.write_text(text, encoding="utf-8")


def beta_icons() -> None:
    from PIL import Image, ImageDraw, ImageFont

    def font(size: int):
        for f in FONTS:
            if Path(f).is_file():
                return ImageFont.truetype(f, size)
        return ImageFont.load_default()

    icon = Image.open(STABLE / "icon.png").convert("RGBA").resize((512, 512), Image.LANCZOS)
    d = ImageDraw.Draw(icon)
    d.rounded_rectangle((30, 360, 482, 472), radius=56, fill=ORANGE)
    d.text((256, 416), "BETA", font=font(86), fill="white", anchor="mm")
    icon.resize((128, 128), Image.LANCZOS).save(BETA / "icon.png", optimize=True)

    logo = Image.open(STABLE / "logo.png").convert("RGBA")
    w, h = logo.size
    f = font(int(h * 0.36))
    tw = ImageDraw.Draw(logo).textlength("BETA", font=f)
    bw = int(tw + h * 0.36)
    out = Image.new("RGBA", (w + bw + int(h * 0.15), h), (0, 0, 0, 0))
    out.paste(logo, (0, 0), logo)
    d = ImageDraw.Draw(out)
    x0, y0, y1 = w + int(h * 0.15), int(h * 0.27), int(h * 0.73)
    d.rounded_rectangle((x0, y0, x0 + bw, y1), radius=(y1 - y0) // 2, fill=ORANGE)
    d.text((x0 + bw / 2, (y0 + y1) / 2), "BETA", font=f, fill="white", anchor="mm")
    out.save(BETA / "logo.png", optimize=True)


def fix() -> None:
    cfg = BETA / "config.yaml"
    set_keys(cfg, {"name": '"IP Manager for UniFi Beta"', "slug": "dhcp_reservations_beta", "url": URL,
                   "panel_title": '"IP Manager Beta"'})
    text = cfg.read_text(encoding="utf-8")
    if not re.search(r'^description: "BETA – ', text, flags=re.M):
        text = re.sub(r'^description: "(.*)"$', r'description: "BETA – \1"', text, count=1, flags=re.M)
    cfg.write_text(text, encoding="utf-8")
    readme = BETA / "README.md"
    if readme.is_file() and BETA_NOTE not in readme.read_text(encoding="utf-8"):
        readme.write_text(BETA_NOTE + readme.read_text(encoding="utf-8"), encoding="utf-8")
    beta_icons()
    print("beta settings applied to", BETA)


def copy_app(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".DS_Store"))


def main(argv: list[str]) -> None:
    if argv[:1] == ["import"] and len(argv) == 2:
        src = Path(argv[1]).resolve()
        if not (src / "config.yaml").is_file():
            sys.exit(f"{src} is not an app folder")
        copy_app(src, BETA)
        fix()
    elif argv == ["fix"]:
        fix()
    elif argv == ["promote"]:
        keep = {n: (STABLE / n).read_bytes() for n in ("icon.png", "logo.png")}
        stable_cfg = (STABLE / "config.yaml").read_text(encoding="utf-8")
        copy_app(BETA, STABLE)
        for n, b in keep.items():
            (STABLE / n).write_bytes(b)
        get = lambda k: re.search(rf"^{k}:.*$", stable_cfg, flags=re.M).group(0).split(":", 1)[1].strip()
        set_keys(STABLE / "config.yaml", {k: get(k) for k in ("name", "slug", "url", "panel_title")})
        text = (STABLE / "config.yaml").read_text(encoding="utf-8").replace('description: "BETA – ', 'description: "', 1)
        (STABLE / "config.yaml").write_text(text, encoding="utf-8")
        readme = STABLE / "README.md"
        if readme.is_file():
            readme.write_text(readme.read_text(encoding="utf-8").replace(BETA_NOTE, ""), encoding="utf-8")
        print("beta released as stable in", STABLE)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
