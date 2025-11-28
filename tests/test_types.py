"""Tests for shared types module."""

from openwrt_imagegen.types import (
    ArtifactInfo,
    BuildDefaults,
    BuildStatus,
    FileSpec,
    FlashStatus,
    ImageBuilderState,
    OperationResult,
    ProfilePolicies,
    VerificationMode,
    VerificationResult,
)


class TestEnums:
    """Test enum definitions."""

    def test_build_status_values(self) -> None:
        """BuildStatus should have expected values."""
        assert BuildStatus.PENDING.value == "pending"
        assert BuildStatus.RUNNING.value == "running"
        assert BuildStatus.SUCCEEDED.value == "succeeded"
        assert BuildStatus.FAILED.value == "failed"

    def test_flash_status_values(self) -> None:
        """FlashStatus should have expected values."""
        assert FlashStatus.PENDING.value == "pending"
        assert FlashStatus.SUCCEEDED.value == "succeeded"
        assert FlashStatus.FAILED.value == "failed"

    def test_imagebuilder_state_values(self) -> None:
        """ImageBuilderState should have expected values."""
        assert ImageBuilderState.PENDING.value == "pending"
        assert ImageBuilderState.READY.value == "ready"
        assert ImageBuilderState.BROKEN.value == "broken"
        assert ImageBuilderState.DEPRECATED.value == "deprecated"

    def test_verification_mode_values(self) -> None:
        """VerificationMode should have expected values."""
        assert VerificationMode.FULL.value == "full-hash"
        assert VerificationMode.PREFIX_16M.value == "prefix-16MiB"
        assert VerificationMode.PREFIX_64M.value == "prefix-64MiB"
        assert VerificationMode.SKIP.value == "skipped"

    def test_verification_result_values(self) -> None:
        """VerificationResult should have expected values."""
        assert VerificationResult.MATCH.value == "match"
        assert VerificationResult.MISMATCH.value == "mismatch"
        assert VerificationResult.SKIPPED.value == "skipped"


class TestDataclasses:
    """Test dataclass definitions."""

    def test_operation_result_minimal(self) -> None:
        """OperationResult should work with minimal args."""
        result = OperationResult(success=True, message="OK")
        assert result.success is True
        assert result.message == "OK"
        assert result.code is None
        assert result.log_path is None
        assert result.details == {}

    def test_operation_result_full(self) -> None:
        """OperationResult should accept all fields."""
        result = OperationResult(
            success=False,
            message="Build failed",
            code="build_failed",
            log_path="/var/log/build.log",
            details={"exit_code": 1},
        )
        assert result.success is False
        assert result.code == "build_failed"
        assert result.log_path == "/var/log/build.log"
        assert result.details == {"exit_code": 1}

    def test_artifact_info_minimal(self) -> None:
        """ArtifactInfo should work with minimal args."""
        artifact = ArtifactInfo(
            filename="image.bin",
            relative_path="23.05/ath79/generic/image.bin",
            size_bytes=1024,
            sha256="abc123",
        )
        assert artifact.filename == "image.bin"
        assert artifact.size_bytes == 1024
        assert artifact.kind is None
        assert artifact.labels == []

    def test_artifact_info_full(self) -> None:
        """ArtifactInfo should accept all fields."""
        artifact = ArtifactInfo(
            filename="image.bin",
            relative_path="23.05/ath79/generic/image.bin",
            size_bytes=1024,
            sha256="abc123",
            kind="sysupgrade",
            labels=["for_tf_flash"],
        )
        assert artifact.kind == "sysupgrade"
        assert artifact.labels == ["for_tf_flash"]


class TestTypedDicts:
    """Test TypedDict definitions."""

    def test_file_spec(self) -> None:
        """FileSpec should work as a TypedDict."""
        spec: FileSpec = {
            "source": "profiles/files/banner",
            "destination": "/etc/banner",
            "mode": "0644",
            "owner": "root:root",
        }
        assert spec["source"] == "profiles/files/banner"
        assert spec["destination"] == "/etc/banner"

    def test_profile_policies(self) -> None:
        """ProfilePolicies should work as a TypedDict."""
        policies: ProfilePolicies = {
            "filesystem": "squashfs",
            "include_kernel_symbols": False,
            "strip_debug": True,
        }
        assert policies["filesystem"] == "squashfs"

    def test_build_defaults(self) -> None:
        """BuildDefaults should work as a TypedDict."""
        defaults: BuildDefaults = {
            "rebuild_if_cached": False,
            "initramfs": False,
        }
        assert defaults["rebuild_if_cached"] is False
