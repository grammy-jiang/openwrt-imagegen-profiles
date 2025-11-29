"""Thin CLI wrapper for openwrt_imagegen.

This module provides the command-line interface using Typer.
All business logic is delegated to core modules.
"""

import json
from typing import Annotated

import typer
from rich.console import Console

from openwrt_imagegen import __version__
from openwrt_imagegen.config import get_settings, print_settings_json

app = typer.Typer(
    name="imagegen",
    help="OpenWrt Image Generator - manage profiles, builds, and TF/SD flashing",
    no_args_is_help=True,
)
console = Console()


def version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"openwrt-imagegen version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-V",
            help="Show version and exit",
            callback=version_callback,
            is_eager=True,
        ),
    ] = None,
) -> None:
    """OpenWrt Image Generator - manage profiles, builds, and TF/SD flashing."""


@app.command()
def config(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Show effective configuration."""
    settings = get_settings()
    if json_output:
        console.print(print_settings_json(settings))
    else:
        tmp_dir_display = (
            str(settings.tmp_dir) if settings.tmp_dir else "(system default)"
        )
        console.print("[bold]Effective Configuration:[/bold]")
        console.print()
        console.print("[bold]Paths:[/bold]")
        console.print(f"  Cache directory:     {settings.cache_dir}")
        console.print(f"  Artifacts directory: {settings.artifacts_dir}")
        console.print(f"  Database URL:        {settings.db_url}")
        console.print(f"  Temp directory:      {tmp_dir_display}")
        console.print()
        console.print("[bold]Operational:[/bold]")
        console.print(f"  Offline mode:        {settings.offline}")
        console.print(f"  Log level:           {settings.log_level}")
        console.print(f"  Verification mode:   {settings.verification_mode}")
        console.print()
        console.print("[bold]Concurrency:[/bold]")
        console.print(f"  Max downloads:       {settings.max_concurrent_downloads}")
        console.print(f"  Max builds:          {settings.max_concurrent_builds}")
        console.print()
        console.print("[bold]Timeouts (seconds):[/bold]")
        console.print(f"  Download timeout:    {settings.download_timeout}")
        console.print(f"  Build timeout:       {settings.build_timeout}")
        console.print(f"  Flash timeout:       {settings.flash_timeout}")


# Placeholder subcommand groups for future implementation


profiles_app = typer.Typer(help="Manage device profiles")
app.add_typer(profiles_app, name="profiles")


@profiles_app.command("list")
def profiles_list(
    device_id: Annotated[
        str | None,
        typer.Option("--device", "-d", help="Filter by device ID"),
    ] = None,
    release: Annotated[
        str | None,
        typer.Option("--release", "-r", help="Filter by OpenWrt release"),
    ] = None,
    target: Annotated[
        str | None,
        typer.Option("--target", "-t", help="Filter by target"),
    ] = None,
    subtarget: Annotated[
        str | None,
        typer.Option("--subtarget", "-s", help="Filter by subtarget"),
    ] = None,
    tags: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Filter by tag (can be repeated)"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """List profiles in the database.

    Supports filtering by device, release, target, subtarget, and tags.
    Use --json for machine-readable output.
    """
    from openwrt_imagegen.db import create_all_tables, get_engine, get_session_factory
    from openwrt_imagegen.profiles.service import (
        list_profiles,
        profile_to_schema,
        query_profiles,
    )

    engine = get_engine()
    create_all_tables(engine)
    factory = get_session_factory(engine)

    with factory() as session:
        # Use query_profiles if any filters are specified, otherwise list_profiles
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
            profiles = list_profiles(session)

        if not profiles:
            if json_output:
                console.print("[]")
            else:
                console.print("[yellow]No profiles found[/yellow]")
            return

        if json_output:
            output = [
                profile_to_schema(p).model_dump(exclude_none=True) for p in profiles
            ]
            console.print(json.dumps(output, indent=2))
        else:
            console.print(f"[bold]Found {len(profiles)} profile(s):[/bold]")
            console.print()
            for p in profiles:
                console.print(f"  [green]{p.profile_id}[/green]")
                console.print(f"    Name: {p.name}")
                console.print(f"    Device: {p.device_id}")
                console.print(
                    f"    Target: {p.openwrt_release}/{p.target}/{p.subtarget}"
                )
                if p.tags:
                    console.print(f"    Tags: {', '.join(p.tags)}")
                console.print()


@profiles_app.command("show")
def profiles_show(
    profile_id: Annotated[str, typer.Argument(help="Profile ID to show")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Show details of a specific profile."""
    from openwrt_imagegen.db import create_all_tables, get_engine, get_session_factory
    from openwrt_imagegen.profiles.service import (
        ProfileNotFoundError,
        get_profile,
        profile_to_schema,
    )

    engine = get_engine()
    create_all_tables(engine)
    factory = get_session_factory(engine)

    with factory() as session:
        try:
            profile = get_profile(session, profile_id)
        except ProfileNotFoundError:
            console.print(f"[red]Profile not found: {profile_id}[/red]")
            raise typer.Exit(code=1) from None

        schema = profile_to_schema(profile, include_meta=True)

        if json_output:
            console.print(schema.model_dump_json(indent=2, exclude_none=True))
        else:
            from openwrt_imagegen.profiles.io import profile_to_yaml_string

            console.print(profile_to_yaml_string(schema))


@profiles_app.command("import")
def profiles_import(
    path: Annotated[str, typer.Argument(help="Path to profile file or directory")],
    update: Annotated[
        bool,
        typer.Option("--update", "-u", help="Update existing profiles"),
    ] = False,
    pattern: Annotated[
        str,
        typer.Option("--pattern", "-p", help="Glob pattern for directory import"),
    ] = "*.yaml",
) -> None:
    """Import profiles from YAML/JSON file(s)."""
    from pathlib import Path

    from openwrt_imagegen.db import create_all_tables, get_engine, get_session_factory
    from openwrt_imagegen.profiles.service import (
        import_profile_from_file,
        import_profiles_from_directory,
    )

    file_path = Path(path)
    if not file_path.exists():
        console.print(f"[red]Path not found: {path}[/red]")
        raise typer.Exit(code=1)

    engine = get_engine()
    create_all_tables(engine)
    factory = get_session_factory(engine)

    with factory() as session:
        if file_path.is_dir():
            result = import_profiles_from_directory(
                session, file_path, pattern=pattern, update_existing=update
            )
            session.commit()

            console.print("[bold]Import results:[/bold]")
            console.print(f"  Total: {result.total}")
            console.print(f"  [green]Succeeded: {result.succeeded}[/green]")
            if result.failed > 0:
                console.print(f"  [red]Failed: {result.failed}[/red]")
                for r in result.results:
                    if not r.success:
                        console.print(f"    - {r.profile_id}: {r.error}")
                raise typer.Exit(code=1)
        else:
            single_result = import_profile_from_file(
                session, file_path, update_existing=update
            )
            session.commit()

            if single_result.success:
                action = "Created" if single_result.created else "Updated"
                console.print(
                    f"[green]{action} profile: {single_result.profile_id}[/green]"
                )
            else:
                console.print(f"[red]Failed: {single_result.error}[/red]")
                raise typer.Exit(code=1)


@profiles_app.command("export")
def profiles_export(
    path: Annotated[str, typer.Argument(help="Output path (file or directory)")],
    profile_id: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Profile ID to export (for single file)"),
    ] = None,
    format: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format for directory export"),
    ] = "yaml",
    include_meta: Annotated[
        bool,
        typer.Option("--include-meta", help="Include metadata in export"),
    ] = False,
) -> None:
    """Export profiles to YAML/JSON file(s)."""
    from pathlib import Path

    from openwrt_imagegen.db import create_all_tables, get_engine, get_session_factory
    from openwrt_imagegen.profiles.service import (
        ProfileNotFoundError,
        export_profile_to_file,
        export_profiles_to_directory,
    )

    output_path = Path(path)
    engine = get_engine()
    create_all_tables(engine)
    factory = get_session_factory(engine)

    with factory() as session:
        try:
            if profile_id:
                # Export single profile
                export_profile_to_file(
                    session, profile_id, output_path, include_meta=include_meta
                )
                console.print(f"[green]Exported {profile_id} to {path}[/green]")
            else:
                # Export all profiles to directory
                count = export_profiles_to_directory(
                    session, output_path, format=format, include_meta=include_meta
                )
                console.print(f"[green]Exported {count} profile(s) to {path}[/green]")
        except ProfileNotFoundError as e:
            console.print(f"[red]Profile not found: {e.profile_id}[/red]")
            raise typer.Exit(code=1) from None
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(code=1) from None


@profiles_app.command("validate")
def profiles_validate(
    path: Annotated[str, typer.Argument(help="Path to profile file to validate")],
) -> None:
    """Validate a profile file without importing."""
    from pathlib import Path

    from pydantic import ValidationError

    from openwrt_imagegen.profiles.io import load_profile

    file_path = Path(path)
    if not file_path.exists():
        console.print(f"[red]File not found: {path}[/red]")
        raise typer.Exit(code=1)

    try:
        profile = load_profile(file_path)
        profile.validate_snapshot_policy()
        console.print(f"[green]✓ Valid profile: {profile.profile_id}[/green]")
        console.print(f"  Name: {profile.name}")
        console.print(f"  Device: {profile.device_id}")
        console.print(
            f"  Target: {profile.openwrt_release}/{profile.target}/{profile.subtarget}"
        )
    except ValidationError as e:
        console.print("[red]Validation failed:[/red]")
        console.print(str(e))
        raise typer.Exit(code=1) from None
    except ValueError as e:
        console.print(f"[red]Validation failed: {e}[/red]")
        raise typer.Exit(code=1) from None


builders_app = typer.Typer(help="Manage Image Builder cache")
app.add_typer(builders_app, name="builders")


@builders_app.command("list")
def builders_list(
    release: Annotated[
        str | None,
        typer.Option("--release", "-r", help="Filter by release"),
    ] = None,
    target: Annotated[
        str | None,
        typer.Option("--target", "-t", help="Filter by target"),
    ] = None,
    subtarget: Annotated[
        str | None,
        typer.Option("--subtarget", "-s", help="Filter by subtarget"),
    ] = None,
    state: Annotated[
        str | None,
        typer.Option(
            "--state", help="Filter by state (pending, ready, broken, deprecated)"
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """List cached Image Builders."""
    from openwrt_imagegen.db import create_all_tables, get_engine, get_session_factory
    from openwrt_imagegen.imagebuilder.service import list_builders
    from openwrt_imagegen.types import ImageBuilderState

    engine = get_engine()
    create_all_tables(engine)
    factory = get_session_factory(engine)

    # Parse state filter
    state_filter: ImageBuilderState | None = None
    if state:
        try:
            state_filter = ImageBuilderState(state)
        except ValueError:
            console.print(f"[red]Invalid state: {state}[/red]")
            console.print("Valid values: pending, ready, broken, deprecated")
            raise typer.Exit(code=1) from None

    with factory() as session:
        builders = list_builders(
            session,
            release=release,
            target=target,
            subtarget=subtarget,
            state=state_filter,
        )

        if not builders:
            if json_output:
                console.print("[]")
            else:
                console.print("[yellow]No Image Builders found[/yellow]")
            return

        if json_output:
            output = [
                {
                    "openwrt_release": b.openwrt_release,
                    "target": b.target,
                    "subtarget": b.subtarget,
                    "state": b.state,
                    "root_dir": b.root_dir,
                    "checksum": b.checksum,
                    "signature_verified": b.signature_verified,
                    "first_used_at": b.first_used_at.isoformat()
                    if b.first_used_at
                    else None,
                    "last_used_at": b.last_used_at.isoformat()
                    if b.last_used_at
                    else None,
                }
                for b in builders
            ]
            console.print(json.dumps(output, indent=2))
        else:
            console.print(f"[bold]Found {len(builders)} Image Builder(s):[/bold]")
            console.print()
            for b in builders:
                state_color = {
                    "ready": "green",
                    "pending": "yellow",
                    "broken": "red",
                    "deprecated": "dim",
                }.get(b.state, "white")
                console.print(
                    f"  [{state_color}]{b.openwrt_release}/{b.target}/{b.subtarget}[/{state_color}]"
                )
                console.print(f"    State: {b.state}")
                console.print(f"    Root: {b.root_dir}")
                if b.last_used_at:
                    console.print(f"    Last used: {b.last_used_at.isoformat()}")
                console.print()


@builders_app.command("ensure")
def builders_ensure(
    release: Annotated[str, typer.Argument(help="OpenWrt release version")],
    target: Annotated[str, typer.Argument(help="Target platform")],
    subtarget: Annotated[str, typer.Argument(help="Subtarget")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Force re-download even if cached"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Ensure an Image Builder is available."""
    from openwrt_imagegen.db import create_all_tables, get_engine, get_session_factory
    from openwrt_imagegen.imagebuilder.service import (
        ImageBuilderBrokenError,
        OfflineModeError,
        ensure_builder,
    )

    engine = get_engine()
    create_all_tables(engine)
    factory = get_session_factory(engine)

    with factory() as session:
        try:
            console.print(
                f"[blue]Ensuring Image Builder {release}/{target}/{subtarget}...[/blue]"
            )
            builder = ensure_builder(
                session,
                release=release,
                target=target,
                subtarget=subtarget,
                force_download=force,
            )
            session.commit()

            if json_output:
                output = {
                    "openwrt_release": builder.openwrt_release,
                    "target": builder.target,
                    "subtarget": builder.subtarget,
                    "state": builder.state,
                    "root_dir": builder.root_dir,
                    "checksum": builder.checksum,
                }
                console.print(json.dumps(output, indent=2))
            else:
                console.print(
                    f"[green]✓ Image Builder ready: {release}/{target}/{subtarget}[/green]"
                )
                console.print(f"  Root: {builder.root_dir}")
                if builder.checksum:
                    console.print(f"  Checksum: {builder.checksum[:16]}...")

        except OfflineModeError:
            console.print("[red]Cannot download in offline mode[/red]")
            raise typer.Exit(code=1) from None
        except ImageBuilderBrokenError:
            console.print(
                f"[red]Image Builder {release}/{target}/{subtarget} is broken. "
                "Use --force to re-download.[/red]"
            )
            raise typer.Exit(code=1) from None
        except Exception as e:
            console.print(f"[red]Failed to ensure Image Builder: {e}[/red]")
            raise typer.Exit(code=1) from None


@builders_app.command("info")
def builders_info(
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Show Image Builder cache information."""
    from openwrt_imagegen.imagebuilder.service import get_builder_cache_info

    info = get_builder_cache_info()

    if json_output:
        console.print(json.dumps(info, indent=2))
    else:
        console.print("[bold]Image Builder Cache Information:[/bold]")
        console.print()
        console.print(f"  Cache directory: {info['cache_dir']}")
        console.print(f"  Exists: {info['exists']}")
        console.print(f"  Total size: {info['total_size_human']}")


@builders_app.command("prune")
def builders_prune(
    deprecated_only: Annotated[
        bool,
        typer.Option(
            "--deprecated-only", help="Only prune deprecated builders (default)"
        ),
    ] = True,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run", "-n", help="Show what would be pruned without actually pruning"
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Prune unused or deprecated Image Builders."""
    from openwrt_imagegen.db import create_all_tables, get_engine, get_session_factory
    from openwrt_imagegen.imagebuilder.service import prune_builders

    engine = get_engine()
    create_all_tables(engine)
    factory = get_session_factory(engine)

    with factory() as session:
        pruned = prune_builders(
            session,
            deprecated_only=deprecated_only,
            dry_run=dry_run,
        )
        if not dry_run:
            session.commit()

        if json_output:
            output = {
                "dry_run": dry_run,
                "pruned": [
                    {"release": r, "target": t, "subtarget": s} for r, t, s in pruned
                ],
            }
            console.print(json.dumps(output, indent=2))
        else:
            if not pruned:
                console.print("[yellow]No Image Builders to prune[/yellow]")
            else:
                prefix = "[DRY RUN] Would prune" if dry_run else "Pruned"
                console.print(f"[bold]{prefix} {len(pruned)} Image Builder(s):[/bold]")
                for r, t, s in pruned:
                    console.print(f"  - {r}/{t}/{s}")


builds_app = typer.Typer(help="Build images")
app.add_typer(builds_app, name="build")


@builds_app.command("run")
def build_run(
    profile_id: Annotated[str, typer.Argument(help="Profile ID to build")],
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Force rebuild even if cached"),
    ] = False,
) -> None:
    """Build an image for a profile."""
    console.print(
        f"[yellow]Not yet implemented: build {profile_id} (force={force})[/yellow]"
    )
    raise typer.Exit(code=1)


@builds_app.command("batch")
def build_batch_cmd(
    profile_ids: Annotated[
        list[str] | None,
        typer.Option("--profile", "-p", help="Profile ID(s) to build"),
    ] = None,
    device_id: Annotated[
        str | None,
        typer.Option("--device", "-d", help="Filter by device ID"),
    ] = None,
    release: Annotated[
        str | None,
        typer.Option("--release", "-r", help="Filter by OpenWrt release"),
    ] = None,
    target: Annotated[
        str | None,
        typer.Option("--target", "-t", help="Filter by target"),
    ] = None,
    subtarget: Annotated[
        str | None,
        typer.Option("--subtarget", "-s", help="Filter by subtarget"),
    ] = None,
    tags: Annotated[
        list[str] | None,
        typer.Option("--tag", help="Filter by tag (can be repeated)"),
    ] = None,
    mode: Annotated[
        str,
        typer.Option(
            "--mode", "-m", help="Batch mode: fail-fast or best-effort (default)"
        ),
    ] = "best-effort",
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Force rebuild even if cached"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Build images for multiple profiles.

    Select profiles by explicit IDs or filters (release, target, tags, etc.).
    Use --mode=fail-fast to stop on first failure, or --mode=best-effort to
    continue building remaining profiles after failures.
    """
    from openwrt_imagegen.builds.service import (
        BatchBuildFilter,
        build_batch,
    )
    from openwrt_imagegen.db import create_all_tables, get_engine, get_session_factory
    from openwrt_imagegen.types import BatchMode

    # Validate mode
    try:
        batch_mode = BatchMode(mode)
    except ValueError:
        console.print(f"[red]Invalid mode: {mode}[/red]")
        console.print("Valid values: fail-fast, best-effort")
        raise typer.Exit(code=1) from None

    # Validate at least one filter is provided
    if not any([profile_ids, device_id, release, target, subtarget, tags]):
        console.print("[red]Error: At least one filter must be specified[/red]")
        console.print(
            "Use --profile, --device, --release, --target, --subtarget, or --tag"
        )
        raise typer.Exit(code=1)

    engine = get_engine()
    create_all_tables(engine)
    factory = get_session_factory(engine)

    with factory() as session:
        filter_spec = BatchBuildFilter(
            profile_ids=profile_ids,
            device_id=device_id,
            openwrt_release=release,
            target=target,
            subtarget=subtarget,
            tags=tags,
        )

        if not json_output:
            console.print("[blue]Starting batch build...[/blue]")

        settings = get_settings()
        result = build_batch(
            session=session,
            filter_spec=filter_spec,
            settings=settings,
            mode=batch_mode,
            force_rebuild=force,
        )
        session.commit()

        if json_output:
            console.print(result.model_dump_json(indent=2))
        else:
            # Human-readable output
            console.print()
            console.print("[bold]Batch Build Results:[/bold]")
            console.print(f"  Total profiles: {result.total}")
            console.print(f"  [green]Succeeded: {result.succeeded}[/green]")
            console.print(f"  [blue]Cache hits: {result.cache_hits}[/blue]")
            if result.failed > 0:
                console.print(f"  [red]Failed: {result.failed}[/red]")
            if result.stopped_early:
                console.print("  [yellow]Stopped early (fail-fast mode)[/yellow]")

            console.print()
            console.print("[bold]Per-Profile Results:[/bold]")
            for r in result.results:
                pid = r["profile_id"]
                if r["success"]:
                    hit_marker = " (cache hit)" if r["is_cache_hit"] else ""
                    console.print(f"  [green]✓ {pid}{hit_marker}[/green]")
                    if r["artifacts"]:
                        for a in r["artifacts"]:
                            console.print(f"      {a['filename']}")
                else:
                    console.print(f"  [red]✗ {pid}[/red]")
                    if r["error_message"]:
                        console.print(f"      Error: {r['error_message']}")

        if result.failed > 0:
            raise typer.Exit(code=1)


@builds_app.command("list")
def builds_list(
    profile_id: Annotated[
        str | None,
        typer.Option("--profile", "-p", help="Filter by profile ID"),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option(
            "--status", "-s", help="Filter by status (pending/running/succeeded/failed)"
        ),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum number of records to return"),
    ] = 100,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """List build records."""
    from openwrt_imagegen.builds.service import list_builds
    from openwrt_imagegen.db import create_all_tables, get_engine, get_session_factory
    from openwrt_imagegen.profiles.service import ProfileNotFoundError, get_profile
    from openwrt_imagegen.types import BuildStatus

    engine = get_engine()
    create_all_tables(engine)
    factory = get_session_factory(engine)

    # Parse status filter
    status_filter: BuildStatus | None = None
    if status:
        try:
            status_filter = BuildStatus(status)
        except ValueError:
            console.print(f"[red]Invalid status: {status}[/red]")
            console.print("Valid values: pending, running, succeeded, failed")
            raise typer.Exit(code=1) from None

    with factory() as session:
        # Resolve profile_id to database ID if provided
        db_profile_id: int | None = None
        if profile_id:
            try:
                profile = get_profile(session, profile_id)
                db_profile_id = profile.id
            except ProfileNotFoundError:
                console.print(f"[red]Profile not found: {profile_id}[/red]")
                raise typer.Exit(code=1) from None

        builds = list_builds(
            session,
            profile_id=db_profile_id,
            status=status_filter,
            limit=limit,
        )

        if not builds:
            if json_output:
                console.print("[]")
            else:
                console.print("[yellow]No build records found[/yellow]")
            return

        if json_output:
            output = [
                {
                    "id": b.id,
                    "profile_id": b.profile.profile_id if b.profile else None,
                    "status": b.status,
                    "cache_key": b.cache_key,
                    "is_cache_hit": b.is_cache_hit,
                    "requested_at": b.requested_at.isoformat()
                    if b.requested_at
                    else None,
                    "started_at": b.started_at.isoformat() if b.started_at else None,
                    "finished_at": b.finished_at.isoformat() if b.finished_at else None,
                    "log_path": b.log_path,
                    "error_type": b.error_type,
                    "error_message": b.error_message,
                    "artifact_count": len(b.artifacts),
                }
                for b in builds
            ]
            console.print(json.dumps(output, indent=2))
        else:
            console.print(f"[bold]Found {len(builds)} build(s):[/bold]")
            console.print()
            for b in builds:
                status_color = {
                    "succeeded": "green",
                    "failed": "red",
                    "running": "blue",
                    "pending": "yellow",
                }.get(b.status, "white")
                profile_display = b.profile.profile_id if b.profile else "N/A"
                console.print(f"  [{status_color}]Build #{b.id}[/{status_color}]")
                console.print(f"    Profile: {profile_display}")
                console.print(f"    Status: {b.status}")
                console.print(f"    Cache hit: {b.is_cache_hit}")
                console.print(
                    f"    Requested: {b.requested_at.isoformat() if b.requested_at else 'N/A'}"
                )
                console.print(f"    Artifacts: {len(b.artifacts)}")
                if b.error_message:
                    console.print(f"    Error: {b.error_message}")
                console.print()


artifacts_app = typer.Typer(help="Manage build artifacts")
app.add_typer(artifacts_app, name="artifacts")


@artifacts_app.command("list")
def artifacts_list(
    build_id: Annotated[
        int | None,
        typer.Option("--build-id", "-b", help="Filter by build ID"),
    ] = None,
    kind: Annotated[
        str | None,
        typer.Option("--kind", "-k", help="Filter by artifact kind"),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """List artifacts."""
    from sqlalchemy import select

    from openwrt_imagegen.builds.models import Artifact
    from openwrt_imagegen.db import create_all_tables, get_engine, get_session_factory

    engine = get_engine()
    create_all_tables(engine)
    factory = get_session_factory(engine)

    with factory() as session:
        stmt = select(Artifact)

        if build_id is not None:
            stmt = stmt.where(Artifact.build_id == build_id)
        if kind is not None:
            stmt = stmt.where(Artifact.kind == kind)

        stmt = stmt.order_by(Artifact.id.desc()).limit(100)
        artifacts = list(session.execute(stmt).scalars().all())

        if not artifacts:
            if json_output:
                console.print("[]")
            else:
                console.print("[yellow]No artifacts found[/yellow]")
            return

        if json_output:
            output = [
                {
                    "id": a.id,
                    "build_id": a.build_id,
                    "kind": a.kind,
                    "filename": a.filename,
                    "relative_path": a.relative_path,
                    "absolute_path": a.absolute_path,
                    "size_bytes": a.size_bytes,
                    "sha256": a.sha256,
                    "labels": a.labels,
                }
                for a in artifacts
            ]
            console.print(json.dumps(output, indent=2))
        else:
            console.print(f"[bold]Found {len(artifacts)} artifact(s):[/bold]")
            console.print()
            for a in artifacts:
                console.print(f"  [green]Artifact #{a.id}[/green]")
                console.print(f"    Build ID: {a.build_id}")
                console.print(f"    Kind: {a.kind or 'unknown'}")
                console.print(f"    Filename: {a.filename}")
                console.print(f"    Size: {a.size_bytes:,} bytes")
                console.print(f"    SHA256: {a.sha256[:16]}...")
                console.print()


@artifacts_app.command("show")
def artifacts_show(
    artifact_id: Annotated[int, typer.Argument(help="Artifact ID to show")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Show details of a specific artifact."""
    from openwrt_imagegen.builds.models import Artifact
    from openwrt_imagegen.db import create_all_tables, get_engine, get_session_factory

    engine = get_engine()
    create_all_tables(engine)
    factory = get_session_factory(engine)

    with factory() as session:
        artifact = session.get(Artifact, artifact_id)

        if artifact is None:
            console.print(f"[red]Artifact not found: {artifact_id}[/red]")
            raise typer.Exit(code=1)

        if json_output:
            output = {
                "id": artifact.id,
                "build_id": artifact.build_id,
                "kind": artifact.kind,
                "filename": artifact.filename,
                "relative_path": artifact.relative_path,
                "absolute_path": artifact.absolute_path,
                "size_bytes": artifact.size_bytes,
                "sha256": artifact.sha256,
                "labels": artifact.labels,
            }
            console.print(json.dumps(output, indent=2))
        else:
            console.print(f"[bold]Artifact #{artifact.id}[/bold]")
            console.print()
            console.print(f"  Build ID:      {artifact.build_id}")
            console.print(f"  Kind:          {artifact.kind or 'unknown'}")
            console.print(f"  Filename:      {artifact.filename}")
            console.print(f"  Relative path: {artifact.relative_path}")
            console.print(f"  Absolute path: {artifact.absolute_path or 'N/A'}")
            console.print(f"  Size:          {artifact.size_bytes:,} bytes")
            console.print(f"  SHA256:        {artifact.sha256}")
            if artifact.labels:
                console.print(f"  Labels:        {', '.join(artifact.labels)}")


flash_app = typer.Typer(help="Flash images to TF/SD cards")
app.add_typer(flash_app, name="flash")


@flash_app.command("write")
def flash_write(
    artifact_id: Annotated[int, typer.Argument(help="Artifact ID to flash")],
    device: Annotated[str, typer.Argument(help="Device path (e.g., /dev/sdX)")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be done without writing"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation prompts"),
    ] = False,
    wipe: Annotated[
        bool,
        typer.Option("--wipe", "-w", help="Wipe device before writing"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Flash an artifact to a TF/SD card.

    Requires explicit device path (e.g., /dev/sdb, /dev/mmcblk0).
    Never operates on partitions (e.g., /dev/sdb1).

    Use --dry-run to see what would happen without writing.
    Use --force to skip confirmation prompts.
    Use --wipe to clear existing signatures before writing.
    """
    from openwrt_imagegen.db import create_all_tables, get_engine, get_session_factory
    from openwrt_imagegen.flash.service import (
        ArtifactFileNotFoundError,
        ArtifactNotFoundError,
        flash_artifact,
    )

    engine = get_engine()
    create_all_tables(engine)
    factory = get_session_factory(engine)

    settings = get_settings()

    # Confirmation prompt unless force or dry-run
    if not force and not dry_run:
        console.print(f"[bold red]WARNING:[/bold red] This will OVERWRITE {device}")
        console.print(f"  Artifact ID: {artifact_id}")
        if wipe:
            console.print("  Device will be WIPED before writing")
        confirm = typer.confirm("Are you sure you want to continue?", default=False)
        if not confirm:
            console.print("[yellow]Aborted[/yellow]")
            raise typer.Exit(code=0)

    with factory() as session:
        try:
            if dry_run and not json_output:
                console.print("[blue]Dry-run mode: validating without writing[/blue]")

            result = flash_artifact(
                session,
                artifact_id=artifact_id,
                device_path=device,
                settings=settings,
                wipe_before=wipe,
                dry_run=dry_run,
                force=force,
            )

            if not dry_run:
                session.commit()

            if json_output:
                output = {
                    "success": result.success,
                    "flash_record_id": result.flash_record_id,
                    "image_path": result.image_path,
                    "device_path": result.device_path,
                    "bytes_written": result.bytes_written,
                    "source_hash": result.source_hash,
                    "device_hash": result.device_hash,
                    "verification_mode": result.verification_mode.value,
                    "verification_result": result.verification_result.value,
                    "message": result.message,
                    "error_message": result.error_message,
                    "error_code": result.error_code,
                }
                console.print(json.dumps(output, indent=2))
            else:
                if result.success:
                    if dry_run:
                        console.print("[green]✓ Dry-run validation passed[/green]")
                        console.print(f"  Would write {result.bytes_written} bytes")
                        console.print(f"  Image: {result.image_path}")
                        console.print(f"  Device: {result.device_path}")
                    else:
                        console.print("[green]✓ Flash succeeded[/green]")
                        console.print(f"  Bytes written: {result.bytes_written}")
                        console.print(
                            f"  Verification: {result.verification_result.value}"
                        )
                        if result.flash_record_id:
                            console.print(f"  Record ID: {result.flash_record_id}")
                else:
                    console.print("[red]✗ Flash failed[/red]")
                    if result.error_message:
                        console.print(f"  Error: {result.error_message}")

            if not result.success:
                raise typer.Exit(code=1)

        except ArtifactNotFoundError as e:
            console.print(f"[red]Artifact not found: {e.artifact_id}[/red]")
            raise typer.Exit(code=1) from None
        except ArtifactFileNotFoundError as e:
            console.print(f"[red]Artifact file not found: {e.path}[/red]")
            raise typer.Exit(code=1) from None
        except Exception as e:
            console.print(f"[red]Flash failed: {e}[/red]")
            raise typer.Exit(code=1) from None


@flash_app.command("image")
def flash_image_cmd(
    image_path: Annotated[str, typer.Argument(help="Path to image file")],
    device: Annotated[str, typer.Argument(help="Device path (e.g., /dev/sdX)")],
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", "-n", help="Show what would be done without writing"),
    ] = False,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Skip confirmation prompts"),
    ] = False,
    wipe: Annotated[
        bool,
        typer.Option("--wipe", "-w", help="Wipe device before writing"),
    ] = False,
    skip_verify: Annotated[
        bool,
        typer.Option("--skip-verify", help="Skip hash verification after write"),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """Flash an image file to a TF/SD card.

    This flashes a raw image file without database tracking.
    Use 'flash write' to flash a tracked artifact instead.

    Requires explicit device path (e.g., /dev/sdb, /dev/mmcblk0).
    Never operates on partitions (e.g., /dev/sdb1).
    """
    from openwrt_imagegen.flash.service import flash_image
    from openwrt_imagegen.types import VerificationMode

    settings = get_settings()

    verification_mode = (
        VerificationMode.SKIP
        if skip_verify
        else VerificationMode(settings.verification_mode)
    )

    # Confirmation prompt unless force or dry-run
    if not force and not dry_run:
        console.print(f"[bold red]WARNING:[/bold red] This will OVERWRITE {device}")
        console.print(f"  Image: {image_path}")
        if wipe:
            console.print("  Device will be WIPED before writing")
        confirm = typer.confirm("Are you sure you want to continue?", default=False)
        if not confirm:
            console.print("[yellow]Aborted[/yellow]")
            raise typer.Exit(code=0)

    try:
        if dry_run and not json_output:
            console.print("[blue]Dry-run mode: validating without writing[/blue]")

        result = flash_image(
            image_path,
            device,
            settings=settings,
            wipe_before=wipe,
            verification_mode=verification_mode,
            dry_run=dry_run,
            force=force,
        )

        if json_output:
            output = {
                "success": result.success,
                "image_path": result.image_path,
                "device_path": result.device_path,
                "bytes_written": result.bytes_written,
                "source_hash": result.source_hash,
                "device_hash": result.device_hash,
                "verification_mode": result.verification_mode.value,
                "verification_result": result.verification_result.value,
                "message": result.message,
                "error_message": result.error_message,
                "error_code": result.error_code,
            }
            console.print(json.dumps(output, indent=2))
        else:
            if result.success:
                if dry_run:
                    console.print("[green]✓ Dry-run validation passed[/green]")
                    console.print(f"  Would write {result.bytes_written} bytes")
                    console.print(f"  Image: {result.image_path}")
                    console.print(f"  Device: {result.device_path}")
                else:
                    console.print("[green]✓ Flash succeeded[/green]")
                    console.print(f"  Bytes written: {result.bytes_written}")
                    console.print(f"  Verification: {result.verification_result.value}")
            else:
                console.print("[red]✗ Flash failed[/red]")
                if result.error_message:
                    console.print(f"  Error: {result.error_message}")

        if not result.success:
            raise typer.Exit(code=1)

    except Exception as e:
        console.print(f"[red]Flash failed: {e}[/red]")
        raise typer.Exit(code=1) from None


@flash_app.command("list")
def flash_list(
    artifact_id: Annotated[
        int | None,
        typer.Option("--artifact-id", "-a", help="Filter by artifact ID"),
    ] = None,
    build_id: Annotated[
        int | None,
        typer.Option("--build-id", "-b", help="Filter by build ID"),
    ] = None,
    device_path: Annotated[
        str | None,
        typer.Option("--device", "-d", help="Filter by device path"),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option(
            "--status", "-s", help="Filter by status (pending/running/succeeded/failed)"
        ),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum number of records to return"),
    ] = 100,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """List flash records.

    Shows history of flash operations with optional filters.
    """
    from openwrt_imagegen.db import create_all_tables, get_engine, get_session_factory
    from openwrt_imagegen.flash.service import get_flash_records
    from openwrt_imagegen.types import FlashStatus

    engine = get_engine()
    create_all_tables(engine)
    factory = get_session_factory(engine)

    # Parse status filter
    status_filter: FlashStatus | None = None
    if status:
        try:
            status_filter = FlashStatus(status)
        except ValueError:
            console.print(f"[red]Invalid status: {status}[/red]")
            console.print("Valid values: pending, running, succeeded, failed")
            raise typer.Exit(code=1) from None

    with factory() as session:
        records = get_flash_records(
            session,
            artifact_id=artifact_id,
            build_id=build_id,
            device_path=device_path,
            status=status_filter,
            limit=limit,
        )

        if not records:
            if json_output:
                console.print("[]")
            else:
                console.print("[yellow]No flash records found[/yellow]")
            return

        if json_output:
            output = [
                {
                    "id": r.id,
                    "artifact_id": r.artifact_id,
                    "build_id": r.build_id,
                    "device_path": r.device_path,
                    "device_model": r.device_model,
                    "device_serial": r.device_serial,
                    "status": r.status,
                    "wiped_before_flash": r.wiped_before_flash,
                    "verification_mode": r.verification_mode,
                    "verification_result": r.verification_result,
                    "requested_at": r.requested_at.isoformat()
                    if r.requested_at
                    else None,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                    "error_type": r.error_type,
                    "error_message": r.error_message,
                    "log_path": r.log_path,
                }
                for r in records
            ]
            console.print(json.dumps(output, indent=2))
        else:
            console.print(f"[bold]Found {len(records)} flash record(s):[/bold]")
            console.print()
            for r in records:
                status_color = {
                    "succeeded": "green",
                    "failed": "red",
                    "running": "blue",
                    "pending": "yellow",
                }.get(r.status, "white")
                console.print(f"  [{status_color}]Flash #{r.id}[/{status_color}]")
                console.print(f"    Artifact ID: {r.artifact_id}")
                console.print(f"    Build ID: {r.build_id}")
                console.print(f"    Device: {r.device_path}")
                console.print(f"    Status: {r.status}")
                console.print(f"    Verification: {r.verification_result or 'N/A'}")
                console.print(
                    f"    Requested: {r.requested_at.isoformat() if r.requested_at else 'N/A'}"
                )
                if r.error_message:
                    console.print(f"    Error: {r.error_message}")
                console.print()


if __name__ == "__main__":
    app()
