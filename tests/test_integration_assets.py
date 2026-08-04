import configparser
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_linux_mime_definition_has_magic_and_canonical_extension():
    root = ET.parse(ROOT / "integrations/linux/wimf.xml").getroot()
    namespace = {"mime": "http://www.freedesktop.org/standards/shared-mime-info"}
    mime = root.find("mime:mime-type", namespace)
    assert mime is not None and mime.attrib["type"] == "image/x-wimf"
    assert {item.attrib["value"] for item in mime.findall("mime:magic/mime:match", namespace)} >= {
        "WIM2",
        "WIMF",
    }
    assert any(item.attrib["pattern"] == "*.wimf" for item in mime.findall("mime:glob", namespace))


def test_linux_desktop_and_thumbnail_entries_are_well_formed():
    for relative, section in (
        ("integrations/linux/wimf.thumbnailer", "Thumbnailer Entry"),
        ("integrations/linux/wimf-studio.desktop", "Desktop Entry"),
    ):
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(ROOT / relative, encoding="utf-8")
        assert section in parser
        assert "image/x-wimf;" in parser[section]["MimeType"]


def test_upstream_adapters_use_only_the_public_wimf_boundary():
    for relative in ("integrations/imagemagick/wimf.c", "integrations/ffmpeg/wimfdec.c"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert '#include "wimf_c.h"' in source
        assert "v2_core" not in source


def test_windows_shell_provider_has_stable_com_exports():
    source = (ROOT / "integrations/windows/wimf_thumbnail.cpp").read_text(encoding="utf-8")
    exports = (ROOT / "integrations/windows/wimf-thumbnail.def").read_text(encoding="utf-8")
    assert "#define NOMINMAX" in source
    assert "STDAPI DllGetClassObject" in source
    assert "STDAPI DllCanUnloadNow" in source
    assert "DllGetClassObject PRIVATE" in exports
    assert "DllCanUnloadNow PRIVATE" in exports
