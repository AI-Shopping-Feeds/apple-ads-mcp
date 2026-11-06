"""CLI entrypoint exposed as the `apple-ads-mcp` console script.

Subcommands:

* `apple-ads-mcp run`       (default) start the MCP server.
* `apple-ads-mcp keygen`    create the EC P-256 key pair in ~/.apple-ads-mcp/secrets;
                            prints the public key to paste into Apple Ads. The
                            private key never leaves disk.
* `apple-ads-mcp purge`     delete the audit log (tokens are memory-only).
* `apple-ads-mcp describe`  print the effective configuration (no secrets).
* `apple-ads-mcp version`   print the package version.
"""

from __future__ import annotations

import ipaddress
import json
import sys
from pathlib import Path

import click

from . import __version__
from ._logging import configure_default, get_logger
from .config import TRANSPORTS, load_audit_settings, load_config
from .paths import (
    PRIVATE_KEY_NAME,
    PUBLIC_KEY_NAME,
    chmod_private,
    default_private_key_path,
    default_secrets_dir,
    ensure_private_dir,
    write_private,
)
from .server import build_server

logger = get_logger("cli")


def is_loopback(host: str) -> bool:
    """True for localhost and loopback addresses (127.0.0.0/8, ::1)."""
    name = host.strip().strip("[]").lower()
    if name == "localhost":
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


@click.group(invoke_without_command=True)
@click.option(
    "--env",
    "env_file",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Path to a .env file. Defaults to ./.env, then ~/.apple-ads-mcp/.env.",
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
@click.option(
    "--allow-remote",
    is_flag=True,
    default=False,
    help="Allow an HTTP transport to bind to a non-loopback host (same as "
    "APPLE_ADS_ALLOW_REMOTE=true). The server has no sign-in: don't.",
)
@click.pass_context
def cli(
    ctx: click.Context,
    env_file: Path | None,
    transport: str | None,
    host: str | None,
    port: int | None,
    allow_remote: bool,
) -> None:
    """Apple Ads MCP server."""
    ctx.ensure_object(dict)
    ctx.obj["env_file"] = env_file
    ctx.obj["transport"] = transport
    ctx.obj["host"] = host
    ctx.obj["port"] = port
    ctx.obj["allow_remote"] = allow_remote
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
    if ctx.obj.get("host") is not None:
        config.host = ctx.obj["host"]
    if ctx.obj.get("port") is not None:
        config.port = ctx.obj["port"]
    if ctx.obj.get("allow_remote"):
        config.allow_remote = True

    if config.transport != "stdio" and not is_loopback(config.host):
        if not config.allow_remote:
            raise click.ClickException(
                f"Refusing to serve {config.transport} on {config.host!r}: the server has no "
                "sign-in, so anyone who can reach that address could use your Apple Ads "
                "credentials and spend your budget. Use 127.0.0.1 (the default), or set "
                "APPLE_ADS_ALLOW_REMOTE=true (or pass --allow-remote) if you have put your own "
                "authentication in front of it."
            )
        logger.warning(
            "binding to %s: the server has no authentication, so anyone who can reach "
            "this address can use your Apple Ads credentials and spend your budget",
            config.host,
        )

    mcp = build_server(config=config)

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


@cli.command()
@click.option(
    "--dir",
    "out_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Folder for private-key.pem and public-key.pem "
    "(default ~/.apple-ads-mcp/secrets). Keep it out of git.",
)
@click.option("--force", is_flag=True, help="Overwrite an existing key pair.")
def keygen(out_dir: Path | None, force: bool) -> None:
    """Create an EC P-256 key pair for the Apple Ads API user.

    Writes private-key.pem (mode 600) and public-key.pem to
    ~/.apple-ads-mcp/secrets (mode 700), then prints the public key. Paste it
    into Apple Ads > Account Settings > API while signed in as the API user.
    The private key is never printed or logged.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    out_dir = (out_dir or default_secrets_dir()).expanduser().resolve()
    private_path = out_dir / PRIVATE_KEY_NAME
    public_path = out_dir / PUBLIC_KEY_NAME
    if private_path.exists() and not force:
        raise click.ClickException(
            f"{private_path} already exists. Use --force to replace it (you'll have to "
            "upload the new public key to Apple Ads and update APPLE_ADS_KEY_ID)."
        )
    ensure_private_dir(out_dir)
    chmod_private(out_dir, 0o700)

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
    write_private(private_path, private_pem)
    public_path.write_bytes(public_pem)

    click.echo(f"Private key saved to {private_path} (mode 600). Keep it secret.")
    click.echo(f"Public key saved to {public_path}.\n")
    click.echo("Paste this public key into Apple Ads > Account Settings > API:\n")
    click.echo(public_pem.decode("ascii"))
    click.echo(f"Then set APPLE_ADS_PRIVATE_KEY_PATH={private_path}")
    if private_path == default_private_key_path().resolve():
        click.echo("(The server also looks there by default if the variable isn't set.)")


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
        "allow_remote": config.allow_remote,
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
