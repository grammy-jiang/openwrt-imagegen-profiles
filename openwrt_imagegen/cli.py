"""Thin CLI wrapper for openwrt_imagegen.

This module provides the command-line interface using Typer.
All business logic is delegated to core modules.
"""

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
        console.print("[bold]Effective Configuration:[/bold]")
        console.print(f"  Cache directory:    {settings.cache_dir}")
        console.print(f"  Artifacts directory: {settings.artifacts_dir}")
        console.print(f"  Database URL:       {settings.db_url}")
        console.print(f"  Offline mode:       {settings.offline}")
        console.print(f"  Log level:          {settings.log_level}")
        console.print(f"  Max downloads:      {settings.max_concurrent_downloads}")
        console.print(f"  Max builds:         {settings.max_concurrent_builds}")
        console.print(f"  Verification mode:  {settings.verification_mode}")


# Placeholder subcommand groups for future implementation


profiles_app = typer.Typer(help="Manage device profiles")
app.add_typer(profiles_app, name="profiles")


@profiles_app.command("list")
def profiles_list() -> None:
    """List all profiles."""
    console.print("[yellow]Not yet implemented[/yellow]")
    raise typer.Exit(code=1)


@profiles_app.command("show")
def profiles_show(
    profile_id: Annotated[str, typer.Argument(help="Profile ID to show")],
) -> None:
    """Show details of a specific profile."""
    console.print(f"[yellow]Not yet implemented: show profile {profile_id}[/yellow]")
    raise typer.Exit(code=1)


builders_app = typer.Typer(help="Manage Image Builder cache")
app.add_typer(builders_app, name="builders")


@builders_app.command("list")
def builders_list() -> None:
    """List cached Image Builders."""
    console.print("[yellow]Not yet implemented[/yellow]")
    raise typer.Exit(code=1)


@builders_app.command("ensure")
def builders_ensure(
    release: Annotated[str, typer.Argument(help="OpenWrt release version")],
    target: Annotated[str, typer.Argument(help="Target platform")],
    subtarget: Annotated[str, typer.Argument(help="Subtarget")],
) -> None:
    """Ensure an Image Builder is available."""
    console.print(
        f"[yellow]Not yet implemented: ensure builder {release}/{target}/{subtarget}[/yellow]"
    )
    raise typer.Exit(code=1)


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
