"""The visible home shell reports pending platforms without implying integration."""

from html.parser import HTMLParser
from pathlib import Path
import json
import os
import struct
import zlib

import pytest
from noor_registry.app import create_app

from noor_registry.platforms_registry import ORDER


def _previous_identity_names() -> list[str]:
    """Names live only in the owner's blocklist outside the public repository (FR-025)."""
    location = os.environ.get("NOOR_BLOCKLIST_FILE")
    if not location or not Path(location).is_file():
        pytest.skip("NOOR_BLOCKLIST_FILE not set; previous-identity check needs the owner's list")
    lines = Path(location).read_text(encoding="utf-8-sig").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


class ShellParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.badges = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a" and "platform-button" in values.get("class", ""):
            self.current = {"href": values.get("href"), "text": ""}
            self.links.append(self.current)
        if tag == "span" and "platform-state" in values.get("class", ""):
            self.badges.append({"aria": values.get("aria-label"), "text": ""})

    def handle_data(self, data):
        if self.current:
            self.current["text"] += data
        if self.badges:
            self.badges[-1]["text"] += data

    def handle_endtag(self, tag):
        if tag == "a":
            self.current = None


def test_home_has_fixed_buttons_and_badges(client_for):
    response = client_for("pm").get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    parser = ShellParser()
    parser.feed(html)
    assert [link["href"].split("/")[-1] for link in parser.links] == list(ORDER)
    assert [name in link["text"] for name, link in zip(
        ("الرادار", "التحليل السريع", "NMIS", "ATPAS", "JoUReady"), parser.links)] == [True] * 5
    assert len(parser.badges) == 5
    assert all(badge["aria"] and badge["text"].strip() for badge in parser.badges)
    assert "لم تُستلم لقطة هذه المنصة بعد؛ لا تُعرض عاملة" in html
    for name in ("المنافسات", "استيراد", "إدخال يدوي"):
        assert name in html
    for phrase in ("لم يُقَس بعد", "XER ومونت كارلو مؤجلان", "حكم النموذج المحلي غير مفعّل",
                   "فحص إحالات SBC المحدود", "ثلاث وحدات إلى خمس", "تأكيد المرشدين لم يُحسم بعد",
                   "جاهزة للبيع", "وضع المزود"):
        assert phrase in html
    assert html.count("نتيجة قائمة FR-010") >= 5


def test_running_pending_is_disclosed_as_not_cleared(client_for, nmis_app):
    nmis_app.app.extensions["noor_registry"]["platforms"]["radar"]["run_state"] = "running"
    html = client_for("pm").get("/").get_data(as_text=True)
    parser = ShellParser()
    parser.feed(html)
    radar = next(link for link in parser.links if link["href"].endswith("/radar"))
    assert "لم تجتز شروط العرض" in radar["text"]
    assert "تعمل" not in radar["text"]


def test_platform_page_is_placeholder_and_unknown_is_404(client_for):
    client = client_for("pm")
    response = client.get("/platform/radar")
    assert response.status_code == 200
    assert "ستُفتح المنصة هنا بعد استلام لقطتها واجتياز شروط العرض" in response.get_data(as_text=True)
    assert "لم يُقَس بعد" in response.get_data(as_text=True)
    assert "لم تجتز شروط العرض" in response.get_data(as_text=True)
    assert client.get("/platform/unknown").status_code == 404


def test_login_required(client_for):
    client = client_for(None)
    assert client.get("/").status_code == 302
    assert client.get("/platform/radar").status_code == 302


def test_no_external_assets_or_previous_identity(client_for):
    client = client_for("pm")
    pages = [client.get(path).get_data(as_text=True) for path in
             ("/", "/platform/radar", "/login", "/tenders")]
    pages += [client.get("/identity/build/noor-tokens.css").get_data(as_text=True),
              client.get("/static/noor.css").get_data(as_text=True)]
    old_names = _previous_identity_names()
    for page in pages:
        assert all(name.casefold() not in page.casefold() for name in old_names)
        assert "https://" not in page
        assert "http://" not in page


def test_identity_route_is_allowlisted(client_for):
    client = client_for("pm")
    assert client.get("/identity/build/noor-tokens.css").status_code == 200
    assert client.get("/identity/fonts/Tajawal-Regular.ttf").status_code == 200
    assert client.get("/identity/profile.json").status_code == 404


def test_labels_validation_fails_on_malformed_or_missing_shell_key(nmis_app, monkeypatch, tmp_path):
    import importlib.resources
    source = Path(__file__).resolve().parents[3] / "packages/noor_identity/noor_identity/labels.ar.json"
    original = json.loads(source.read_text(encoding="utf-8"))
    monkeypatch.setattr(importlib.resources, "files", lambda package: tmp_path if package == "noor_identity" else source.parent)
    for mutate, message in ((lambda doc: doc.update(schema="wrong"), "noor.labels/v1"),
                            (lambda doc: doc["entries"].pop("platform.radar"), "missing shell label keys")):
        doc = json.loads(json.dumps(original))
        mutate(doc)
        (tmp_path / "labels.ar.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(ValueError, match=message):
            create_app(nmis_app.config)
    (tmp_path / "labels.ar.json").write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="missing or malformed"):
        create_app(nmis_app.config)


def _png() -> bytes:
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff")) + chunk(b"IEND", b""))


def test_valid_logo_is_served_and_corrupt_logo_falls_back(nmis_app, monkeypatch):
    monkeypatch.setattr('noor_registry.sso.load_private_key',
                        lambda config: nmis_app.app.extensions['noor_registry']['signing_key'])
    root = nmis_app.config.identity_dir
    profile_path = root / "profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["logo"] = "synthetic-logo.png"
    profile_path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
    (root / profile["logo"]).write_bytes(_png())
    app = create_app(nmis_app.config)
    app.config['SERVER_NAME'] = 'noor.localhost:5310'
    client = app.test_client()
    page = client.get("/login").get_data(as_text=True)
    assert 'alt="' + profile["system_name"] + '"' in page
    response = client.get("/identity/synthetic-logo.png")
    assert response.status_code == 200 and response.mimetype == "image/png" and response.data == _png()
    assert client.get("/identity/profile.json").status_code == 404
    (root / profile["logo"]).write_bytes(b"corrupt")
    app = create_app(nmis_app.config)
    app.config['SERVER_NAME'] = 'noor.localhost:5310'
    client = app.test_client()
    assert profile["short_name"] in client.get("/login").get_data(as_text=True)
    assert client.get("/identity/synthetic-logo.png").status_code == 404


def test_new_text_files_have_no_previous_identity():
    root = Path(__file__).resolve().parents[3]
    paths = [
        root / "packages/noor_identity/noor_identity/labels.ar.json",
        root / "config/identity/noor/profile.json",
        root / "config/identity/noor/RIGHTS.md",
        root / "platforms/nmis/noor_registry/platforms.json",
        root / "platforms/nmis/noor_registry/platforms_registry.py",
        root / "platforms/nmis/noor_registry/views_shell.py",
        *sorted((root / "platforms/nmis/noor_registry/templates/shell").glob("*.html")),
    ]
    old_names = _previous_identity_names()
    for path in paths:
        content = path.read_text(encoding="utf-8").casefold()
        assert all(name.casefold() not in content for name in old_names), path
