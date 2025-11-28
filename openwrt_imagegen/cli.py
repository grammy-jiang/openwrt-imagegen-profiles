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
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Output as JSON"),
    ] = False,
) -> None:
    """List all profiles in the database."""
    from openwrt_imagegen.db import create_all_tables, get_engine, get_session_factory
    from openwrt_imagegen.profiles.service import list_profiles, profile_to_schema

    engine = get_engine()
    create_all_tables(engine)
    factory = get_session_factory(engine)

    with factory() as session:
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


@builds_app.command("list")
def builds_list() -> None:
    """List build records."""
    console.print("[yellow]Not yet implemented[/yellow]")
    raise typer.Exit(code=1)


artifacts_app = typer.Typer(help="Manage build artifacts")
app.add_typer(artifacts_app, name="artifacts")


@artifacts_app.command("list")
def artifacts_list(
    build_id: Annotated[
        int | None,
        typer.Option("--build-id", help="Filter by build ID"),
    ] = None,
) -> None:
    """List artifacts."""
    console.print(
        f"[yellow]Not yet implemented: list artifacts (build={build_id})[/yellow]"
    )
    raise typer.Exit(code=1)


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
) -> None:
    """Flash an artifact to a TF/SD card."""
    console.print(
        f"[yellow]Not yet implemented: flash artifact {artifact_id} to {device} "
        f"(dry_run={dry_run}, force={force})[/yellow]"
    )
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
