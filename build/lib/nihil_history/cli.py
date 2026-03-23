from __future__ import annotations

from pathlib import Path
import sys

import typer
from rich.console import Console
from rich.table import Table

from nihil_history.db import init_db
from nihil_history.services import (
    MissingEngagementError,
    access_link,
    access_list,
    access_matrix,
    access_remove,
    creds_add,
    creds_remove,
    creds_set,
    creds_list,
    engagement_init,
    engagement_list,
    engagement_use,
    env_exports,
    export_report_json,
    export_report_markdown,
    hosts_add,
    hosts_remove,
    hosts_set,
    hosts_list,
)
from nihil_history.sync_nmap import import_nmap_xml
from nihil_history.sync_nxc import import_nxc_text
from nihil_history.tui import NihilHistoryTUI

app = typer.Typer(no_args_is_help=True, help="nihil-history CLI")
engagement_app = typer.Typer(no_args_is_help=True, help="Manage engagements.")
creds_app = typer.Typer(no_args_is_help=True, help="Manage credentials.")
hosts_app = typer.Typer(no_args_is_help=True, help="Manage hosts.")
access_app = typer.Typer(no_args_is_help=True, help="Manage access links.")
env_app = typer.Typer(no_args_is_help=True, help="Print environment exports.")
sync_app = typer.Typer(no_args_is_help=True, help="Synchronize from external tools.")
export_app = typer.Typer(no_args_is_help=True, help="Export engagement reports.")
console = Console()


def _handle_missing_engagement(exc: MissingEngagementError) -> None:
    console.print(f"[red]{exc}[/red]")
    raise typer.Exit(code=1)


@app.callback()
def main() -> None:
    binary_name = Path(sys.argv[0]).name
    if binary_name == "nxh":
        console.print("[yellow]Deprecated alias:[/yellow] use `nhi` instead of `nxh`.")
    init_db()


app.add_typer(engagement_app, name="engagement")
app.add_typer(creds_app, name="creds")
app.add_typer(hosts_app, name="hosts")
app.add_typer(access_app, name="access")
app.add_typer(env_app, name="env")
app.add_typer(sync_app, name="sync")
app.add_typer(export_app, name="export")


@engagement_app.command("init")
def cmd_engagement_init(name: str) -> None:
    entry = engagement_init(name)
    console.print(f"[green]Engagement ready:[/green] {entry.name}")


@engagement_app.command("use")
def cmd_engagement_use(name: str) -> None:
    try:
        entry = engagement_use(name)
    except MissingEngagementError as exc:
        _handle_missing_engagement(exc)
    console.print(f"[green]Active engagement:[/green] {entry.name}")


@engagement_app.command("list")
def cmd_engagement_list() -> None:
    entries = engagement_list()
    table = Table(title="Engagements")
    table.add_column("ID")
    table.add_column("Name")
    table.add_column("Created")
    for entry in entries:
        table.add_row(str(entry.id), entry.name, entry.created_at.isoformat())
    console.print(table)


@creds_app.command("add")
def cmd_creds_add(
    username: str = typer.Option(..., "--username", "-u"),
    secret: str | None = typer.Option(None, "--secret", "-p", help="Password/hash/token."),
    domain: str | None = typer.Option(None, "--domain", "-d"),
    cred_type: str = typer.Option("password", "--type"),
) -> None:
    try:
        cred = creds_add(username=username, secret=secret, domain=domain, cred_type=cred_type)
    except MissingEngagementError as exc:
        _handle_missing_engagement(exc)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Credential added:[/green] id={cred.id} user={cred.username}")


@creds_app.command("list")
def cmd_creds_list() -> None:
    try:
        entries = creds_list()
    except MissingEngagementError as exc:
        _handle_missing_engagement(exc)
    table = Table(title="Credentials")
    table.add_column("ID")
    table.add_column("Username")
    table.add_column("Domain")
    table.add_column("Type")
    table.add_column("Source")
    for cred in entries:
        table.add_row(str(cred.id), cred.username, cred.domain or "-", cred.cred_type, cred.source)
    console.print(table)


@creds_app.command("set")
def cmd_creds_set(cred_id: int = typer.Option(..., "--id")) -> None:
    try:
        cred = creds_set(cred_id)
    except MissingEngagementError as exc:
        _handle_missing_engagement(exc)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Selected credential:[/green] id={cred.id} user={cred.username}")


@creds_app.command("rm")
def cmd_creds_rm(cred_id: int = typer.Option(..., "--id")) -> None:
    try:
        creds_remove(cred_id)
    except MissingEngagementError as exc:
        _handle_missing_engagement(exc)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Credential removed:[/green] id={cred_id}")


@hosts_app.command("add")
def cmd_hosts_add(
    ip: str = typer.Option(..., "--ip"),
    hostname: str | None = typer.Option(None, "--hostname"),
    domain: str | None = typer.Option(None, "--domain"),
    os_name: str | None = typer.Option(None, "--os"),
) -> None:
    try:
        host = hosts_add(ip=ip, hostname=hostname, domain=domain, operating_system=os_name)
    except MissingEngagementError as exc:
        _handle_missing_engagement(exc)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Host added:[/green] id={host.id} ip={host.ip}")


@hosts_app.command("list")
def cmd_hosts_list() -> None:
    try:
        entries = hosts_list()
    except MissingEngagementError as exc:
        _handle_missing_engagement(exc)
    table = Table(title="Hosts")
    table.add_column("ID")
    table.add_column("IP")
    table.add_column("Hostname")
    table.add_column("Domain")
    table.add_column("OS")
    for host in entries:
        table.add_row(str(host.id), host.ip, host.hostname or "-", host.domain or "-", host.operating_system or "-")
    console.print(table)


@hosts_app.command("set")
def cmd_hosts_set(host_id: int = typer.Option(..., "--id")) -> None:
    try:
        host = hosts_set(host_id)
    except MissingEngagementError as exc:
        _handle_missing_engagement(exc)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Selected host:[/green] id={host.id} ip={host.ip}")


@hosts_app.command("rm")
def cmd_hosts_rm(host_id: int = typer.Option(..., "--id")) -> None:
    try:
        hosts_remove(host_id)
    except MissingEngagementError as exc:
        _handle_missing_engagement(exc)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Host removed:[/green] id={host_id}")


@hosts_app.command("import-nmap")
def cmd_hosts_import_nmap(file: str = typer.Option(..., "--file", "-f")) -> None:
    try:
        result = import_nmap_xml(file)
    except FileNotFoundError:
        console.print(f"[red]File not found:[/red] {file}")
        raise typer.Exit(code=1)
    except MissingEngagementError as exc:
        _handle_missing_engagement(exc)
    except Exception as exc:
        console.print(f"[red]Invalid Nmap XML:[/red] {exc}")
        raise typer.Exit(code=1)
    console.print(f"[green]Nmap import complete:[/green] hosts={result['hosts']}")


@access_app.command("link")
def cmd_access_link(
    cred_id: int = typer.Option(..., "--cred-id"),
    host_id: int = typer.Option(..., "--host-id"),
    protocol: str = typer.Option(..., "--protocol"),
    status: str = typer.Option("unknown", "--status"),
) -> None:
    try:
        link = access_link(cred_id=cred_id, host_id=host_id, protocol=protocol, status=status)
    except MissingEngagementError as exc:
        _handle_missing_engagement(exc)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Access linked:[/green] id={link.id} cred={cred_id} host={host_id} {protocol}/{status}")


@access_app.command("list")
def cmd_access_list() -> None:
    try:
        entries = access_list()
    except MissingEngagementError as exc:
        _handle_missing_engagement(exc)
    table = Table(title="Access Links")
    table.add_column("ID")
    table.add_column("Cred")
    table.add_column("Host")
    table.add_column("Protocol")
    table.add_column("Status")
    table.add_column("Source")
    for link in entries:
        table.add_row(str(link.id), str(link.cred_id), str(link.host_id), link.protocol, link.status, link.source)
    console.print(table)


@access_app.command("rm")
def cmd_access_rm(link_id: int = typer.Option(..., "--id")) -> None:
    try:
        access_remove(link_id)
    except MissingEngagementError as exc:
        _handle_missing_engagement(exc)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Access link removed:[/green] id={link_id}")


@access_app.command("matrix")
def cmd_access_matrix() -> None:
    try:
        hosts, creds, matrix = access_matrix()
    except MissingEngagementError as exc:
        _handle_missing_engagement(exc)
    table = Table(title="Access Matrix")
    table.add_column("Host \\ Cred")
    for cred in creds:
        table.add_column(f"{cred.id}:{cred.username}", justify="center")
    for host in hosts:
        row = [f"{host.id}:{host.ip}"]
        for cred in creds:
            row.append(matrix.get((host.id, cred.id), "-"))
        table.add_row(*row)
    console.print(table)


@env_app.command("print")
def cmd_env_print(shell: str = typer.Option("bash", "--shell")) -> None:
    export_rows = list(env_exports())
    if shell not in {"bash", "zsh", "fish"}:
        console.print("[red]Unsupported shell. Use bash, zsh, or fish.[/red]")
        raise typer.Exit(code=1)
    for key, value in export_rows:
        escaped = value.replace('"', '\\"')
        if shell == "fish":
            console.print(f'set -gx {key} "{escaped}"')
        else:
            console.print(f'export {key}="{escaped}"')


@sync_app.command("nxc")
def cmd_sync_nxc(file: str = typer.Option(..., "--file", "-f")) -> None:
    try:
        result = import_nxc_text(file)
    except FileNotFoundError:
        console.print(f"[red]File not found:[/red] {file}")
        raise typer.Exit(code=1)
    except MissingEngagementError as exc:
        _handle_missing_engagement(exc)
    console.print(
        f"[green]NXC sync complete:[/green] creds={result['creds']} hosts={result['hosts']} links={result['links']}"
    )


@app.command("tui")
def cmd_tui() -> None:
    NihilHistoryTUI().run()


@export_app.command("json")
def cmd_export_json(
    output: str | None = typer.Option(None, "--output", "-o"),
    include_secrets: bool = typer.Option(False, "--include-secrets"),
) -> None:
    try:
        payload = export_report_json(include_secrets=include_secrets)
    except MissingEngagementError as exc:
        _handle_missing_engagement(exc)
    if output:
        Path(output).write_text(payload, encoding="utf-8")
        console.print(f"[green]JSON report written:[/green] {output}")
        return
    console.print(payload)


@export_app.command("markdown")
def cmd_export_markdown(
    output: str | None = typer.Option(None, "--output", "-o"),
    include_secrets: bool = typer.Option(False, "--include-secrets"),
) -> None:
    try:
        payload = export_report_markdown(include_secrets=include_secrets)
    except MissingEngagementError as exc:
        _handle_missing_engagement(exc)
    if output:
        Path(output).write_text(payload, encoding="utf-8")
        console.print(f"[green]Markdown report written:[/green] {output}")
        return
    console.print(payload)
