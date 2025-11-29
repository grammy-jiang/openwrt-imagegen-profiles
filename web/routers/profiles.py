"""Profile management endpoints.

Per docs/FRONTENDS.md section 3.2:
- GET /profiles - List profiles
- GET /profiles/{id} - Get profile by ID
- POST /profiles - Create profile
- PUT /profiles/{id} - Update profile
- DELETE /profiles/{id} - Delete profile
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from openwrt_imagegen.profiles.schema import ProfileSchema
from openwrt_imagegen.profiles.service import (
    ProfileExistsError,
    ProfileNotFoundError,
    create_profile,
    delete_profile,
    get_profile,
    list_profiles,
    profile_to_schema,
    query_profiles,
    update_profile,
)
from web.deps import get_db

router = APIRouter()


@router.get("")
def list_profiles_endpoint(
    device_id: str | None = Query(None, description="Filter by device ID"),
    release: str | None = Query(None, description="Filter by OpenWrt release"),
    target: str | None = Query(None, description="Filter by target"),
    subtarget: str | None = Query(None, description="Filter by subtarget"),
    tag: list[str] | None = Query(None, description="Filter by tags"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """List profiles with optional filters.

    Args:
        device_id: Filter by device ID.
        release: Filter by OpenWrt release.
        target: Filter by target.
        subtarget: Filter by subtarget.
        tag: Filter by tags.
        db: Database session.

    Returns:
        List of profiles.
    """
    if any([device_id, release, target, subtarget, tag]):
        profiles = query_profiles(
            db,
            device_id=device_id,
            openwrt_release=release,
            target=target,
            subtarget=subtarget,
            tags=tag,
        )
    else:
        profiles = list_profiles(db)

    return [profile_to_schema(p).model_dump(exclude_none=True) for p in profiles]


@router.get("/{profile_id}")
def get_profile_endpoint(
    profile_id: str,
    include_meta: bool = Query(False, description="Include metadata section"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get a profile by ID.

    Args:
        profile_id: Profile ID.
        include_meta: Whether to include metadata.
        db: Database session.

    Returns:
        Profile data.

    Raises:
        HTTPException: If profile not found.
    """
    try:
        profile = get_profile(db, profile_id)
        return profile_to_schema(profile, include_meta=include_meta).model_dump(
            exclude_none=True
        )
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "profile_not_found",
                "message": f"Profile not found: {profile_id}",
            },
        ) from None


@router.post("", status_code=status.HTTP_201_CREATED)
def create_profile_endpoint(
    profile_data: ProfileSchema,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a new profile.

    Args:
        profile_data: Profile data.
        db: Database session.

    Returns:
        Created profile.

    Raises:
        HTTPException: If profile already exists.
    """
    try:
        profile = create_profile(db, profile_data)
        return profile_to_schema(profile).model_dump(exclude_none=True)
    except ProfileExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "profile_exists",
                "message": f"Profile already exists: {profile_data.profile_id}",
            },
        ) from None


@router.put("/{profile_id}")
def update_profile_endpoint(
    profile_id: str,
    profile_data: ProfileSchema,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Update an existing profile.

    Args:
        profile_id: Profile ID to update.
        profile_data: New profile data.
        db: Database session.

    Returns:
        Updated profile.

    Raises:
        HTTPException: If profile not found or profile_id mismatch.
    """
    if profile_data.profile_id != profile_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "profile_id_mismatch",
                "message": f"Profile ID in body ({profile_data.profile_id}) does not match URL ({profile_id})",
            },
        )

    try:
        profile = update_profile(db, profile_id, profile_data)
        db.commit()
        return profile_to_schema(profile).model_dump(exclude_none=True)
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "profile_not_found",
                "message": f"Profile not found: {profile_id}",
            },
        ) from None


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile_endpoint(
    profile_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete a profile.

    Args:
        profile_id: Profile ID to delete.
        db: Database session.

    Raises:
        HTTPException: If profile not found.
    """
    try:
        delete_profile(db, profile_id)
        db.commit()
    except ProfileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "profile_not_found",
                "message": f"Profile not found: {profile_id}",
            },
        ) from None
