"""Tests for builds/artifacts.py module.

Tests artifact discovery, classification, and manifest generation.
"""

import json

from openwrt_imagegen.builds.artifacts import (
    classify_artifact,
    compute_file_hash,
    discover_artifacts,
    generate_manifest,
    get_primary_artifact,
    write_manifest,
)
from openwrt_imagegen.types import ArtifactInfo


class TestClassifyArtifact:
    """Tests for classify_artifact function."""

    def test_sysupgrade_bin(self):
        """Should classify sysupgrade.bin as sysupgrade."""
        assert (
            classify_artifact("openwrt-23.05.3-ath79-generic-sysupgrade.bin")
            == "sysupgrade"
        )
        assert classify_artifact("image-sysupgrade.bin") == "sysupgrade"

    def test_sysupgrade_img_gz(self):
        """Should classify sysupgrade.img.gz as sysupgrade."""
        assert classify_artifact("openwrt-sysupgrade.img.gz") == "sysupgrade"

    def test_factory_bin(self):
        """Should classify factory.bin as factory."""
        assert classify_artifact("openwrt-factory.bin") == "factory"
        assert classify_artifact("image-factory.img") == "factory"

    def test_kernel(self):
        """Should classify kernel images."""
        # Note: -kernel.bin is in FACTORY_PATTERNS for backwards compatibility
        # since it's often bundled with factory images
        assert classify_artifact("openwrt-kernel.bin") == "factory"
        assert (
            classify_artifact("image-uImage") == "kernel"
        )  # -uimage pattern (case insensitive)
        assert classify_artifact("image-vmlinux") == "kernel"  # -vmlinux pattern

    def test_rootfs(self):
        """Should classify rootfs images."""
        assert classify_artifact("openwrt-rootfs.tar.gz") == "rootfs"  # -rootfs.tar.gz
        assert classify_artifact("openwrt-rootfs.squashfs") == "rootfs"
        assert classify_artifact("openwrt-rootfs.ext4") == "rootfs"

    def test_manifest(self):
        """Should classify manifest files."""
        assert classify_artifact("openwrt.manifest") == "manifest"
        assert classify_artifact("packages.manifest") == "manifest"

    def test_initramfs(self):
        """Should classify initramfs images."""
        # Initramfs is checked before factory so -initramfs-kernel.bin is correctly classified
        assert classify_artifact("openwrt-initramfs-kernel.bin") == "initramfs"
        assert classify_artifact("image-initramfs.bin") == "initramfs"

    def test_other(self):
        """Should classify unknown files as other."""
        assert classify_artifact("random.bin") == "other"
        assert classify_artifact("unknown.img") == "other"
        assert classify_artifact("test.txt") == "other"

    def test_case_insensitive(self):
        """Should be case insensitive."""
        assert classify_artifact("IMAGE-SYSUPGRADE.BIN") == "sysupgrade"
        assert classify_artifact("Openwrt-Factory.Bin") == "factory"


class TestComputeFileHash:
    """Tests for compute_file_hash function."""

    def test_computes_sha256(self, tmp_path):
        """Should compute correct SHA-256 hash."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("test content")

        # Known SHA-256 of "test content"
        import hashlib

        expected = hashlib.sha256(b"test content").hexdigest()

        assert compute_file_hash(file_path) == expected

    def test_binary_file(self, tmp_path):
        """Should handle binary files."""
        file_path = tmp_path / "test.bin"
        file_path.write_bytes(b"\x00\x01\x02\x03\x04")

        result = compute_file_hash(file_path)
        assert len(result) == 64  # SHA-256 hex length

    def test_large_file(self, tmp_path):
        """Should handle files larger than chunk size."""
        file_path = tmp_path / "large.bin"
        # Write 1MB of data
        file_path.write_bytes(b"x" * (1024 * 1024))

        result = compute_file_hash(file_path)
        assert len(result) == 64


class TestDiscoverArtifacts:
    """Tests for discover_artifacts function."""

    def test_empty_directory(self, tmp_path):
        """Should return empty list for empty directory."""
        result = discover_artifacts(tmp_path)
        assert result == []

    def test_nonexistent_directory(self, tmp_path):
        """Should return empty list for nonexistent directory."""
        result = discover_artifacts(tmp_path / "nonexistent")
        assert result == []

    def test_discovers_bin_files(self, tmp_path):
        """Should discover .bin files."""
        (tmp_path / "sysupgrade.bin").write_bytes(b"x" * 10000)
        (tmp_path / "factory.bin").write_bytes(b"y" * 10000)

        result = discover_artifacts(tmp_path)

        assert len(result) == 2
        filenames = [a.filename for a in result]
        assert "sysupgrade.bin" in filenames
        assert "factory.bin" in filenames

    def test_discovers_img_gz_files(self, tmp_path):
        """Should discover .img.gz files."""
        (tmp_path / "image-sysupgrade.img.gz").write_bytes(b"x" * 10000)

        result = discover_artifacts(tmp_path)

        assert len(result) == 1
        assert result[0].filename == "image-sysupgrade.img.gz"

    def test_skips_small_files(self, tmp_path):
        """Should skip files smaller than threshold."""
        (tmp_path / "small.bin").write_bytes(b"x" * 100)  # Too small

        result = discover_artifacts(tmp_path)
        assert len(result) == 0

    def test_nested_discovery(self, tmp_path):
        """Should discover files in nested directories."""
        (tmp_path / "targets" / "ath79" / "generic").mkdir(parents=True)
        (tmp_path / "targets" / "ath79" / "generic" / "image.bin").write_bytes(
            b"x" * 10000
        )

        result = discover_artifacts(tmp_path)

        assert len(result) == 1
        assert "targets" in result[0].relative_path

    def test_includes_artifact_info(self, tmp_path):
        """Should include all artifact info fields."""
        (tmp_path / "openwrt-sysupgrade.bin").write_bytes(b"x" * 10000)

        result = discover_artifacts(tmp_path)

        assert len(result) == 1
        artifact = result[0]
        assert isinstance(artifact, ArtifactInfo)
        assert artifact.filename == "openwrt-sysupgrade.bin"
        assert artifact.size_bytes == 10000
        assert len(artifact.sha256) == 64
        assert artifact.kind == "sysupgrade"

    def test_adds_labels_for_sysupgrade(self, tmp_path):
        """Should add 'for_tf_flash' label to sysupgrade."""
        (tmp_path / "openwrt-sysupgrade.bin").write_bytes(b"x" * 10000)

        result = discover_artifacts(tmp_path)

        assert "for_tf_flash" in result[0].labels

    def test_adds_labels_for_factory(self, tmp_path):
        """Should add 'for_factory_install' label to factory."""
        (tmp_path / "openwrt-factory.bin").write_bytes(b"x" * 10000)

        result = discover_artifacts(tmp_path)

        assert "for_factory_install" in result[0].labels

    def test_include_non_binary(self, tmp_path):
        """Should include manifest when include_non_binary=True."""
        (tmp_path / "openwrt.manifest").write_text("package list")

        result = discover_artifacts(tmp_path, include_non_binary=False)
        assert len(result) == 0

        result = discover_artifacts(tmp_path, include_non_binary=True)
        assert len(result) == 1
        assert result[0].kind == "manifest"


class TestGenerateManifest:
    """Tests for generate_manifest function."""

    def test_minimal_manifest(self):
        """Should generate minimal manifest."""
        artifacts = [
            ArtifactInfo(
                filename="test.bin",
                relative_path="test.bin",
                size_bytes=1000,
                sha256="a" * 64,
                kind="sysupgrade",
            )
        ]

        manifest = generate_manifest(artifacts)

        assert manifest["version"] == "1.0"
        assert "generated_at" in manifest
        assert len(manifest["artifacts"]) == 1
        assert manifest["summary"]["total_artifacts"] == 1

    def test_with_build_metadata(self):
        """Should include build metadata when provided."""
        artifacts = []

        manifest = generate_manifest(
            artifacts,
            build_id=123,
            cache_key="sha256:abc123",
            profile_id="test.profile",
        )

        assert manifest["build_id"] == 123
        assert manifest["cache_key"] == "sha256:abc123"
        assert manifest["profile_id"] == "test.profile"

    def test_with_build_inputs(self):
        """Should include build inputs when provided."""
        manifest = generate_manifest(
            [],
            build_inputs={"profile_id": "test", "packages": ["luci"]},
        )

        assert manifest["build_inputs"]["profile_id"] == "test"

    def test_with_extra_metadata(self):
        """Should include extra metadata when provided."""
        manifest = generate_manifest(
            [],
            extra_metadata={"custom": "value"},
        )

        assert manifest["metadata"]["custom"] == "value"

    def test_summary_statistics(self):
        """Should compute summary statistics."""
        artifacts = [
            ArtifactInfo(
                filename="a.bin",
                relative_path="a.bin",
                size_bytes=1000,
                sha256="a" * 64,
                kind="sysupgrade",
            ),
            ArtifactInfo(
                filename="b.bin",
                relative_path="b.bin",
                size_bytes=2000,
                sha256="b" * 64,
                kind="factory",
            ),
        ]

        manifest = generate_manifest(artifacts)

        assert manifest["summary"]["total_artifacts"] == 2
        assert manifest["summary"]["total_size_bytes"] == 3000
        assert "sysupgrade" in manifest["summary"]["kinds"]
        assert "factory" in manifest["summary"]["kinds"]


class TestWriteManifest:
    """Tests for write_manifest function."""

    def test_writes_json(self, tmp_path):
        """Should write valid JSON file."""
        manifest = {"version": "1.0", "artifacts": []}
        output_path = tmp_path / "manifest.json"

        result = write_manifest(manifest, output_path)

        assert result == output_path
        assert output_path.exists()

        with open(output_path) as f:
            loaded = json.load(f)
        assert loaded["version"] == "1.0"

    def test_creates_parent_directories(self, tmp_path):
        """Should create parent directories."""
        manifest = {"version": "1.0"}
        output_path = tmp_path / "deep" / "nested" / "manifest.json"

        write_manifest(manifest, output_path)

        assert output_path.exists()


class TestGetPrimaryArtifact:
    """Tests for get_primary_artifact function."""

    def test_prefers_sysupgrade(self):
        """Should prefer sysupgrade over other types."""
        artifacts = [
            ArtifactInfo(
                filename="factory.bin",
                relative_path="factory.bin",
                size_bytes=1000,
                sha256="a" * 64,
                kind="factory",
            ),
            ArtifactInfo(
                filename="sysupgrade.bin",
                relative_path="sysupgrade.bin",
                size_bytes=1000,
                sha256="b" * 64,
                kind="sysupgrade",
            ),
        ]

        result = get_primary_artifact(artifacts)
        assert result is not None
        assert result.kind == "sysupgrade"

    def test_falls_back_to_factory(self):
        """Should fall back to factory if no sysupgrade."""
        artifacts = [
            ArtifactInfo(
                filename="factory.bin",
                relative_path="factory.bin",
                size_bytes=1000,
                sha256="a" * 64,
                kind="factory",
            ),
            ArtifactInfo(
                filename="other.bin",
                relative_path="other.bin",
                size_bytes=1000,
                sha256="b" * 64,
                kind="other",
            ),
        ]

        result = get_primary_artifact(artifacts)
        assert result is not None
        assert result.kind == "factory"

    def test_falls_back_to_any_binary(self):
        """Should fall back to any non-manifest binary."""
        artifacts = [
            ArtifactInfo(
                filename="manifest",
                relative_path="manifest",
                size_bytes=100,
                sha256="a" * 64,
                kind="manifest",
            ),
            ArtifactInfo(
                filename="kernel.bin",
                relative_path="kernel.bin",
                size_bytes=1000,
                sha256="b" * 64,
                kind="kernel",
            ),
        ]

        result = get_primary_artifact(artifacts)
        assert result is not None
        assert result.kind == "kernel"

    def test_returns_none_for_empty(self):
        """Should return None for empty list."""
        assert get_primary_artifact([]) is None

    def test_returns_none_for_only_manifests(self):
        """Should return None if only manifests."""
        artifacts = [
            ArtifactInfo(
                filename="manifest",
                relative_path="manifest",
                size_bytes=100,
                sha256="a" * 64,
                kind="manifest",
            ),
        ]

        assert get_primary_artifact(artifacts) is None
