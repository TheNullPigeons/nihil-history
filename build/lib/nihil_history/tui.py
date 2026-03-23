from __future__ import annotations

from dataclasses import dataclass

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static, TabPane, TabbedContent

from nihil_history.services import (
    MissingEngagementError,
    access_link,
    access_list,
    access_remove,
    access_update,
    creds_add,
    creds_list,
    creds_remove,
    creds_set,
    creds_update,
    hosts_add,
    hosts_list,
    hosts_remove,
    hosts_set,
    hosts_update,
)


@dataclass(slots=True)
class SelectionState:
    creds: list = None
    hosts: list = None
    links: list = None


class QuickInputScreen(ModalScreen[str | None]):
    CSS = """
    QuickInputScreen {
      align: center middle;
    }
    #dialog {
      width: 80;
      height: auto;
      border: round $accent;
      padding: 1;
      background: $panel;
    }
    #row {
      height: auto;
      margin-top: 1;
    }
    Button {
      margin-right: 1;
    }
    """

    def __init__(self, title: str, placeholder: str) -> None:
        super().__init__()
        self.title = title
        self.placeholder = placeholder

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Label(self.title)
            yield Input(placeholder=self.placeholder, id="value")
            with Container(id="row"):
                yield Button("OK", variant="success", id="ok")
                yield Button("Cancel", id="cancel")

    @on(Button.Pressed, "#ok")
    def _ok(self) -> None:
        value = self.query_one("#value", Input).value.strip()
        self.dismiss(value or None)

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)


class NihilHistoryTUI(App[None]):
    TITLE = "nxh tui"
    SUB_TITLE = "Credentials, hosts, and access matrix"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("1", "tab_creds", "Credentials"),
        Binding("2", "tab_hosts", "Hosts"),
        Binding("3", "tab_matrix", "Matrix"),
        Binding("a", "add_item", "Add"),
        Binding("d", "delete_item", "Delete"),
        Binding("e", "edit_item", "Edit"),
        Binding("s", "set_item", "Set"),
        Binding("l", "link_item", "Link"),
        Binding("enter", "show_details", "Details"),
    ]

    CSS = """
    Screen {
      layout: vertical;
    }
    #status {
      height: 1;
      content-align: left middle;
      color: $text-muted;
      margin-left: 1;
    }
    """

    def compose(self) -> ComposeResult:
        self.state = SelectionState(creds=[], hosts=[], links=[])
        yield Header()
        with Container():
            yield Static("Ready", id="status")
            with TabbedContent(initial="creds"):
                with TabPane("Credentials", id="creds"):
                    yield DataTable(id="creds_table")
                with TabPane("Hosts", id="hosts"):
                    yield DataTable(id="hosts_table")
                with TabPane("Access Matrix", id="matrix"):
                    yield DataTable(id="matrix_table")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_all()

    def action_refresh(self) -> None:
        self._refresh_all()

    def action_tab_creds(self) -> None:
        self.query_one(TabbedContent).active = "creds"

    def action_tab_hosts(self) -> None:
        self.query_one(TabbedContent).active = "hosts"

    def action_tab_matrix(self) -> None:
        self.query_one(TabbedContent).active = "matrix"

    def action_add_item(self) -> None:
        active = self.query_one(TabbedContent).active
        if active == "creds":
            self.push_screen(
                QuickInputScreen("Add credential: username,secret,domain,type", "admin,P@ss,ACME.LOCAL,password"),
                callback=self._on_add_cred,
            )
        elif active == "hosts":
            self.push_screen(
                QuickInputScreen("Add host: ip,hostname,domain,os", "10.10.10.10,DC01,ACME.LOCAL,Windows Server"),
                callback=self._on_add_host,
            )
        else:
            self._set_status("Use 'l' to add an access link from matrix tab.")
            return

    def action_delete_item(self) -> None:
        active = self.query_one(TabbedContent).active
        if active == "creds":
            selected = self._selected_cred()
            if selected is None:
                return
            self.push_screen(
                QuickInputScreen(f"Delete credential id={selected.id}? Type YES", "YES"),
                callback=lambda raw: self._confirm_delete(raw, "creds", selected.id),
            )
        elif active == "hosts":
            selected = self._selected_host()
            if selected is None:
                return
            self.push_screen(
                QuickInputScreen(f"Delete host id={selected.id}? Type YES", "YES"),
                callback=lambda raw: self._confirm_delete(raw, "hosts", selected.id),
            )
        elif active == "matrix":
            selected = self._selected_link()
            if selected is None:
                self._set_status("No access row selected.")
                return
            self.push_screen(
                QuickInputScreen(f"Delete link id={selected.id}? Type YES", "YES"),
                callback=lambda raw: self._confirm_delete(raw, "matrix", selected.id),
            )

    def action_edit_item(self) -> None:
        active = self.query_one(TabbedContent).active
        if active == "creds":
            selected = self._selected_cred()
            if selected is None:
                return
            default = f"{selected.username},{selected.secret or ''},{selected.domain or ''},{selected.cred_type}"
            self.push_screen(
                QuickInputScreen("Edit credential: username,secret,domain,type", default),
                callback=lambda raw: self._on_edit_cred(raw, selected.id),
            )
        elif active == "hosts":
            selected = self._selected_host()
            if selected is None:
                return
            default = f"{selected.ip},{selected.hostname or ''},{selected.domain or ''},{selected.operating_system or ''}"
            self.push_screen(
                QuickInputScreen("Edit host: ip,hostname,domain,os", default),
                callback=lambda raw: self._on_edit_host(raw, selected.id),
            )
        elif active == "matrix":
            selected = self._selected_link()
            if selected is None:
                return
            default = f"{selected.cred_id},{selected.host_id},{selected.protocol},{selected.status}"
            self.push_screen(
                QuickInputScreen("Edit link: cred_id,host_id,protocol,status", default),
                callback=lambda raw: self._on_edit_link(raw, selected.id),
            )

    def action_set_item(self) -> None:
        active = self.query_one(TabbedContent).active
        if active == "creds":
            selected = self._selected_cred()
            if selected is None:
                return
            creds_set(selected.id)
            self._set_status(f"Selected credential id={selected.id}")
        elif active == "hosts":
            selected = self._selected_host()
            if selected is None:
                return
            hosts_set(selected.id)
            self._set_status(f"Selected host id={selected.id}")
        else:
            self._set_status("Set is available on credentials and hosts tabs.")
            return
        self._refresh_all()

    def action_link_item(self) -> None:
        self.push_screen(
            QuickInputScreen("Create link: cred_id,host_id,protocol,status", "1,2,smb,valid"),
            callback=self._on_add_link,
        )

    def action_show_details(self) -> None:
        active = self.query_one(TabbedContent).active
        if active == "creds":
            selected = self._selected_cred()
            if selected:
                self._set_status(f"cred id={selected.id} user={selected.username} type={selected.cred_type}")
        elif active == "hosts":
            selected = self._selected_host()
            if selected:
                self._set_status(f"host id={selected.id} ip={selected.ip} hostname={selected.hostname or '-'}")
        else:
            selected = self._selected_link()
            if selected:
                self._set_status(
                    f"link id={selected.id} cred={selected.cred_id} host={selected.host_id} {selected.protocol}/{selected.status}"
                )

    def _set_status(self, value: str) -> None:
        self.query_one("#status", Static).update(value)

    def _on_add_cred(self, raw: str | None) -> None:
        if not raw:
            return
        try:
            username, secret, domain, cred_type = self._parse_csv(raw, 4)
            if not username:
                self._set_status("Username is required.")
                return
            creds_add(username=username, secret=secret or None, domain=domain or None, cred_type=cred_type or "password")
            self._refresh_all()
        except Exception as exc:
            self._set_status(f"Add credential failed: {exc}")

    def _on_add_host(self, raw: str | None) -> None:
        if not raw:
            return
        try:
            ip, hostname, domain, os_name = self._parse_csv(raw, 4)
            if not ip:
                self._set_status("IP is required.")
                return
            hosts_add(ip=ip, hostname=hostname or None, domain=domain or None, operating_system=os_name or None)
            self._refresh_all()
        except Exception as exc:
            self._set_status(f"Add host failed: {exc}")

    def _on_add_link(self, raw: str | None) -> None:
        if not raw:
            return
        try:
            cred_id, host_id, protocol, status = self._parse_csv(raw, 4)
            access_link(cred_id=int(cred_id), host_id=int(host_id), protocol=protocol, status=status or "unknown")
            self._refresh_all()
        except Exception as exc:
            self._set_status(f"Create link failed: {exc}")

    def _on_edit_cred(self, raw: str | None, cred_id: int) -> None:
        if not raw:
            return
        try:
            username, secret, domain, cred_type = self._parse_csv(raw, 4)
            if not username:
                self._set_status("Username is required.")
                return
            creds_update(
                cred_id=cred_id,
                username=username,
                secret=secret or None,
                domain=domain or None,
                cred_type=cred_type or "password",
            )
            self._refresh_all()
        except Exception as exc:
            self._set_status(f"Edit credential failed: {exc}")

    def _on_edit_host(self, raw: str | None, host_id: int) -> None:
        if not raw:
            return
        try:
            ip, hostname, domain, os_name = self._parse_csv(raw, 4)
            if not ip:
                self._set_status("IP is required.")
                return
            hosts_update(
                host_id=host_id,
                ip=ip,
                hostname=hostname or None,
                domain=domain or None,
                operating_system=os_name or None,
            )
            self._refresh_all()
        except Exception as exc:
            self._set_status(f"Edit host failed: {exc}")

    def _on_edit_link(self, raw: str | None, link_id: int) -> None:
        if not raw:
            return
        try:
            cred_id, host_id, protocol, status = self._parse_csv(raw, 4)
            access_update(
                link_id=link_id,
                cred_id=int(cred_id),
                host_id=int(host_id),
                protocol=protocol,
                status=status or "unknown",
            )
            self._refresh_all()
        except Exception as exc:
            self._set_status(f"Edit link failed: {exc}")

    def _confirm_delete(self, raw: str | None, entity: str, entity_id: int) -> None:
        if (raw or "").upper() != "YES":
            self._set_status("Delete cancelled.")
            return
        try:
            if entity == "creds":
                creds_remove(entity_id)
            elif entity == "hosts":
                hosts_remove(entity_id)
            else:
                access_remove(entity_id)
            self._refresh_all()
        except Exception as exc:
            self._set_status(f"Delete failed: {exc}")

    def _refresh_all(self) -> None:
        try:
            creds = creds_list()
            hosts = hosts_list()
            links = access_list()
        except MissingEngagementError as exc:
            self._set_status(str(exc))
            self._render_empty()
            return

        self.state.creds = creds
        self.state.hosts = hosts
        self.state.links = links
        self._render_creds(creds)
        self._render_hosts(hosts)
        self._render_matrix(links)
        self._set_status(
            "Loaded: "
            f"creds={len(creds)} hosts={len(hosts)} links={len(links)} | "
            "Keys: 1/2/3 switch, a add, e edit, d delete, s set, l link, Enter details, r refresh, q quit"
        )

    def _render_empty(self) -> None:
        for table_id in ("creds_table", "hosts_table", "matrix_table"):
            table = self.query_one(f"#{table_id}", DataTable)
            table.clear(columns=True)
            table.add_column("Info")
            table.add_row("No active engagement.")

    def _render_creds(self, creds: list) -> None:
        table = self.query_one("#creds_table", DataTable)
        table.clear(columns=True)
        table.add_column("ID")
        table.add_column("Username")
        table.add_column("Domain")
        table.add_column("Type")
        table.add_column("Source")
        for cred in creds:
            table.add_row(str(cred.id), cred.username, cred.domain or "-", cred.cred_type, cred.source)

    def _render_hosts(self, hosts: list) -> None:
        table = self.query_one("#hosts_table", DataTable)
        table.clear(columns=True)
        table.add_column("ID")
        table.add_column("IP")
        table.add_column("Hostname")
        table.add_column("Domain")
        table.add_column("OS")
        for host in hosts:
            table.add_row(str(host.id), host.ip, host.hostname or "-", host.domain or "-", host.operating_system or "-")

    def _render_matrix(self, links: list) -> None:
        table = self.query_one("#matrix_table", DataTable)
        table.clear(columns=True)
        table.add_column("LinkID")
        table.add_column("Cred")
        table.add_column("Host")
        table.add_column("Protocol")
        table.add_column("Status")
        for link in links:
            table.add_row(str(link.id), str(link.cred_id), str(link.host_id), link.protocol, link.status)

    def _selected_cred(self):
        table = self.query_one("#creds_table", DataTable)
        idx = table.cursor_row
        if idx is None or idx < 0 or idx >= len(self.state.creds):
            self._set_status("No credential row selected.")
            return None
        return self.state.creds[idx]

    def _selected_host(self):
        table = self.query_one("#hosts_table", DataTable)
        idx = table.cursor_row
        if idx is None or idx < 0 or idx >= len(self.state.hosts):
            self._set_status("No host row selected.")
            return None
        return self.state.hosts[idx]

    def _selected_link(self):
        table = self.query_one("#matrix_table", DataTable)
        idx = table.cursor_row
        if idx is None or idx < 0 or idx >= len(self.state.links):
            self._set_status("No access row selected.")
            return None
        return self.state.links[idx]

    @staticmethod
    def _parse_csv(raw: str, expected: int) -> list[str]:
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) < expected:
            parts.extend([""] * (expected - len(parts)))
        return parts[:expected]
