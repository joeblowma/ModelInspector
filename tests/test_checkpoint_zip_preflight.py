import io
from pathlib import Path
import struct
import sys
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from back import checkpoint_reader


def _archive(zip64: bool, prefix: bytes = b"") -> tuple[bytes, int, int, int]:
    comment = b"preflight comment"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.comment = comment
        archive.writestr("metadata.json", b'{"safe": true}')
    classic = buffer.getvalue()
    eocd = classic.rfind(zipfile.stringEndArchive)
    (_, _, _, entries_on_disk, entries_total, directory_size,
     directory_offset, comment_size) = struct.unpack_from(
        "<4s4H2LH", classic, eocd
    )
    comment = classic[eocd + 22 : eocd + 22 + comment_size]
    directory_end = len(prefix) + eocd
    classic_eocd = directory_end
    if not zip64:
        payload = prefix + classic
    else:
        zip64_end = struct.pack(
            "<4sQ2H2L4Q",
            zipfile.stringEndArchive64,
            44,
            45,
            45,
            0,
            0,
            entries_on_disk,
            entries_total,
            directory_size,
            directory_offset,
        )
        locator = struct.pack("<4sLQL", b"PK\x06\x07", 0, eocd, 1)
        end = struct.pack(
            "<4s4H2LH",
            zipfile.stringEndArchive,
            0,
            0,
            0xFFFF,
            0xFFFF,
            0xFFFFFFFF,
            0xFFFFFFFF,
            len(comment),
        )
        payload = prefix + classic[:eocd] + zip64_end + locator + end + comment
        classic_eocd += zipfile.sizeEndCentDir64 + zipfile.sizeEndCentDir64Locator
    assert len(prefix) + directory_offset + directory_size == directory_end
    return payload, classic_eocd, directory_end, directory_size


def _use_legacy_zip64_location(patch, classic_eocd, directory_size=None):
    end_reader = checkpoint_reader.zipfile._EndRecData

    def read_end_record(stream):
        end_record = end_reader(stream)
        if end_record and end_record[zipfile._ECD_SIGNATURE] == zipfile.stringEndArchive64:
            end_record[zipfile._ECD_LOCATION] = classic_eocd
            if directory_size is not None:
                end_record[zipfile._ECD_SIZE] = directory_size
        return end_record

    patch.setattr(checkpoint_reader.zipfile, "_EndRecData", read_end_record)


@pytest.mark.parametrize(
    ("zip64", "prefix"),
    [
        (False, b""),
        (False, b"SFX prefix"),
        (True, b""),
        (True, b"SFX prefix"),
    ],
    ids=("classic", "classic-sfx", "zip64", "zip64-sfx"),
)
def test_preflight_handles_nonempty_archives_and_legacy_zip64_location(
    monkeypatch, tmp_path, zip64, prefix
):
    payload, classic_eocd, directory_end, _ = _archive(zip64, prefix)
    path = tmp_path / "checkpoint.pt"
    path.write_bytes(payload)

    with monkeypatch.context() as patch:
        if zip64:
            _use_legacy_zip64_location(patch, classic_eocd)
        patch.setattr(
            checkpoint_reader.zipfile,
            "_handle_prepended_data",
            lambda *_args: pytest.fail("version-specific helper used"),
            raising=False,
        )
        checkpoint_reader._preflight_zip_directory(str(path), directory_end)

    metadata, tensors, _ = checkpoint_reader.read_checkpoint_header(
        str(path), checkpoint_safety="metadata"
    )
    assert metadata["checkpoint.metadata"] == {"safe": True}
    assert metadata["checkpoint.tensor_payloads_read"] is False
    assert tensors == {}


@pytest.mark.parametrize("failure", ("negative-position", "directory-budget"))
def test_legacy_zip64_position_and_budget_reject_before_zipfile(
    monkeypatch, tmp_path, failure
):
    payload, classic_eocd, directory_end, directory_size = _archive(
        True, b"SFX prefix"
    )
    path = tmp_path / "forged-zip64.pt"
    path.write_bytes(payload)
    bad_size = directory_end + 1 if failure == "negative-position" else None

    with monkeypatch.context() as patch:
        _use_legacy_zip64_location(patch, classic_eocd, bad_size)
        if failure == "directory-budget":
            patch.setattr(checkpoint_reader, "MAX_ARCHIVE_DIRECTORY_BYTES", 1)
        patch.setattr(
            checkpoint_reader.zipfile,
            "ZipFile",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("ZipFile constructed")
            ),
        )
        with pytest.raises(zipfile.BadZipFile, match="central directory exceeds"):
            checkpoint_reader._zip_metadata(str(path), len(payload))

    if failure == "directory-budget":
        assert directory_size > 1
