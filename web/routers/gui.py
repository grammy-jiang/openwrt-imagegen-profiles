"""Web GUI router for server-rendered HTML pages.

This module provides the /ui routes for the web GUI, using Jinja2 templates
for server-side rendering. It calls service modules directly (not HTTP APIs)
per docs/FRONTENDS.md guidance.

All routes call the underlying service modules directly using FastAPI's
dependency injection, following the same patterns as the JSON API routers.
"""

from __future__ import annotations

import contextlib
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi import status as http_status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from openwrt_imagegen import __version__
from openwrt_imagegen.builds.models import BuildRecord
from openwrt_imagegen.builds.service import (
    BuildNotFoundError,
    get_build,
    list_builds,
)
from openwrt_imagegen.config import Settings, get_settings
from openwrt_imagegen.flash.models import FlashRecord
from openwrt_imagegen.flash.service import (
    ArtifactFileNotFoundError,
    ArtifactNotFoundError,
    flash_artifact,
    get_artifact,
    get_flash_records,
)
from openwrt_imagegen.profiles.models import Profile
from openwrt_imagegen.profiles.service import (
    ProfileNotFoundError,
    get_profile,
    list_profiles,
    profile_to_schema,
    query_profiles,
)
from openwrt_imagegen.types import BuildStatus, FlashStatus
from web.deps import get_db

router = APIRouter()

# Templates are configured relative to the web directory
templates = Jinja2Templates(directory="web/templates")


def get_settings_dep() -> Settings:
    """Get application settings.

    Returns:
        Settings instance.
    """
    return get_settings()


# Type aliases for dependencies
DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]


# Dashboard


@router.get("/", response_class=HTMLResponse, name="gui_dashboard")
def dashboard(
    request: Request,
    db: DbSession,
    settings: AppSettings,
) -> HTMLResponse:
    """Render the dashboard page.

    Shows system status, quick links, and summary counts.
    """
    # Get counts
    profile_count = db.execute(select(func.count(Profile.id))).scalar() or 0
    build_count = db.execute(select(func.count(BuildRecord.id))).scalar() or 0
    flash_count = db.execute(select(func.count(FlashRecord.id))).scalar() or 0

    # Build config dict for template
    config = {
        "cache_dir": str(settings.cache_dir),
        "artifacts_dir": str(settings.artifacts_dir),
        "db_url": settings.db_url,
        "offline": settings.offline,
        "log_level": settings.log_level,
        "verification_mode": settings.verification_mode,
        "max_concurrent_downloads": settings.max_concurrent_downloads,
        "max_concurrent_builds": settings.max_concurrent_builds,
        "download_timeout": settings.download_timeout,
        "build_timeout": settings.build_timeout,
        "flash_timeout": settings.flash_timeout,
    }

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "active_nav": "dashboard",
            "version": __version__,
            "config": config,
            "profile_count": profile_count,
            "build_count": build_count,
            "flash_count": flash_count,
        },
    )


# Profiles


@router.get("/profiles", response_class=HTMLResponse, name="gui_profiles_list")
def profiles_list(
    request: Request,
    db: DbSession,
    target: str | None = Query(None, description="Filter by target"),
    release: str | None = Query(None, description="Filter by release"),
    device_id: str | None = Query(None, description="Filter by device ID"),
    tag: str | None = Query(None, description="Filter by tag"),
) -> HTMLResponse:
    """Render the profiles list page."""
    # Build filters
    tags = [tag] if tag else None
    has_filters = any([target, release, device_id, tag])

    if has_filters:
        profiles = query_profiles(
            db,
            device_id=device_id,
            openwrt_release=release,
            target=target,
            tags=tags,
        )
    else:
        profiles = list_profiles(db)

    # Convert to schema for template
    profile_data = [profile_to_schema(p) for p in profiles]

    return templates.TemplateResponse(
        request=request,
        name="profiles/list.html",
        context={
            "active_nav": "profiles",
            "version": __version__,
            "profiles": profile_data,
            "target": target,
            "release": release,
            "device_id": device_id,
            "tag": tag,
        },
    )


@router.get(
    "/profiles/{profile_id}", response_class=HTMLResponse, name="gui_profile_detail"
)
def profile_detail(
    request: Request,
    profile_id: str,
    db: DbSession,
) -> HTMLResponse:
    """Render the profile detail page."""
    try:
        profile = get_profile(db, profile_id)
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Profile not found: {profile_id}",
        ) from None

    # Get recent builds for this profile
    builds = list_builds(db, profile_id=profile.id, limit=10)

    profile_schema = profile_to_schema(profile)

    return templates.TemplateResponse(
        request=request,
        name="profiles/detail.html",
        context={
            "active_nav": "profiles",
            "version": __version__,
            "profile": profile_schema,
            "builds": builds,
        },
    )


# Builds


@router.get("/builds", response_class=HTMLResponse, name="gui_builds_list")
def builds_list(
    request: Request,
    db: DbSession,
    status: str | None = Query(None, description="Filter by status"),
    profile: str | None = Query(None, description="Filter by profile ID"),
) -> HTMLResponse:
    """Render the builds list page."""
    # Parse status filter
    status_filter: BuildStatus | None = None
    if status:
        try:
            status_filter = BuildStatus(status)
        except ValueError:
            # Invalid status, ignore filter
            status = None

    # Resolve profile_id to database ID
    db_profile_id: int | None = None
    if profile:
        try:
            profile_obj = get_profile(db, profile)
            db_profile_id = profile_obj.id
        except ProfileNotFoundError:
            # Profile not found, show empty results
            pass

    builds = list_builds(db, profile_id=db_profile_id, status=status_filter, limit=100)

    return templates.TemplateResponse(
        request=request,
        name="builds/list.html",
        context={
            "active_nav": "builds",
            "version": __version__,
            "builds": builds,
            "status": status,
            "profile": profile,
        },
    )


@router.get("/builds/{build_id}", response_class=HTMLResponse, name="gui_build_detail")
def build_detail(
    request: Request,
    build_id: int,
    db: DbSession,
) -> HTMLResponse:
    """Render the build detail page."""
    try:
        build = get_build(db, build_id)
    except BuildNotFoundError:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Build not found: {build_id}",
        ) from None

    # Get artifacts
    artifacts = list(build.artifacts)

    return templates.TemplateResponse(
        request=request,
        name="builds/detail.html",
        context={
            "active_nav": "builds",
            "version": __version__,
            "build": build,
            "artifacts": artifacts,
        },
    )


@router.post("/builds", name="gui_builds_create")
def builds_create(
    db: DbSession,
    settings: AppSettings,  # Reserved for future use
    profile_id: str = Form(...),
    force_rebuild: bool = Form(False),
) -> RedirectResponse:
    """Handle build creation form submission.

    This is a placeholder that redirects to the build detail page.
    In a full implementation, it would call build_or_reuse() from
    the builds service.

    For now, since building requires an ImageBuilder to be available
    and that involves downloading, we show an info message.
    """
    # Validate profile exists
    try:
        profile = get_profile(db, profile_id)
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Profile not found: {profile_id}",
        ) from None

    # For a complete implementation, we would:
    # 1. ensure_builder() to get/download the ImageBuilder
    # 2. build_or_reuse() to run the build
    # 3. Redirect to the build detail page
    #
    # For this GUI implementation, we provide a simple placeholder
    # that shows the profile was found and the user should use CLI
    # or implement the full build flow.

    # Check if there's already a successful build for this profile
    builds = list_builds(
        db, profile_id=profile.id, status=BuildStatus.SUCCEEDED, limit=1
    )

    if builds and not force_rebuild:
        # Redirect to the most recent successful build
        return RedirectResponse(
            url=f"/ui/builds/{builds[0].id}",
            status_code=http_status.HTTP_303_SEE_OTHER,
        )

    # No existing build or force rebuild requested
    # In a full implementation, this would start the build
    # For now, redirect back to profile with a message
    return RedirectResponse(
        url=f"/ui/profiles/{profile_id}",
        status_code=http_status.HTTP_303_SEE_OTHER,
    )


# Flash


@router.get("/flash", response_class=HTMLResponse, name="gui_flash_list")
def flash_list(
    request: Request,
    db: DbSession,
    status: str | None = Query(None, description="Filter by status"),
    device: str | None = Query(None, description="Filter by device path"),
) -> HTMLResponse:
    """Render the flash records list page."""
    # Parse status filter
    status_filter: FlashStatus | None = None
    if status:
        try:
            status_filter = FlashStatus(status)
        except ValueError:
            status = None

    records = get_flash_records(
        db,
        device_path=device,
        status=status_filter,
        limit=100,
    )

    return templates.TemplateResponse(
        request=request,
        name="flash/list.html",
        context={
            "active_nav": "flash",
            "version": __version__,
            "records": records,
            "status": status,
            "device": device,
        },
    )


@router.get("/flash/new", response_class=HTMLResponse, name="gui_flash_wizard")
def flash_wizard(
    request: Request,
    db: DbSession,
    artifact_id: int | None = Query(None, description="Pre-selected artifact ID"),
) -> HTMLResponse:
    """Render the flash wizard page."""
    artifact = None
    error = None

    if artifact_id is not None:
        try:
            artifact = get_artifact(db, artifact_id)
        except ArtifactNotFoundError:
            error = f"Artifact not found: {artifact_id}"

    return templates.TemplateResponse(
        request=request,
        name="flash/wizard.html",
        context={
            "active_nav": "flash",
            "version": __version__,
            "artifact": artifact,
            "device_path": "",
            "error": error,
        },
    )


@router.post("/flash", name="gui_flash_start", response_model=None)
def flash_start(
    request: Request,
    db: DbSession,
    settings: AppSettings,
    artifact_id: int = Form(...),
    device_path: str = Form(...),
    confirmation: str = Form(...),
    wipe_before: bool = Form(False),
    dry_run: bool = Form(True),
    force: bool = Form(False),
) -> HTMLResponse | RedirectResponse:
    """Handle flash form submission.

    Enforces safety requirements:
    - confirmation must match device_path
    - dry_run defaults to True
    - Real write requires dry_run=False AND force=True
    """
    # Validate confirmation matches device path
    if confirmation.strip() != device_path.strip():
        # Re-render wizard with error
        artifact = None
        with contextlib.suppress(ArtifactNotFoundError):
            artifact = get_artifact(db, artifact_id)

        return templates.TemplateResponse(
            request=request,
            name="flash/wizard.html",
            context={
                "active_nav": "flash",
                "version": __version__,
                "artifact": artifact,
                "device_path": device_path,
                "error": "Device confirmation does not match. Please type the device path exactly.",
            },
            status_code=http_status.HTTP_400_BAD_REQUEST,
        )

    # Enforce safety: real write requires force flag
    if not dry_run and not force:
        artifact = None
        with contextlib.suppress(ArtifactNotFoundError):
            artifact = get_artifact(db, artifact_id)

        return templates.TemplateResponse(
            request=request,
            name="flash/wizard.html",
            context={
                "active_nav": "flash",
                "version": __version__,
                "artifact": artifact,
                "device_path": device_path,
                "error": "Actual write requires both dry_run=False AND force=True. "
                "Please check the 'Force' checkbox to confirm you understand the risks.",
            },
            status_code=http_status.HTTP_400_BAD_REQUEST,
        )

    # Perform flash operation
    try:
        result = flash_artifact(
            db,
            artifact_id=artifact_id,
            device_path=device_path.strip(),
            settings=settings,
            wipe_before=wipe_before,
            dry_run=dry_run,
            force=force,
        )

        if result.flash_record_id:
            # Redirect to the flash record detail page
            return RedirectResponse(
                url=f"/ui/flash/{result.flash_record_id}",
                status_code=http_status.HTTP_303_SEE_OTHER,
            )
        else:
            # Dry run or no record created - show result on wizard page
            artifact = None
            with contextlib.suppress(ArtifactNotFoundError):
                artifact = get_artifact(db, artifact_id)

            if result.success:
                success_msg = result.message or "Operation completed successfully."
                if dry_run:
                    success_msg = f"Dry run completed: {success_msg}"
                return templates.TemplateResponse(
                    request=request,
                    name="flash/wizard.html",
                    context={
                        "active_nav": "flash",
                        "version": __version__,
                        "artifact": artifact,
                        "device_path": device_path,
                        "success": success_msg,
                    },
                )
            else:
                return templates.TemplateResponse(
                    request=request,
                    name="flash/wizard.html",
                    context={
                        "active_nav": "flash",
                        "version": __version__,
                        "artifact": artifact,
                        "device_path": device_path,
                        "error": result.error_message or "Flash operation failed.",
                    },
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                )

    except ArtifactNotFoundError:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Artifact not found: {artifact_id}",
        ) from None
    except ArtifactFileNotFoundError as e:
        artifact = None
        with contextlib.suppress(ArtifactNotFoundError):
            artifact = get_artifact(db, artifact_id)

        return templates.TemplateResponse(
            request=request,
            name="flash/wizard.html",
            context={
                "active_nav": "flash",
                "version": __version__,
                "artifact": artifact,
                "device_path": device_path,
                "error": f"Artifact file not found on disk: {e.path}",
            },
            status_code=http_status.HTTP_404_NOT_FOUND,
        )


@router.get("/flash/{flash_id}", response_class=HTMLResponse, name="gui_flash_detail")
def flash_detail(
    request: Request,
    flash_id: int,
    db: DbSession,
) -> HTMLResponse:
    """Render the flash record detail page."""
    record = db.get(FlashRecord, flash_id)
    if record is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Flash record not found: {flash_id}",
        ) from None

    return templates.TemplateResponse(
        request=request,
        name="flash/detail.html",
        context={
            "active_nav": "flash",
            "version": __version__,
            "record": record,
        },
    )
