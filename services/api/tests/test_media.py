from pathlib import Path

import pytest

from framebounty.media import InvalidMedia, LocalStorage, validate_container_header, validate_probe


def probe(**overrides):
    video = {"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720, "avg_frame_rate": "30/1"}
    video.update(overrides)
    return {"streams": [video], "format": {"duration": "15.123"}}


@pytest.mark.parametrize("key", ["../../secret.video", "/tmp/file.video", "C:\\file.video", "a" * 32 + ".exe", "a" * 31 + ".video"])
def test_storage_rejects_unsafe_keys(tmp_path, key):
    with pytest.raises(InvalidMedia):
        LocalStorage(tmp_path).path(key)


def test_hash_is_content_based_and_private_keys_are_generated(tmp_path):
    storage = LocalStorage(tmp_path)
    key = "a" * 32 + ".video"
    storage.path(key).write_bytes(b"same lawful synthetic fixture")
    assert len(storage.sha256(key)) == 64
    assert storage.path(key).parent == Path(tmp_path).resolve()


@pytest.mark.parametrize("content", [b"", b"<html>video/mp4</html>", b"\x89PNG\r\n\x1a\n"])
def test_claimed_mime_is_not_content_validation(content):
    with pytest.raises(InvalidMedia):
        validate_container_header(content)


@pytest.mark.parametrize("field,value", [("width", 100000), ("height", 1), ("codec_name", "unsupported"), ("avg_frame_rate", "1000/1"), ("avg_frame_rate", "1/0")])
def test_probe_rejects_decoder_risks(field, value):
    with pytest.raises(InvalidMedia):
        validate_probe(probe(**{field: value}))


@pytest.mark.parametrize("duration", ["NaN", "Infinity", "9.999", "30.001", "malformed"])
def test_duration_must_be_bounded(duration):
    payload = probe()
    payload["format"]["duration"] = duration
    with pytest.raises(InvalidMedia):
        validate_probe(payload)


def test_metadata_is_not_task_completion():
    result = validate_probe(probe())
    assert result.duration_ms == 15123
    assert not hasattr(result, "task_completed")


@pytest.mark.parametrize("payload", [{}, {"streams": []}, {"streams": [None]}, {"streams": None}])
def test_malformed_probe_fails_safely(payload):
    with pytest.raises(InvalidMedia):
        validate_probe(payload)
