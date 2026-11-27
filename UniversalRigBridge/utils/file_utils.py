"""Filesystem helpers for atomic, deterministic package output."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from datetime import datetime, timezone


def ensure_directory(path):
    os.makedirs(path, exist_ok=True)
    return path


def json_bytes(payload):
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False).encode("utf-8")


def write_json(path, payload):
    ensure_directory(os.path.dirname(path))
    with open(path, "wb") as handle:
        handle.write(json_bytes(payload))
        handle.write(b"\n")
    return path


def atomic_write(path, data):
    ensure_directory(os.path.dirname(path))
    directory = os.path.dirname(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".urb-", dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return path


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def zip_directory(source, destination, exclude_suffixes=(".urb",)):
    """Zip a directory with stable paths and no timestamp noise where possible."""
    ensure_directory(os.path.dirname(destination))
    entries = []
    for root, _dirs, files in os.walk(source):
        for filename in files:
            full = os.path.join(root, filename)
            if filename.endswith(exclude_suffixes):
                continue
            relative = os.path.relpath(full, source).replace(os.sep, "/")
            entries.append((relative, full))
    entries.sort(key=lambda item: item[0])
    descriptor, temporary = tempfile.mkstemp(prefix=".urb-package-", suffix=".urb", dir=os.path.dirname(destination))
    os.close(descriptor)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for relative, full in entries:
                info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                with open(full, "rb") as handle:
                    archive.writestr(info, handle.read())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return destination


def read_urb_manifest(package_path):
    with zipfile.ZipFile(package_path, "r") as archive:
        with archive.open("manifest.json") as handle:
            return json.loads(handle.read().decode("utf-8"))
