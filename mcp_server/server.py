"""MCP server implementation.

This module creates the FastMCP server and registers all tools.
Tools are thin wrappers around core openwrt_imagegen services.

Per docs/FRONTENDS.md:
- Tools must be idempotent where applicable
- Return structured errors with codes
- Support cache-aware semantics
"""

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field
from sqlalchemy import select

from mcp_server.errors import (
    INTERNAL_ERROR,
    artifact_not_found,
    build_not_found,
    flash_error,
    make_error,
    profile_not_found,
    validation_error,
)
from mcp_server.schemas import (
    ArtifactSummary,
    BuildBatchResponse,
    BuildBatchResultItem,
    BuildImageResponse,
    BuildSummary,
    FlashResponse,
    GetProfileResponse,
    ListArtifactsResponse,
    ListBuildsResponse,
    ListProfilesResponse,
    ProfileDetail,
    ProfileSummary,
)

# Create the FastMCP server instance
mcp = FastMCP(
    name="openwrt-imagegen",
)


def _get_session_factory() -> Any:
    """Get the database session factory.

    Returns:
        Session factory callable.
    """
    from openwrt_imagegen.db import create_all_tables, get_engine, get_session_factory

    engine = get_engine()
    create_all_tables(engine)
    return get_session_factory(engine)


@mcp.tool()
def list_profiles(
    device_id: Annotated[str | None, Field(description="Filter by device ID")] = None,
    release: Annotated[
        str | None, Field(description="Filter by OpenWrt release")
    ] = None,
    target: Annotated[str | None, Field(description="Filter by target")] = None,
    subtarget: Annotated[str | None, Field(description="Filter by subtarget")] = None,
    tags: Annotated[
        list[str] | None, Field(description="Filter by tags (must have all)")
    ] = None,
) -> ListProfilesResponse:
    """List profiles with optional filters.

    This tool queries the profile database and returns matching profiles.
    Use filters to narrow down results by device, release, target, or tags.

    Returns:
        ListProfilesResponse with list of profiles or error.
    """
    from openwrt_imagegen.profiles.service import list_profiles as svc_list_profiles
    from openwrt_imagegen.profiles.service import query_profiles

    try:
        factory = _get_session_factory()
        with factory() as session:
            # Use query if filters provided, otherwise list all
            if any([device_id, release, target, subtarget, tags]):
                profiles = query_profiles(
                    session,
                    device_id=device_id,
                    openwrt_release=release,
                    target=target,
                    subtarget=subtarget,
                    tags=tags,
                )
            else:
                profiles = svc_list_profiles(session)

            summaries = [
                ProfileSummary(
                    profile_id=p.profile_id,
                    name=p.name,
                    device_id=p.device_id,
                    openwrt_release=p.openwrt_release,
                    target=p.target,
                    subtarget=p.subtarget,
                    tags=p.tags,
                )
                for p in profiles
            ]

            return ListProfilesResponse(
                success=True,
                profiles=summaries,
                total=len(summaries),
            )

    except Exception as e:
        error = make_error(INTERNAL_ERROR, str(e))
        return ListProfilesResponse(
            success=False,
            profiles=[],
            total=0,
            error=error.to_dict(),
        )


@mcp.tool()
def get_profile(
    profile_id: Annotated[str, Field(description="Profile ID to retrieve")],
) -> GetProfileResponse:
    """Get detailed information about a specific profile.

    Args:
        profile_id: The unique profile identifier.

    Returns:
        GetProfileResponse with profile details or error.
    """
    from openwrt_imagegen.profiles.service import (
        ProfileNotFoundError,
        profile_to_schema,
    )
    from openwrt_imagegen.profiles.service import (
        get_profile as svc_get_profile,
    )

    try:
        factory = _get_session_factory()
        with factory() as session:
            try:
                profile = svc_get_profile(session, profile_id)
            except ProfileNotFoundError:
                return GetProfileResponse(
                    success=False,
                    error=profile_not_found(profile_id).to_dict(),
                )

            schema = profile_to_schema(profile, include_meta=True)

            detail = ProfileDetail(
                profile_id=schema.profile_id,
                name=schema.name,
                device_id=schema.device_id,
                openwrt_release=schema.openwrt_release,
                target=schema.target,
                subtarget=schema.subtarget,
                tags=schema.tags,
                description=schema.description,
                imagebuilder_profile=schema.imagebuilder_profile,
                packages=schema.packages,
                packages_remove=schema.packages_remove,
                overlay_dir=schema.overlay_dir,
                policies=schema.policies.model_dump() if schema.policies else None,
                build_defaults=schema.build_defaults.model_dump()
                if schema.build_defaults
                else None,
                disabled_services=schema.disabled_services,
                rootfs_partsize=schema.rootfs_partsize,
                notes=schema.notes,
                created_at=schema.meta.created_at if schema.meta else None,
                updated_at=schema.meta.updated_at if schema.meta else None,
            )

            return GetProfileResponse(success=True, profile=detail)

    except Exception as e:
        error = make_error(INTERNAL_ERROR, str(e))
        return GetProfileResponse(success=False, error=error.to_dict())


@mcp.tool()
def build_image(
    profile_id: Annotated[str, Field(description="Profile ID to build")],
    force_rebuild: Annotated[
        bool, Field(description="Force rebuild even if cached")
    ] = False,
    extra_packages: Annotated[
        list[str] | None, Field(description="Additional packages to include")
    ] = None,
) -> BuildImageResponse:
    """Build an image for a profile with cache-aware semantics.

    This tool implements build-or-reuse behavior:
    - By default, returns cached build if available (idempotent)
    - Use force_rebuild=True to force a new build

    The response indicates whether a cache hit occurred.

    Args:
        profile_id: Profile to build.
        force_rebuild: Skip cache and force new build.
        extra_packages: Additional packages at build time.

    Returns:
        BuildImageResponse with build status, artifacts, or error.
    """
    from openwrt_imagegen.builds.service import (
        BuildServiceError,
        build_or_reuse,
    )
    from openwrt_imagegen.config import get_settings
    from openwrt_imagegen.imagebuilder.service import ensure_builder
    from openwrt_imagegen.profiles.service import (
        ProfileNotFoundError,
        profile_to_schema,
    )
    from openwrt_imagegen.profiles.service import (
        get_profile as svc_get_profile,
    )

    try:
        factory = _get_session_factory()
        settings = get_settings()

        with factory() as session:
            # Get profile
            try:
                profile = svc_get_profile(session, profile_id)
            except ProfileNotFoundError:
                return BuildImageResponse(
                    success=False,
                    error=profile_not_found(profile_id).to_dict(),
                )

            profile_schema = profile_to_schema(profile)

            # Ensure Image Builder is available
            try:
                imagebuilder = ensure_builder(
                    session,
                    release=profile.openwrt_release,
                    target=profile.target,
                    subtarget=profile.subtarget,
                )
            except Exception as e:
                error = make_error("imagebuilder_error", str(e))
                return BuildImageResponse(success=False, error=error.to_dict())

            # Build or reuse
            try:
                build, is_cache_hit = build_or_reuse(
                    session=session,
                    profile=profile,
                    profile_schema=profile_schema,
                    imagebuilder=imagebuilder,
                    settings=settings,
                    force_rebuild=force_rebuild,
                    extra_packages=extra_packages,
                )
                session.commit()
            except BuildServiceError as e:
                error = make_error(e.code, str(e))
                return BuildImageResponse(success=False, error=error.to_dict())

            # Build artifacts list
            artifacts = [
                ArtifactSummary(
                    id=a.id,
                    filename=a.filename,
                    kind=a.kind,
                    size_bytes=a.size_bytes,
                    sha256=a.sha256,
                    relative_path=a.relative_path,
                )
                for a in build.artifacts
            ]

            return BuildImageResponse(
                success=build.is_succeeded(),
                build_id=build.id,
                cache_hit=is_cache_hit,
                status=build.status,
                artifacts=artifacts if build.is_succeeded() else None,
                log_path=build.log_path,
                error=make_error(
                    build.error_type or "build_failed",
                    build.error_message or "Build failed",
                ).to_dict()
                if not build.is_succeeded() and build.error_type
                else None,
            )

    except Exception as e:
        error = make_error(INTERNAL_ERROR, str(e))
        return BuildImageResponse(success=False, error=error.to_dict())


@mcp.tool()
def build_images_batch(
    profile_ids: Annotated[
        list[str] | None, Field(description="Explicit list of profile IDs to build")
    ] = None,
    device_id: Annotated[
        str | None, Field(description="Filter profiles by device ID")
    ] = None,
    release: Annotated[
        str | None, Field(description="Filter profiles by release")
    ] = None,
    target: Annotated[
        str | None, Field(description="Filter profiles by target")
    ] = None,
    subtarget: Annotated[
        str | None, Field(description="Filter profiles by subtarget")
    ] = None,
    tags: Annotated[
        list[str] | None, Field(description="Filter profiles by tags")
    ] = None,
    mode: Annotated[
        str, Field(description="Batch mode: fail-fast or best-effort")
    ] = "best-effort",
    force_rebuild: Annotated[
        bool, Field(description="Force rebuild even if cached")
    ] = False,
) -> BuildBatchResponse:
    """Build images for multiple profiles.

    Profiles can be selected by explicit IDs or filters.
    Supports fail-fast (stop on first failure) or best-effort (continue) modes.

    Per-profile results include cache_hit flag showing idempotent behavior.

    Args:
        profile_ids: Explicit profile IDs to build.
        device_id: Filter by device ID.
        release: Filter by release.
        target: Filter by target.
        subtarget: Filter by subtarget.
        tags: Filter by tags.
        mode: fail-fast or best-effort.
        force_rebuild: Force rebuild for all profiles.

    Returns:
        BuildBatchResponse with per-profile results or error.
    """
    from openwrt_imagegen.builds.service import (
        BatchBuildFilter,
        build_batch,
    )
    from openwrt_imagegen.config import get_settings
    from openwrt_imagegen.types import BatchMode

    # Validate mode
    try:
        batch_mode = BatchMode(mode)
    except ValueError:
        error = validation_error(
            f"Invalid mode: {mode}. Use 'fail-fast' or 'best-effort'"
        )
        return BuildBatchResponse(
            success=False,
            total=0,
            succeeded=0,
            failed=0,
            cache_hits=0,
            mode=mode,
            results=[],
            error=error.to_dict(),
        )

    # Require at least one filter
    if not any([profile_ids, device_id, release, target, subtarget, tags]):
        error = validation_error(
            "At least one filter must be specified (profile_ids, device_id, release, target, subtarget, or tags)"
        )
        return BuildBatchResponse(
            success=False,
            total=0,
            succeeded=0,
            failed=0,
            cache_hits=0,
            mode=mode,
            results=[],
            error=error.to_dict(),
        )

    try:
        factory = _get_session_factory()
        settings = get_settings()

        with factory() as session:
            filter_spec = BatchBuildFilter(
                profile_ids=profile_ids,
                device_id=device_id,
                openwrt_release=release,
                target=target,
                subtarget=subtarget,
                tags=tags,
            )

            result = build_batch(
                session=session,
                filter_spec=filter_spec,
                settings=settings,
                mode=batch_mode,
                force_rebuild=force_rebuild,
            )
            session.commit()

            # Convert results to response format
            items = [
                BuildBatchResultItem(
                    profile_id=r["profile_id"],
                    build_id=r.get("build_id"),
                    success=r["success"],
                    is_cache_hit=r.get("is_cache_hit", False),
                    artifacts=r.get("artifacts"),
                    error_code=r.get("error_code"),
                    error_message=r.get("error_message"),
                    log_path=r.get("log_path"),
                )
                for r in result.results
            ]

            return BuildBatchResponse(
                success=result.failed == 0,
                total=result.total,
                succeeded=result.succeeded,
                failed=result.failed,
                cache_hits=result.cache_hits,
                mode=result.mode,
                stopped_early=result.stopped_early,
                results=items,
            )

    except Exception as e:
        error = make_error(INTERNAL_ERROR, str(e))
        return BuildBatchResponse(
            success=False,
            total=0,
            succeeded=0,
            failed=0,
            cache_hits=0,
            mode=mode,
            results=[],
            error=error.to_dict(),
        )


@mcp.tool()
def list_builds(
    profile_id: Annotated[str | None, Field(description="Filter by profile ID")] = None,
    status: Annotated[
        str | None,
        Field(description="Filter by status: pending, running, succeeded, failed"),
    ] = None,
    limit: Annotated[int, Field(description="Maximum results to return")] = 100,
) -> ListBuildsResponse:
    """List build records with optional filters.

    Args:
        profile_id: Filter by profile ID.
        status: Filter by build status.
        limit: Maximum number of results.

    Returns:
        ListBuildsResponse with list of builds or error.
    """
    from openwrt_imagegen.builds.service import list_builds as svc_list_builds
    from openwrt_imagegen.profiles.service import (
        ProfileNotFoundError,
    )
    from openwrt_imagegen.profiles.service import (
        get_profile as svc_get_profile,
    )
    from openwrt_imagegen.types import BuildStatus

    # Validate status
    status_filter: BuildStatus | None = None
    if status:
        try:
            status_filter = BuildStatus(status)
        except ValueError:
            error = validation_error(
                f"Invalid status: {status}. Use pending, running, succeeded, or failed"
            )
            return ListBuildsResponse(
                success=False, builds=[], total=0, error=error.to_dict()
            )

    try:
        factory = _get_session_factory()
        with factory() as session:
            # Resolve profile_id to database ID if provided
            db_profile_id: int | None = None
            if profile_id:
                try:
                    profile = svc_get_profile(session, profile_id)
                    db_profile_id = profile.id
                except ProfileNotFoundError:
                    return ListBuildsResponse(
                        success=False,
                        builds=[],
                        total=0,
                        error=profile_not_found(profile_id).to_dict(),
                    )

            builds = svc_list_builds(
                session,
                profile_id=db_profile_id,
                status=status_filter,
                limit=limit,
            )

            summaries = [
                BuildSummary(
                    id=b.id,
                    profile_id=b.profile.profile_id if b.profile else None,
                    status=b.status,
                    cache_key=b.cache_key,
                    is_cache_hit=b.is_cache_hit,
                    requested_at=b.requested_at.isoformat() if b.requested_at else None,
                    started_at=b.started_at.isoformat() if b.started_at else None,
                    finished_at=b.finished_at.isoformat() if b.finished_at else None,
                    artifact_count=len(b.artifacts),
                    error_type=b.error_type,
                    error_message=b.error_message,
                    log_path=b.log_path,
                )
                for b in builds
            ]

            return ListBuildsResponse(
                success=True,
                builds=summaries,
                total=len(summaries),
            )

    except Exception as e:
        error = make_error(INTERNAL_ERROR, str(e))
        return ListBuildsResponse(
            success=False, builds=[], total=0, error=error.to_dict()
        )


@mcp.tool()
def list_artifacts(
    build_id: Annotated[int | None, Field(description="Filter by build ID")] = None,
    kind: Annotated[str | None, Field(description="Filter by artifact kind")] = None,
    limit: Annotated[int, Field(description="Maximum results to return")] = 100,
) -> ListArtifactsResponse:
    """List artifacts with optional filters.

    Args:
        build_id: Filter by build ID.
        kind: Filter by artifact kind.
        limit: Maximum number of results.

    Returns:
        ListArtifactsResponse with list of artifacts or error.
    """
    from openwrt_imagegen.builds.models import Artifact
    from openwrt_imagegen.builds.service import BuildNotFoundError, get_build

    try:
        factory = _get_session_factory()
        with factory() as session:
            # Validate build_id if provided
            if build_id is not None:
                try:
                    get_build(session, build_id)
                except BuildNotFoundError:
                    return ListArtifactsResponse(
                        success=False,
                        artifacts=[],
                        total=0,
                        error=build_not_found(build_id).to_dict(),
                    )

            stmt = select(Artifact)

            if build_id is not None:
                stmt = stmt.where(Artifact.build_id == build_id)
            if kind is not None:
                stmt = stmt.where(Artifact.kind == kind)

            stmt = stmt.order_by(Artifact.id.desc()).limit(limit)
            artifacts = list(session.execute(stmt).scalars().all())

            summaries = [
                ArtifactSummary(
                    id=a.id,
                    filename=a.filename,
                    kind=a.kind,
                    size_bytes=a.size_bytes,
                    sha256=a.sha256,
                    relative_path=a.relative_path,
                )
                for a in artifacts
            ]

            return ListArtifactsResponse(
                success=True,
                artifacts=summaries,
                total=len(summaries),
            )

    except Exception as e:
        error = make_error(INTERNAL_ERROR, str(e))
        return ListArtifactsResponse(
            success=False, artifacts=[], total=0, error=error.to_dict()
        )


@mcp.tool()
def flash_artifact(
    artifact_id: Annotated[int, Field(description="Artifact ID to flash")],
    device_path: Annotated[
        str, Field(description="Device path (e.g., /dev/sdX). Must be whole device.")
    ],
    dry_run: Annotated[bool, Field(description="Validate without writing")] = False,
    force: Annotated[
        bool, Field(description="Skip confirmation (required for actual writes)")
    ] = False,
    wipe_before: Annotated[
        bool, Field(description="Wipe device before writing")
    ] = False,
) -> FlashResponse:
    """Flash an artifact to a TF/SD card.

    Safety rules (per docs/SAFETY.md):
    - Only whole devices (e.g., /dev/sdX), never partitions
    - Device path must be explicitly provided
    - Requires force=True for actual writes (non-interactive use)
    - Hash verification after write

    Use dry_run=True to validate without writing.

    Args:
        artifact_id: Artifact to flash.
        device_path: Target block device path.
        dry_run: Validate without writing.
        force: Skip confirmation (required for writes).
        wipe_before: Wipe device before writing.

    Returns:
        FlashResponse with operation result or error.
    """
    from openwrt_imagegen.config import get_settings
    from openwrt_imagegen.flash.service import (
        ArtifactFileNotFoundError,
        ArtifactNotFoundError,
    )
    from openwrt_imagegen.flash.service import (
        flash_artifact as svc_flash_artifact,
    )

    # Require force flag for actual writes (safety)
    if not dry_run and not force:
        error = validation_error(
            "Flash requires force=True for actual writes. Use dry_run=True to validate first."
        )
        return FlashResponse(
            success=False,
            device_path=device_path,
            error=error.to_dict(),
        )

    try:
        factory = _get_session_factory()
        settings = get_settings()

        with factory() as session:
            try:
                result = svc_flash_artifact(
                    session,
                    artifact_id=artifact_id,
                    device_path=device_path,
                    settings=settings,
                    wipe_before=wipe_before,
                    dry_run=dry_run,
                    force=force,
                )

                if not dry_run:
                    session.commit()

            except ArtifactNotFoundError:
                return FlashResponse(
                    success=False,
                    device_path=device_path,
                    error=artifact_not_found(artifact_id).to_dict(),
                )
            except ArtifactFileNotFoundError as e:
                return FlashResponse(
                    success=False,
                    device_path=device_path,
                    error=flash_error(
                        f"Artifact file not found: {e.path}",
                        error_code="artifact_file_not_found",
                    ).to_dict(),
                )

            if result.success:
                return FlashResponse(
                    success=True,
                    flash_record_id=result.flash_record_id,
                    image_path=result.image_path,
                    device_path=result.device_path,
                    bytes_written=result.bytes_written,
                    source_hash=result.source_hash,
                    device_hash=result.device_hash,
                    verification_mode=result.verification_mode.value,
                    verification_result=result.verification_result.value,
                    message=result.message,
                )
            else:
                return FlashResponse(
                    success=False,
                    flash_record_id=result.flash_record_id,
                    image_path=result.image_path,
                    device_path=result.device_path,
                    bytes_written=result.bytes_written,
                    verification_mode=result.verification_mode.value,
                    verification_result=result.verification_result.value,
                    error=flash_error(
                        result.error_message or "Flash failed",
                        error_code=result.error_code,
                    ).to_dict(),
                )

    except Exception as e:
        error = make_error(INTERNAL_ERROR, str(e))
        return FlashResponse(
            success=False,
            device_path=device_path,
            error=error.to_dict(),
        )


__all__ = [
    "build_image",
    "build_images_batch",
    "flash_artifact",
    "get_profile",
    "list_artifacts",
    "list_builds",
    "list_profiles",
    "mcp",
]
