"""CLI entrypoint exposed as the `apple-ads-mcp` console script.

Subcommands:

* `apple-ads-mcp run`       (default) start the MCP server.
* `apple-ads-mcp keygen`    create the EC P-256 key pair; prints the public key to
                            paste into Apple Ads. The private key never leaves disk.
* `apple-ads-mcp purge`     delete the audit log (tokens are memory-only).
* `apple-ads-mcp describe`  print the effective configuration (no secrets).
* `apple-ads-mcp version`   print the package version.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click

from . import __version__
from ._logging import configure_default, get_logger
from .config import TRANSPORTS, load_audit_settings, load_config
from .server import build_server

logger = get_logger("cli")

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


@click.group(invoke_without_command=True)
@click.option(
    "--env",
    "env_file",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Path to a .env file. Defaults to ./.env.",
)
@click.option(
    "--transport",
    type=click.Choice(TRANSPORTS),
    default=None,
    help="Override APPLE_ADS_TRANSPORT. 'sse' is deprecated; use 'streamable-http'.",
)
@click.option(
    "--host", default=None, help="Bind host for streamable-http / sse (default 127.0.0.1)."
)
@click.option(
    "--port", type=int, default=None, help="Bind port for streamable-http / sse (default 8000)."
)
@click.pass_context
def cli(
    ctx: click.Context,
    env_file: Path | None,
    transport: str | None,
    host: str | None,
    port: int | None,
) -> None:
    """Apple Ads MCP server."""
    ctx.ensure_object(dict)
    ctx.obj["env_file"] = env_file
    ctx.obj["transport"] = transport
    ctx.obj["host"] = host
    ctx.obj["port"] = port
    if ctx.invoked_subcommand is None:
        ctx.invoke(run)


@cli.command()
@click.pass_context
def run(ctx: click.Context) -> None:
    """Start the MCP server (default subcommand)."""
    configure_default()
    config = load_config(env_file=ctx.obj.get("env_file"))
    if ctx.obj.get("transport"):
        config.transport = ctx.obj["transport"]
    if ctx.obj.get("host"):
        config.host = ctx.obj["host"]
    if ctx.obj.get("port"):
        config.port = ctx.obj["port"]

    mcp = build_server(config=config)

    if config.transport != "stdio" and config.host not in _LOOPBACK_HOSTS:
        logger.warning(
            "binding to %s: the server has no authentication, so anyone who can reach "
            "this address can use your Apple Ads credentials and spend your budget",
            config.host,
        )
    if config.transport == "stdio":
        mcp.run("stdio")
    elif config.transport == "streamable-http":
        logger.info("serving streamable HTTP on http://%s:%d/mcp", config.host, config.port)
        mcp.run("streamable-http", host=config.host, port=config.port)
    elif config.transport == "sse":
        logger.warning(
            "the sse transport (HTTP+SSE) is deprecated by the MCP spec; "
            "use --transport streamable-http instead"
        )
        mcp.run("sse", host=config.host, port=config.port)
    else:
        raise click.ClickException(f"Unknown transport: {config.transport}")


def _write_private(path: Path, data: bytes) -> None:
    """Create `path` with mode 0600 from the start (no window where it's world-readable)."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    if os.name == "posix":
        path.chmod(0o600)


@cli.command()
@click.option(
    "--dir",
    "out_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("secrets"),
    show_default=True,
    help="Folder for private-key.pem and public-key.pem (keep it out of git).",
)
@click.option("--force", is_flag=True, help="Overwrite an existing key pair.")
def keygen(out_dir: Path, force: bool) -> None:
    """Create an EC P-256 key pair for the Apple Ads API user.

    Writes private-key.pem (mode 600) and public-key.pem, then prints the public
    key. Paste it into Apple Ads > Account Settings > API while signed in as the
    API user. The private key is never printed or logged.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    private_path = out_dir / "private-key.pem"
    public_path = out_dir / "public-key.pem"
    if private_path.exists() and not force:
        raise click.ClickException(
            f"{private_path} already exists. Use --force to replace it (you'll have to "
            "upload the new public key to Apple Ads and update APPLE_ADS_KEY_ID)."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        out_dir.chmod(0o700)

    key = ec.generate_private_key(ec.SECP256R1())
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    _write_private(private_path, private_pem)
    public_path.write_bytes(public_pem)

    click.echo(f"Private key saved to {private_path.resolve()} (mode 600). Keep it secret.")
    click.echo(f"Public key saved to {public_path.resolve()}.\n")
    click.echo("Paste this public key into Apple Ads > Account Settings > API:\n")
    click.echo(public_pem.decode("ascii"))
    click.echo(f"Then set APPLE_ADS_PRIVATE_KEY_PATH={private_path.resolve()}")


@cli.command()
@click.option("--yes", is_flag=True, help="Don't ask for confirmation.")
@click.pass_context
def purge(ctx: click.Context, yes: bool) -> None:
    """Delete the local audit log.

    Access tokens and client secrets are held in memory only and are gone when
    the server stops, so there is no token cache to delete. Your private key is
    not touched: delete it yourself (and revoke it in Apple Ads) if you no
    longer need API access.
    """
    path, _ = load_audit_settings(ctx.obj.get("env_file"))
    if not yes and not click.confirm(f"Delete the audit log at {path}?", default=False):
        click.echo("Nothing deleted.")
        return
    from .audit import AuditLog

    removed = AuditLog(path).purge()
    for extra in (path.with_suffix(path.suffix + ".tmp"),):
        if extra.exists():
            extra.unlink()
    click.echo(f"Deleted {path}." if removed else f"No audit log at {path}.")
    click.echo("Tokens are memory-only: nothing else to delete.")


@cli.command()
def version() -> None:
    """Print the apple-ads-mcp version."""
    click.echo(__version__)


@cli.command("describe")
@click.pass_context
def describe(ctx: click.Context) -> None:
    """Print the effective config (no secrets) and exit. Useful for debugging."""
    configure_default()
    config = load_config(env_file=ctx.obj.get("env_file"))
    info = {
        "version": __version__,
        "client_id": config.client_id[:18] + "…",
        "private_key_path": str(config.private_key_path),
        "ad_account_id": config.ad_account_id,
        "audit_log": str(config.audit_log),
        "audit_retention_days": config.audit_retention_days,
        "max_increase_pct": config.max_increase_pct,
        "dry_run": config.dry_run,
        "read_only": config.read_only,
        "tool_groups": config.tool_groups or "all",
        "transport": config.transport,
        "host": config.host,
        "port": config.port,
    }
    click.echo(json.dumps(info, indent=2, ensure_ascii=False))


def main() -> None:
    try:
        cli(obj={})
    except RuntimeError as e:
        # Surface config errors cleanly instead of a Python traceback.
        click.echo(f"Error: {e}", err=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
