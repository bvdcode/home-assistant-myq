"""Deletion boundaries: only enrolled, unchanged clips can expire."""

import time
from pathlib import Path
from unittest.mock import patch

from homeassistant.core import HomeAssistant

from custom_components.myq.keypad_retention import KeypadRecordings


async def test_retention_preserves_existing_recent_and_replaced_files(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    recordings = KeypadRecordings(hass, "retention-test")
    recordings.root = tmp_path
    existing, expired, recent, replaced = [tmp_path / (c * 32 + ".mp4") for c in "abcd"]
    for path in (existing, expired, recent, replaced):
        path.write_bytes(b"video")
    now = time.time()
    with patch("custom_components.myq.keypad_retention.time.time", return_value=now - 31 * 86400):
        await recordings.async_add(str(expired))
        await recordings.async_add(str(replaced))
    await recordings.async_add(str(recent))
    replaced.write_bytes(b"replacement video must survive")
    # Reload proves ownership is durable; directory enumeration never enrolls old clips.
    restored = KeypadRecordings(hass, "retention-test")
    restored.root = tmp_path
    await restored.async_load()
    await restored.async_cleanup(0)
    assert expired.exists()
    await restored.async_cleanup(30)
    assert not expired.exists()
    assert existing.exists() and recent.exists() and replaced.exists()


async def test_retention_cannot_follow_symlink_or_parent_path(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    recordings = KeypadRecordings(hass, "retention-path-test")
    recordings.root = tmp_path / "recordings"
    recordings.root.mkdir()
    external = tmp_path / "outside.mp4"
    external.write_bytes(b"preserve")
    link = recordings.root / ("a" * 32 + ".mp4")
    link.symlink_to(external)
    expired = {"created_at": time.time() - 31 * 86400, "identity": {}}
    recordings._clips = {link.name: expired, "../outside.mp4": expired}
    await recordings.async_cleanup(30)
    assert external.read_bytes() == b"preserve"
    assert link.is_symlink()


async def test_failed_enrollment_does_not_mutate_ownership_ledger(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    import pytest
    from homeassistant.util.file import WriteError

    recordings = KeypadRecordings(hass, "retention-save-failure")
    recordings.root = tmp_path
    old, new = [tmp_path / (c * 32 + ".mp4") for c in "ab"]
    old.write_bytes(b"existing managed video")
    new.write_bytes(b"new video")
    await recordings.async_add(str(old))
    previous = dict(recordings._clips)
    with (
        patch.object(recordings._store, "_async_write_data", side_effect=WriteError("full")),
        pytest.raises(OSError),
    ):
        await recordings.async_add(str(new))
    assert recordings._clips == previous
    restored = KeypadRecordings(hass, "retention-save-failure")
    await restored.async_load()
    assert restored._clips == previous


async def test_last_retained_clip_is_durable_and_scoped_to_camera(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    store = KeypadRecordings(hass, "mixed-cameras")
    store.root = tmp_path
    paths = [tmp_path / (str(i) * 32 + ".mp4") for i in range(3)]
    for path, serial in zip(paths, ("first", "second", None), strict=True):
        path.write_bytes(b"video")
        await store.async_add(str(path), serial=serial)
    reloaded = KeypadRecordings(hass, "mixed-cameras")
    await reloaded.async_load()
    first, second = reloaded.latest("first"), reloaded.latest("second")
    assert first is not None and first[1] == paths[0].name
    assert second is not None and second[1] == paths[1].name
    assert reloaded.latest("third") is None


async def test_custom_media_directory_resolves_published_sensor_link(
    hass: HomeAssistant, tmp_path: Path
) -> None:
    from unittest.mock import MagicMock

    from homeassistant.components.media_source.local_source import LocalSource
    from homeassistant.components.media_source.models import MediaSourceItem

    from custom_components.myq.models import MyQCamera
    from custom_components.myq.sensor import LastRecordingSensor

    hass.config.media_dirs = {"videos": str(tmp_path)}
    store = KeypadRecordings(hass, "custom-directory")
    assert store.root == tmp_path / "myq-keypad"
    store.root.mkdir()
    clip = store.root / ("a" * 32 + ".mp4")
    clip.write_bytes(b"video")
    camera = MyQCamera("TC-0007-20000001", True, "vkp-camera")
    await store.async_add(str(clip), serial=camera.serial_number)
    sensor = LastRecordingSensor(MagicMock(recordings=store), camera, "last_recording")
    attrs = sensor.extra_state_attributes
    assert attrs is not None
    source = LocalSource(hass, "media_source", "Library", hass.config.media_dirs, "/media")
    item = MediaSourceItem(
        hass,
        "media_source",
        attrs["media_content_id"].removeprefix("media-source://media_source/"),
        None,
    )
    assert (await source.async_resolve_media(item)).path == clip
