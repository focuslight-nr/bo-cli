from pathlib import Path
from types import SimpleNamespace
import pytest
from mutagen.mp4 import MP4Cover
import gui_server


# --- extract_art tests ---

def test_extract_art_mutagen_returns_none(monkeypatch):
    monkeypatch.setattr("mutagen.File", lambda path: None)
    assert gui_server.extract_art(Path("/x/y.flac")) is None


def test_extract_art_flac_picture(monkeypatch):
    stub = SimpleNamespace(
        pictures=[SimpleNamespace(data=b"IMG", mime="image/png")],
        tags=None
    )
    monkeypatch.setattr("mutagen.File", lambda path: stub)
    assert gui_server.extract_art(Path("/x/y.flac")) == (b"IMG", "image/png")


def test_extract_art_flac_mime_none_fallback(monkeypatch):
    stub = SimpleNamespace(
        pictures=[SimpleNamespace(data=b"IMG", mime=None)],
        tags=None
    )
    monkeypatch.setattr("mutagen.File", lambda path: stub)
    assert gui_server.extract_art(Path("/x/y.flac")) == (b"IMG", "image/jpeg")


def test_extract_art_flac_empty_pictures_no_tags(monkeypatch):
    stub = SimpleNamespace(pictures=[], tags=None)
    monkeypatch.setattr("mutagen.File", lambda path: stub)
    assert gui_server.extract_art(Path("/x/y.flac")) is None


def test_extract_art_id3_apic(monkeypatch):
    stub = SimpleNamespace(
        tags={"APIC:cover": SimpleNamespace(data=b"IMG", mime="image/jpeg")}
    )
    monkeypatch.setattr("mutagen.File", lambda path: stub)
    assert gui_server.extract_art(Path("/x/y.mp3")) == (b"IMG", "image/jpeg")


def test_extract_art_id3_apic_mime_none_fallback(monkeypatch):
    stub = SimpleNamespace(
        tags={"APIC:cover": SimpleNamespace(data=b"IMG", mime=None)}
    )
    monkeypatch.setattr("mutagen.File", lambda path: stub)
    assert gui_server.extract_art(Path("/x/y.mp3")) == (b"IMG", "image/jpeg")


def test_extract_art_id3_no_apic_no_covr(monkeypatch):
    stub = SimpleNamespace(tags={"TIT2": SimpleNamespace(data=b"title", mime=None)})
    monkeypatch.setattr("mutagen.File", lambda path: stub)
    assert gui_server.extract_art(Path("/x/y.mp3")) is None


def test_extract_art_mp4_png_cover(monkeypatch):
    covr_obj = MP4Cover(b"IMG", imageformat=MP4Cover.FORMAT_PNG)
    stub = SimpleNamespace(tags={"covr": [covr_obj]})
    monkeypatch.setattr("mutagen.File", lambda path: stub)
    assert gui_server.extract_art(Path("/x/y.m4a")) == (b"IMG", "image/png")


def test_extract_art_mp4_jpeg_cover(monkeypatch):
    covr_obj = MP4Cover(b"IMG", imageformat=MP4Cover.FORMAT_JPEG)
    stub = SimpleNamespace(tags={"covr": [covr_obj]})
    monkeypatch.setattr("mutagen.File", lambda path: stub)
    assert gui_server.extract_art(Path("/x/y.m4a")) == (b"IMG", "image/jpeg")


def test_extract_art_mutagen_raises_exception(monkeypatch):
    def fake_loader(path):
        raise RuntimeError("bad file")
    monkeypatch.setattr("mutagen.File", fake_loader)
    assert gui_server.extract_art(Path("/x/y.flac")) is None


def test_extract_art_tags_empty_dict(monkeypatch):
    stub = SimpleNamespace(tags={})
    monkeypatch.setattr("mutagen.File", lambda path: stub)
    assert gui_server.extract_art(Path("/x/y.mp3")) is None


def test_extract_art_pictures_win_over_tags(monkeypatch):
    pic_stub = SimpleNamespace(data=b"PIC", mime="image/png")
    apic_stub = SimpleNamespace(data=b"APIC", mime="image/jpeg")
    stub = SimpleNamespace(
        pictures=[pic_stub],
        tags={"APIC:cover": apic_stub}
    )
    monkeypatch.setattr("mutagen.File", lambda path: stub)
    assert gui_server.extract_art(Path("/x/y.flac")) == (b"PIC", "image/png")


# --- probe_duration tests ---

def fake_proc(stdout: bytes):
    class Proc:
        async def communicate(self):
            return stdout, b""
    async def create(*args, **kwargs):
        return Proc()
    return create


async def test_probe_duration_valid(monkeypatch):
    monkeypatch.setattr(
        gui_server.asyncio,
        "create_subprocess_exec",
        fake_proc(b"estimated duration: 123.456789 sec\n")
    )
    result = await gui_server.probe_duration(Path("/x/y.mp3"))
    assert result == 123
    assert isinstance(result, int)


async def test_probe_duration_zero_point_four(monkeypatch):
    monkeypatch.setattr(
        gui_server.asyncio,
        "create_subprocess_exec",
        fake_proc(b"estimated duration: 0.4 sec\n")
    )
    result = await gui_server.probe_duration(Path("/x/y.mp3"))
    assert result == 0


async def test_probe_duration_multiple_lines(monkeypatch):
    stdout = b"File: x\nother line\nestimated duration: 45.9 sec\n"
    monkeypatch.setattr(
        gui_server.asyncio,
        "create_subprocess_exec",
        fake_proc(stdout)
    )
    result = await gui_server.probe_duration(Path("/x/y.mp3"))
    assert result == 45


async def test_probe_duration_no_line(monkeypatch):
    monkeypatch.setattr(
        gui_server.asyncio,
        "create_subprocess_exec",
        fake_proc(b"File: x\nother line\n")
    )
    result = await gui_server.probe_duration(Path("/x/y.mp3"))
    assert result is None


async def test_probe_duration_invalid_number(monkeypatch):
    monkeypatch.setattr(
        gui_server.asyncio,
        "create_subprocess_exec",
        fake_proc(b"estimated duration: notanumber sec\n")
    )
    result = await gui_server.probe_duration(Path("/x/y.mp3"))
    assert result is None


async def test_probe_duration_missing_value(monkeypatch):
    monkeypatch.setattr(
        gui_server.asyncio,
        "create_subprocess_exec",
        fake_proc(b"estimated duration:\n")
    )
    result = await gui_server.probe_duration(Path("/x/y.mp3"))
    assert result is None


async def test_probe_duration_file_not_found(monkeypatch):
    async def raise_err(*args, **kwargs):
        raise FileNotFoundError("afinfo not found")
    monkeypatch.setattr(
        gui_server.asyncio,
        "create_subprocess_exec",
        raise_err
    )
    result = await gui_server.probe_duration(Path("/x/y.mp3"))
    assert result is None


async def test_probe_duration_invalid_utf8(monkeypatch):
    stdout = b"\xff\xfe estimated duration: 12.0 sec"
    monkeypatch.setattr(
        gui_server.asyncio,
        "create_subprocess_exec",
        fake_proc(stdout)
    )
    result = await gui_server.probe_duration(Path("/x/y.mp3"))
    assert result == 12


# ---- 実物の afinfo に対する検証(macOS限定) ----


@pytest.mark.macos
async def test_probe_duration_against_real_afinfo(tmp_path):
    """stdlibで作った2秒のWAVを実際のafinfoに読ませる。"""
    import array
    import math
    import shutil
    import wave

    if shutil.which("afinfo") is None:
        pytest.skip("afinfo が無い")

    path = tmp_path / "tone.wav"
    rate, seconds = 8000, 2
    samples = array.array(
        "h", (int(16000 * math.sin(i * 0.05)) for i in range(rate * seconds))
    )
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.tobytes())

    assert await gui_server.probe_duration(path) == seconds


@pytest.mark.macos
async def test_probe_duration_on_a_non_audio_file(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("これは音声ファイルではない")
    assert await gui_server.probe_duration(path) is None
