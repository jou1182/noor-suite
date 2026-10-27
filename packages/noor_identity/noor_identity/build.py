"""Validate an identity and compile local color/font tokens before serving it."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from jsonschema import ValidationError, validate


class IdentityBuildError(ValueError):
    """The profile cannot safely be presented."""


def _channel(value: int) -> float:
    scaled = value / 255
    return scaled / 12.92 if scaled <= 0.04045 else ((scaled + 0.055) / 1.055) ** 2.4


def contrast(foreground: str, background: str) -> float:
    def luminance(color: str) -> float:
        channels = [_channel(int(color[i:i + 2], 16)) for i in (1, 3, 5)]
        return sum(a * b for a, b in zip(channels, (0.2126, 0.7152, 0.0722)))

    light, dark = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def _referenced_file(root: Path, name: str) -> Path:
    if not name or Path(name).is_absolute() or "\\" in name or ".." in Path(name).parts:
        raise IdentityBuildError("referenced file escapes identity directory")
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        raise IdentityBuildError("referenced file escapes identity directory")
    if not path.is_file():
        raise IdentityBuildError(f"referenced file missing: {name}")
    return path


def _image_mimetype(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) > 32 and data[12:16] == b"IHDR":
        return "image/png"
    if data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9"):
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) > 14:
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP" and len(data) > 20:
        return "image/webp"
    return None


def _css_string(value: str) -> str:
    return '"' + "".join(f"\\{ord(c):x} " if c in '"\\\n\r\f' else c for c in value) + '"'


def _css_palette(palette: dict) -> str:
    return "\n".join(f"  --noor-{key.replace('_', '-')}: {value};" for key, value in palette.items())


def build_identity(identity_dir: str | Path) -> dict:
    """Build tokens, failing before writing if schema, files, or contrast are invalid."""
    root = Path(identity_dir).resolve()
    try:
        profile = json.loads((root / "profile.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise IdentityBuildError("profile.json missing or unreadable") from exc
    from noor_contracts import __file__ as contracts_init

    schema_path = Path(contracts_init).parent / "schemas" / "identity-profile.schema.json"
    try:
        validate(profile, json.loads(schema_path.read_text(encoding="utf-8")))
    except (ValidationError, ValueError) as exc:
        raise IdentityBuildError(f"identity schema failure: {exc.message if isinstance(exc, ValidationError) else exc}") from exc

    referenced = list(profile["font"]["files"])
    if profile["font"]["rights_ref"]:
        referenced.append(profile["font"]["rights_ref"])
    if profile["logo_rights_ref"]:
        referenced.append(profile["logo_rights_ref"])
    if profile["logo"]:
        referenced.append(profile["logo"])
    for name in referenced:
        _referenced_file(root, name)

    for mode, palette in profile["palette"].items():
        pairs = [("on_primary", "primary"), ("on_surface", "surface"),
                 ("primary", "surface"), ("muted", "surface"), ("focus", "surface")]
        pairs += [(key, "surface") for key in palette if key.startswith("status_")]
        for foreground, background in pairs:
            if contrast(palette[foreground], palette[background]) < 4.5:
                raise IdentityBuildError(f"contrast below 4.5:1: {mode}.{foreground} on {background}")

    font_faces = []
    for name in profile["font"]["files"]:
        weight = 700 if "bold" in name.lower() else 400
        font_faces.append(
            f'@font-face {{ font-family: {_css_string(profile["font"]["family"])}; '
            f'src: url("/identity/{quote(name, safe="/")}") format("truetype"); '
            f'font-weight: {weight}; font-display: swap; }}'
        )
    palettes = profile["palette"]
    css = "\n".join(font_faces) + "\n"
    css += ":root, [data-theme=\"light\"] {\n" + _css_palette(palettes["light"]) + "\n}\n"
    css += "@media (prefers-color-scheme: dark) { :root:not([data-theme]) {\n" + _css_palette(palettes["dark"]) + "\n} }\n"
    css += "[data-theme=\"dark\"] {\n" + _css_palette(palettes["dark"]) + "\n}\n"
    css += ":root { --noor-font-family: " + _css_string(profile["font"]["family"]) + "; }\n"
    logo_mimetype = _image_mimetype(root / profile["logo"]) if profile["logo"] else None
    logo_ok = logo_mimetype is not None
    tokens = {
        "system_name": profile["system_name"], "short_name": profile["short_name"],
        "company_name": profile["company_name"], "logo": profile["logo"] if logo_ok else None,
        "logo_ok": logo_ok, "logo_mimetype": logo_mimetype, "font_family": profile["font"]["family"],
        "font_fallback": profile["font"]["fallback"], "font_files": profile["font"]["files"],
        "palette": palettes,
    }
    output = root / "build"
    output.mkdir(exist_ok=True)
    (output / "noor-tokens.css").write_text(css, encoding="utf-8")
    (output / "noor_tokens.json").write_text(json.dumps(tokens, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return tokens
