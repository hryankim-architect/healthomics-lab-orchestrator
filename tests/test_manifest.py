"""Validate the data manifest's structure.

The manifest is the contract for `make data`: it lists the public RNA-seq
samples, the chr22 reference, and the SHA-256 checksums that make the demo
byte-reproducible. These tests catch manifest drift (a malformed checksum, a
sample missing its condition) before it breaks a fresh clone's `make data`.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

MANIFEST = Path(__file__).resolve().parents[1] / "data" / "manifest.yaml"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _load() -> dict:
    with MANIFEST.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def test_manifest_exists_and_parses() -> None:
    assert MANIFEST.exists(), f"manifest missing at {MANIFEST}"
    data = _load()
    assert isinstance(data, dict) and data, "manifest did not parse to a non-empty mapping"


def test_samples_have_id_and_condition() -> None:
    data = _load()
    samples = data.get("samples", [])
    assert len(samples) >= 1, "expected at least one sample"
    for s in samples:
        assert s.get("id"), f"sample missing id: {s}"
        assert s.get("condition"), f"sample missing condition: {s}"


def test_reference_declares_fasta_url() -> None:
    ref = _load().get("reference", {})
    assert ref.get("fasta_url", "").startswith("http"), "reference fasta_url must be a URL"


def test_checksums_are_valid_sha256() -> None:
    checksums = _load().get("checksums", [])
    assert len(checksums) >= 1, "expected at least one checksum entry"
    for c in checksums:
        assert c.get("path"), f"checksum entry missing path: {c}"
        digest = str(c.get("sha256", ""))
        assert SHA256_RE.match(digest), f"not a 64-hex sha256 for {c.get('path')}: {digest!r}"
