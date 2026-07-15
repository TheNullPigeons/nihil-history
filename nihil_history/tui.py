from __future__ import annotations

from dataclasses import dataclass

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.coordinate import Coordinate
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Static, TabPane, TabbedContent

from nihil_history.config import load_config
from nihil_history.services import (
    MissingEngagementError,
    ensure_default_engagement,
    access_link,
    access_list,
    access_remove,
    access_update,
    creds_add,
    creds_list,
    creds_remove,
    creds_set,
    creds_update,
    engagement_delete,
    engagement_init,
    engagement_list,
    engagement_merge,
    engagement_rename,
    hosts_add,
    hosts_list,
    hosts_remove,
    hosts_set,
    hosts_update,
    require_engagement,
    targets_add,
    targets_list,
    targets_remove,
    targets_set,
    targets_update,
)
from nihil_history.sync_nxc import nxc_delete_credential, nxc_delete_host
from nihil_history.validators import (
    ALLOWED_PROTOCOLS,
    ALLOWED_STATUS,
)


@dataclass(slots=True)
class SelectionState:
    creds: list = None
    hosts: list = None
    links: list = None
    targets: list = None


class QuickInputScreen(ModalScreen[str | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+c", "cancel", "Cancel"),
    ]
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

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#ok")
    def _ok(self) -> None:
        value = self.query_one("#value", Input).value.strip()
        self.dismiss(value or None)

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)


class MultiFieldScreen(ModalScreen[list[str] | None]):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+c", "cancel", "Cancel"),
    ]
    CSS = """
    MultiFieldScreen {
      align: center middle;
    }
    #dialog {
      width: 80;
      height: auto;
      border: round $accent;
      padding: 1;
      background: $panel;
    }
    .field-label {
      color: $text-muted;
      margin-top: 1;
    }
    #row {
      height: auto;
      margin-top: 1;
    }
    Button {
      margin-right: 1;
    }
    """

    def __init__(self, title: str, fields: list[tuple[str, str, str]]) -> None:
        """fields: list of (label, placeholder, default_value)"""
        super().__init__()
        self._title = title
        self.fields = fields

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Label(self._title)
            for i, (label, placeholder, default) in enumerate(self.fields):
                yield Label(label, classes="field-label")
                yield Input(placeholder=placeholder, value=default, id=f"field_{i}")
            with Container(id="row"):
                yield Button("OK", variant="success", id="ok")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#field_0", Input).focus()

    @on(Button.Pressed, "#ok")
    def _ok(self) -> None:
        self.dismiss(self._collect())

    def action_cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        current_idx = int(event.input.id.split("_")[1])
        next_idx = current_idx + 1
        if next_idx < len(self.fields):
            self.query_one(f"#field_{next_idx}", Input).focus()
        else:
            self.dismiss(self._collect())

    def _collect(self) -> list[str]:
        return [
            self.query_one(f"#field_{i}", Input).value.strip()
            for i in range(len(self.fields))
        ]


class EngagementScreen(ModalScreen[str | None]):
    BINDINGS = [
        Binding("enter", "select_row", "Select"),
        Binding("n", "new_engagement", "New"),
        Binding("r", "rename_engagement", "Rename"),
        Binding("d", "delete_engagement", "Delete"),
        Binding("j", "vi_down", "↓", show=False),
        Binding("k", "vi_up", "↑", show=False),
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+c", "cancel", "Cancel"),
    ]
    CSS = """
    EngagementScreen {
      align: center middle;
    }
    #dialog {
      width: 80;
      height: auto;
      max-height: 30;
      border: round $accent;
      padding: 1;
      background: $panel;
    }
    #title {
      margin-bottom: 1;
    }
    #hint {
      color: $text-muted;
      margin-bottom: 1;
    }
    #eng_table {
      height: auto;
      max-height: 15;
      margin-bottom: 1;
    }
    #row {
      height: auto;
      margin-top: 1;
    }
    Button {
      margin-right: 1;
    }
    """

    def __init__(self, current: str | None, existing: list[str]) -> None:
        super().__init__()
        self.current = current
        self.existing = existing

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Label("Engagement manager", id="title")
            yield Label("Enter / select  |  n new  |  r rename  |  d delete  |  Esc cancel", id="hint")
            yield DataTable(id="eng_table", cursor_type="row")
            with Container(id="row"):
                yield Button("Select", variant="success", id="select")
                yield Button("New", id="new")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self._rebuild_table()
        self.query_one("#eng_table", DataTable).focus()

    def _rebuild_table(self) -> None:
        table = self.query_one("#eng_table", DataTable)
        table.clear(columns=True)
        table.add_column("Engagement")
        table.add_column("Active")
        for name in self.existing:
            table.add_row(name, "✓" if name == self.current else "")

    def _selected_name(self) -> str | None:
        table = self.query_one("#eng_table", DataTable)
        idx = table.cursor_row
        if idx is None or idx < 0 or idx >= len(self.existing):
            return None
        return self.existing[idx]

    @on(Button.Pressed, "#select")
    def _btn_select(self) -> None:
        self.dismiss(self._selected_name())

    @on(Button.Pressed, "#new")
    def _btn_new(self) -> None:
        self.action_new_engagement()

    @on(Button.Pressed, "#cancel")
    def _btn_cancel(self) -> None:
        self.dismiss(None)

    def action_select_row(self) -> None:
        self.dismiss(self._selected_name())

    @on(DataTable.RowSelected, "#eng_table")
    def _row_selected(self, event: DataTable.RowSelected) -> None:
        event.stop()
        self.dismiss(self._selected_name())

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_vi_down(self) -> None:
        table = self.query_one("#eng_table", DataTable)
        table.move_cursor(row=min(table.cursor_row + 1, table.row_count - 1))

    def action_vi_up(self) -> None:
        table = self.query_one("#eng_table", DataTable)
        table.move_cursor(row=max(table.cursor_row - 1, 0))

    def action_new_engagement(self) -> None:
        def _on_name(value: str | None) -> None:
            if not value:
                return
            try:
                engagement_init(value)
                self.existing.append(value)
                self.current = value
                self._rebuild_table()
            except Exception as exc:
                self.notify(str(exc), severity="error", markup=False)

        self.app.push_screen(
            QuickInputScreen("New engagement name", "engagement-name"),
            callback=_on_name,
        )

    def action_rename_engagement(self) -> None:
        name = self._selected_name()
        if name is None:
            return

        def _do_merge(src: str, dst: str) -> None:
            def _confirm(value: str | None) -> None:
                if (value or "").upper() not in ("Y", "YES"):
                    return
                try:
                    engagement_merge(src, dst)
                    self.existing.remove(src)
                    if self.current == src:
                        self.current = dst
                    self._rebuild_table()
                except Exception as exc:
                    self.notify(str(exc), severity="error", markup=False)

            self.app.push_screen(
                QuickInputScreen(f"'{dst}' exists. Merge '{src}' into it? Type y", "y"),
                callback=_confirm,
            )

        def _on_new_name(value: str | None) -> None:
            if not value:
                return
            if value in self.existing:
                _do_merge(name, value)
                return
            try:
                engagement_rename(name, value)
                idx = self.existing.index(name)
                self.existing[idx] = value
                if self.current == name:
                    self.current = value
                self._rebuild_table()
            except Exception as exc:
                self.notify(str(exc), severity="error", markup=False)

        self.app.push_screen(
            QuickInputScreen(f"Rename '{name}' to", name),
            callback=_on_new_name,
        )

    def action_delete_engagement(self) -> None:
        name = self._selected_name()
        if name is None:
            return

        def _confirm(value: str | None) -> None:
            if (value or "").upper() not in ("Y", "YES"):
                return
            try:
                engagement_delete(name)
                self.existing.remove(name)
                if self.current == name:
                    self.current = None
                self._rebuild_table()
            except Exception as exc:
                self.notify(str(exc), severity="error", markup=False)

        self.app.push_screen(
            QuickInputScreen(f"Delete '{name}' and all its data? Type y", "y"),
            callback=_confirm,
        )


class SearchInput(Input):
    """Search bar that treats Tab like Enter: confirm and jump to the table.

    Tab is normally reserved for focus navigation, so pressing it here would
    just move focus one widget at a time (through the tab bar, etc.) instead
    of landing on the results - the muscle-memory "type query, Tab to the
    result" flow otherwise took two Tab presses to work.
    """

    BINDINGS = [Binding("tab", "confirm_search", "Confirm", show=False)]

    def action_confirm_search(self) -> None:
        app = self.app
        app._search_query = self.value.lower()
        app._apply_search()
        app._close_search(clear=False)


class NihilHistoryTUI(App[None]):
    TITLE = "nxh tui"
    SUB_TITLE = "Credentials, hosts, and access matrix"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("ctrl+e", "engagement", "Engagement"),
        Binding("1", "tab_creds", "Credentials"),
        Binding("2", "tab_hosts", "Hosts"),
        Binding("3", "tab_targets", "Targets"),
        Binding("4", "tab_matrix", "Matrix"),
        Binding("a", "add_item", "Add"),
        Binding("d", "delete_item", "Delete"),
        Binding("e", "edit_item", "Edit"),
        Binding("s", "set_item", "Set"),
        Binding("L", "link_item", "Link"),
        Binding("ctrl+d", "toggle_dc", "DC", show=False),
        Binding("v", "visual_toggle", "Visual", show=False),
        Binding("y", "yank", "Yank", show=False),
        Binding("p", "paste", "Paste", show=False),
        Binding("?", "show_allowed_values", "?"),
        Binding("enter", "show_details", "Set+Quit"),
        Binding("j", "vi_down", "↓", show=False),
        Binding("k", "vi_up", "↑", show=False),
        Binding("g", "vi_top", "Top", show=False),
        Binding("G", "vi_bottom", "Bottom", show=False),
        Binding("h", "tab_prev", "◀", show=False),
        Binding("l", "tab_next", "▶", show=False),
        Binding("/", "search_open", "/", show=False),
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
    #search_bar {
      display: none;
      height: 3;
      border: solid $accent;
    }
    Container {
      height: 1fr;
    }
    TabbedContent {
      height: 1fr;
    }
    TabPane {
      height: 1fr;
    }
    DataTable {
      height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        self.state = SelectionState(creds=[], hosts=[], links=[], targets=[])
        self._vis_creds: list = []
        self._vis_hosts: list = []
        self._vis_links: list = []
        self._vis_targets: list = []
        self._search_query: str = ""
        self._visual_mode: bool = False
        self._visual_anchor: int = 0
        self._visual_prev_sel: range | None = None
        yield Header()
        with Container():
            yield Static("Ready", id="status")
            yield SearchInput(id="search_bar", placeholder="/search...")
            with TabbedContent(initial="creds"):
                with TabPane("Credentials", id="creds"):
                    yield DataTable(id="creds_table", cursor_type="row")
                with TabPane("Hosts", id="hosts"):
                    yield DataTable(id="hosts_table", cursor_type="row")
                with TabPane("Targets", id="targets"):
                    yield DataTable(id="targets_table", cursor_type="row")
                with TabPane("Access Matrix", id="matrix"):
                    yield DataTable(id="matrix_table", cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        try:
            ensure_default_engagement()
        except Exception:
            pass
        cfg = load_config()
        if not cfg.current_engagement:
            self._show_engagement_picker()
        else:
            self._refresh_all()
            self.query_one("#creds_table", DataTable).focus()

    def action_refresh(self) -> None:
        self._refresh_all()

    def action_engagement(self) -> None:
        self._show_engagement_picker()

    def _show_engagement_picker(self) -> None:
        try:
            existing = [e.name for e in engagement_list()]
        except Exception:
            existing = []
        current = load_config().current_engagement
        self.push_screen(EngagementScreen(current, existing), callback=self._on_engagement_selected)

    def _on_engagement_selected(self, name: str | None) -> None:
        if not name:
            self._set_status("No engagement selected. Press 'g' to pick one.")
            self._render_empty()
            return
        try:
            engagement_init(name)
            self._refresh_all(status_message=f"Engagement: {name}")
            self.query_one("#creds_table", DataTable).focus()
        except Exception as exc:
            self._set_status(f"Engagement error: {exc}")

    _TABS = ["creds", "hosts", "targets", "matrix"]

    def action_tab_creds(self) -> None:
        self.query_one(TabbedContent).active = "creds"

    def action_tab_hosts(self) -> None:
        self.query_one(TabbedContent).active = "hosts"

    def action_tab_matrix(self) -> None:
        self.query_one(TabbedContent).active = "matrix"

    def action_tab_targets(self) -> None:
        self.query_one(TabbedContent).active = "targets"

    def action_tab_prev(self) -> None:
        tc = self.query_one(TabbedContent)
        idx = self._TABS.index(tc.active) if tc.active in self._TABS else 0
        tc.active = self._TABS[(idx - 1) % len(self._TABS)]
        self._focus_active_table()

    def action_tab_next(self) -> None:
        tc = self.query_one(TabbedContent)
        idx = self._TABS.index(tc.active) if tc.active in self._TABS else 0
        tc.active = self._TABS[(idx + 1) % len(self._TABS)]
        self._focus_active_table()

    def _focus_active_table(self) -> None:
        if t := self._active_table():
            t.focus()

    @on(TabbedContent.TabActivated)
    def _on_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        # The search filter is shared global state across all tabs' lists,
        # so leaving it active after switching tabs silently filters a tab
        # you never searched in (e.g. "/administrator" on creds, then
        # switching to hosts shows nothing because it's still filtering by
        # that query). Any tab change clears it.
        if not self._search_query:
            return
        bar = self.query_one("#search_bar", Input)
        bar.value = ""
        bar.display = False
        self._search_query = ""
        self._apply_search()

    def action_add_item(self) -> None:
        active = self.query_one(TabbedContent).active
        if active == "creds":
            self.push_screen(
                MultiFieldScreen(
                    "Add credential",
                    [
                        ("Username", "admin", ""),
                        ("Password", "P@ssw0rd", ""),
                        ("Hash", "aad3b435b51404ee:...", ""),
                        ("Secret", "token/key/...", ""),
                        ("Domain", "ACME.LOCAL", ""),
                    ],
                ),
                callback=self._on_add_cred,
            )
        elif active == "hosts":
            self.push_screen(
                MultiFieldScreen(
                    "Add host",
                    [
                        ("IP", "10.10.10.10", ""),
                        ("Hostname", "DC01", ""),
                        ("OS", "Windows Server 2022", ""),
                        ("Role  [DC, WS, SRV, WEB, ...]", "DC", ""),
                    ],
                ),
                callback=self._on_add_host,
            )
        elif active == "targets":
            self.push_screen(
                MultiFieldScreen(
                    "Add target",
                    [
                        ("Name *", "admin-hunt", ""),
                        ("User  (TARGET_USER)", "jdoe", ""),
                        ("Group  (TARGET_GROUP)", "Domain Admins", ""),
                        ("Object  (TARGET_OBJECT)", "cn=...", ""),
                        ("Computer  (TARGET_COMPUTER)", "DC01", ""),
                        ("Domain  (TARGET_DOMAIN)", "serval.int", ""),
                        ("Principal  (TARGET_PRINCIPAL)", "S-1-5-21-...", ""),
                    ],
                ),
                callback=self._on_add_target,
            )
        elif active == "matrix":
            self.action_link_item()

    def action_delete_item(self) -> None:
        active = self.query_one(TabbedContent).active
        if self._visual_mode:
            t = self._active_table()
            if t is None:
                return
            sel = self._visual_selection(t)
            if active == "creds":
                items = self._vis_creds[sel.start:sel.stop]
            elif active == "hosts":
                items = self._vis_hosts[sel.start:sel.stop]
            else:
                self._exit_visual_mode()
                return
            if not items:
                self._exit_visual_mode()
                return
            entity = active if active in ("creds", "hosts") else "matrix"
            ids = [item.id for item in items]
            self.push_screen(
                QuickInputScreen(f"Delete {len(ids)} {entity} ({', '.join(str(i) for i in ids)})? Type y", "y"),
                callback=lambda raw: self._confirm_delete_many(raw, entity, ids, items),
            )
            return
        if active == "creds":
            selected = self._selected_cred()
            if selected is None:
                return
            self.push_screen(
                QuickInputScreen(f"Delete credential id={selected.id}? Type y", "y"),
                callback=lambda raw: self._confirm_delete(raw, "creds", selected.id, selected),
            )
        elif active == "hosts":
            selected = self._selected_host()
            if selected is None:
                return
            self.push_screen(
                QuickInputScreen(f"Delete host id={selected.id}? Type y", "y"),
                callback=lambda raw: self._confirm_delete(raw, "hosts", selected.id, selected),
            )
        elif active == "matrix":
            selected = self._selected_link()
            if selected is None:
                self._set_status("No access row selected.")
                return
            self.push_screen(
                QuickInputScreen(f"Delete link id={selected.id}? Type y", "y"),
                callback=lambda raw: self._confirm_delete(raw, "matrix", selected.id),
            )
        elif active == "targets":
            selected = self._selected_target()
            if selected is None:
                return
            self.push_screen(
                QuickInputScreen(f"Delete target id={selected.id} '{selected.name}'? Type y", "y"),
                callback=lambda raw: self._confirm_delete(raw, "targets", selected.id),
            )

    def action_edit_item(self) -> None:
        active = self.query_one(TabbedContent).active
        if active == "creds":
            selected = self._selected_cred()
            if selected is None:
                return
            self.push_screen(
                MultiFieldScreen(
                    "Edit credential",
                    [
                        ("Username", "admin", selected.username or ""),
                        ("Password", "P@ssw0rd", selected.password or ""),
                        ("Hash", "aad3b435b51404ee:...", selected.hash or ""),
                        ("Secret", "token/key/...", selected.secret or ""),
                        ("Domain", "ACME.LOCAL", selected.domain or ""),
                    ],
                ),
                callback=lambda values: self._on_edit_cred(values, selected.id),
            )
        elif active == "hosts":
            selected = self._selected_host()
            if selected is None:
                return
            self.push_screen(
                MultiFieldScreen(
                    "Edit host",
                    [
                        ("IP", "10.10.10.10", selected.ip or ""),
                        ("Hostname", "DC01", selected.hostname or ""),
                        ("OS", "Windows Server 2022", selected.operating_system or ""),
                        ("Role  [DC, WS, SRV, WEB, ...]", "DC", selected.role or ""),
                    ],
                ),
                callback=lambda values: self._on_edit_host(values, selected.id),
            )
        elif active == "matrix":
            selected = self._selected_link()
            if selected is None:
                return
            proto_hint = ", ".join(sorted(ALLOWED_PROTOCOLS))
            status_hint = ", ".join(sorted(ALLOWED_STATUS))
            self.push_screen(
                MultiFieldScreen(
                    "Edit link",
                    [
                        ("Cred ID *", "1", str(selected.cred_id)),
                        ("Host ID *", "2", str(selected.host_id)),
                        (f"Protocol  [{proto_hint}]", "smb", selected.protocol),
                        (f"Status  [{status_hint}]", "valid", selected.status),
                    ],
                ),
                callback=lambda values: self._on_edit_link(values, selected.id),
            )
        elif active == "targets":
            selected = self._selected_target()
            if selected is None:
                return
            self.push_screen(
                MultiFieldScreen(
                    "Edit target",
                    [
                        ("Name *", "admin-hunt", selected.name),
                        ("User  (TARGET_USER)", "jdoe", selected.user or ""),
                        ("Group  (TARGET_GROUP)", "Domain Admins", selected.group or ""),
                        ("Object  (TARGET_OBJECT)", "cn=...", selected.object or ""),
                        ("Computer  (TARGET_COMPUTER)", "DC01", selected.computer or ""),
                        ("Domain  (TARGET_DOMAIN)", "serval.int", selected.domain or ""),
                        ("Principal  (TARGET_PRINCIPAL)", "S-1-5-21-...", selected.principal or ""),
                    ],
                ),
                callback=lambda values: self._on_edit_target(values, selected.id),
            )

    def action_set_item(self) -> None:
        active = self.query_one(TabbedContent).active
        if active == "creds":
            selected = self._selected_cred()
            if selected is None:
                return
            creds_set(selected.id)
            self.notify(f"Credential set: {selected.username or '-'} (id={selected.id})", title="Set", severity="information")
        elif active == "hosts":
            selected = self._selected_host()
            if selected is None:
                return
            hosts_set(selected.id)
            self.notify(f"Host set: {selected.ip or selected.hostname or '-'} (id={selected.id})", title="Set", severity="information")
        elif active == "targets":
            selected = self._selected_target()
            if selected is None:
                return
            targets_set(selected.id)
            self.notify(f"Target set: {selected.name} (id={selected.id})", title="Set", severity="information")
        else:
            self._set_status("Set is available on credentials, hosts, and targets tabs.")
            return
        self._refresh_all()

    def action_link_item(self) -> None:
        proto_hint = ", ".join(sorted(ALLOWED_PROTOCOLS))
        status_hint = ", ".join(sorted(ALLOWED_STATUS))
        self.push_screen(
            MultiFieldScreen(
                "Create access link",
                [
                    ("Cred ID *", "1", ""),
                    ("Host ID *", "2", ""),
                    (f"Protocol  [{proto_hint}]", "smb", "smb"),
                    (f"Status  [{status_hint}]", "valid", "valid"),
                ],
            ),
            callback=self._on_add_link,
        )

    def action_toggle_dc(self) -> None:
        if self.query_one(TabbedContent).active != "hosts":
            return
        selected = self._selected_host()
        if selected is None:
            return
        new_role = None if selected.role == "DC" else "DC"
        try:
            hosts_update(
                host_id=selected.id,
                ip=selected.ip,
                hostname=selected.hostname,
                domain=selected.domain,
                operating_system=selected.operating_system,
                role=new_role,
            )
            label = selected.ip or selected.hostname or f"id={selected.id}"
            if new_role:
                self.notify(f"{label}  →  DC", title="Role set", severity="information")
            else:
                self.notify(f"{label}  →  role cleared", title="Role cleared", severity="information")
            self._refresh_all()
        except Exception as exc:
            self.notify(str(exc), title="Toggle DC failed", severity="error", markup=False)

    def action_yank(self) -> None:
        """Copy the selected row into the yank buffer (vim-style y, paste with p)."""
        active = self.query_one(TabbedContent).active
        getter = {
            "creds": self._selected_cred,
            "hosts": self._selected_host,
            "targets": self._selected_target,
            "matrix": self._selected_link,
        }.get(active)
        if getter is None:
            return
        selected = getter()
        if selected is None:
            return
        self._yank = (active, selected)
        self._set_status(f"Yanked {active} id={selected.id} - press p to paste a copy")

    def action_paste(self) -> None:
        """Paste the yank buffer as a new entry of the same kind."""
        yanked = getattr(self, "_yank", None)
        if not yanked:
            self._set_status("Nothing to paste - press y on a row first")
            return
        kind, obj = yanked
        try:
            if kind == "creds":
                creds_add(username=obj.username, password=obj.password, hash=obj.hash,
                          secret=obj.secret, domain=obj.domain, source="yank")
            elif kind == "hosts":
                hosts_add(ip=obj.ip, hostname=obj.hostname, domain=obj.domain,
                          operating_system=obj.operating_system, role=obj.role, source="yank")
            elif kind == "targets":
                targets_add(name=obj.name, user=obj.user, group=obj.group,
                            object_=obj.object, computer=obj.computer, domain=obj.domain,
                            principal=obj.principal)
            elif kind == "matrix":
                access_link(cred_id=obj.cred_id, host_id=obj.host_id,
                            protocol=obj.protocol, status=obj.status, source="yank")
            else:
                return
        except Exception as exc:
            self.notify(str(exc), title="Paste failed", severity="error", markup=False)
            return
        self._refresh_all(f"Pasted a copy of {kind} id={obj.id}")

    def action_visual_toggle(self) -> None:
        active = self.query_one(TabbedContent).active
        if active not in ("creds", "hosts"):
            return
        if self._visual_mode:
            self._exit_visual_mode()
            return
        t = self._active_table()
        if t is None or t.row_count == 0:
            return
        self._visual_mode = True
        self._visual_anchor = t.cursor_row
        self._visual_prev_sel = None
        self._update_visual_status(t)

    def _exit_visual_mode(self) -> None:
        self._visual_mode = False
        self._visual_prev_sel = None
        active = self.query_one(TabbedContent).active
        if active == "creds":
            self._render_creds(self._vis_creds)
        elif active == "hosts":
            self._render_hosts(self._vis_hosts)
        self._set_status("-- NORMAL --")

    def _visual_selection(self, t) -> range:
        a = self._visual_anchor
        b = t.cursor_row
        return range(min(a, b), max(a, b) + 1)

    def _paint_visual_markers(self, table: DataTable, count: int, sel: range) -> None:
        """Update only the marker cells that changed since the last selection.

        Avoids a full clear()+rebuild on every up/down keystroke, which used
        to reset and re-scroll the cursor each time and caused a visible
        jump/flicker while moving through the selection in visual mode.
        """
        prev = getattr(self, "_visual_prev_sel", None)
        lo = min(sel.start, prev.start) if prev is not None else sel.start
        hi = max(sel.stop, prev.stop) if prev is not None else sel.stop
        for i in range(max(0, lo), min(hi, count)):
            marker = "▶" if i in sel else " "
            table.update_cell_at(Coordinate(i, 0), marker)
        self._visual_prev_sel = sel

    def _update_visual_status(self, t) -> None:
        sel = self._visual_selection(t)
        n = len(sel)
        self._set_status(f"-- VISUAL -- {n} row{'s' if n > 1 else ''} (#{sel.start + 1}-#{sel.stop})  |  d delete  |  Esc cancel")
        active = self.query_one(TabbedContent).active
        if active == "creds":
            self._paint_visual_markers(t, len(self._vis_creds), sel)
        elif active == "hosts":
            self._paint_visual_markers(t, len(self._vis_hosts), sel)

    def action_show_allowed_values(self) -> None:
        protocols = ", ".join(sorted(ALLOWED_PROTOCOLS))
        status = ", ".join(sorted(ALLOWED_STATUS))
        self._set_status(f"protocol: {protocols} | status: {status}")

    def _active_table(self) -> DataTable | None:
        active = self.query_one(TabbedContent).active
        table_id = {"creds": "creds_table", "hosts": "hosts_table", "matrix": "matrix_table", "targets": "targets_table"}.get(active)
        return self.query_one(f"#{table_id}", DataTable) if table_id else None

    def action_vi_down(self) -> None:
        if t := self._active_table():
            t.focus()
            t.move_cursor(row=min(t.cursor_row + 1, t.row_count - 1))
            if self._visual_mode:
                self._update_visual_status(t)

    def action_vi_up(self) -> None:
        if t := self._active_table():
            t.focus()
            t.move_cursor(row=max(t.cursor_row - 1, 0))
            if self._visual_mode:
                self._update_visual_status(t)

    def action_vi_top(self) -> None:
        if t := self._active_table():
            t.focus()
            t.move_cursor(row=0)
            if self._visual_mode:
                self._update_visual_status(t)

    def action_vi_bottom(self) -> None:
        if t := self._active_table():
            t.focus()
            t.move_cursor(row=max(t.row_count - 1, 0))
            if self._visual_mode:
                self._update_visual_status(t)

    def action_search_open(self) -> None:
        bar = self.query_one("#search_bar", Input)
        bar.display = True
        bar.focus()

    def _close_search(self, clear: bool = True) -> None:
        """Hide the search bar.

        `clear=True` (Escape) cancels the search and restores the full list.
        `clear=False` (Enter/Tab) keeps the filter active and just hides the
        input, so confirming a search actually lands you on the filtered
        results instead of immediately showing everything again.
        """
        bar = self.query_one("#search_bar", Input)
        bar.display = False
        if clear:
            bar.value = ""
            self._search_query = ""
            self._apply_search()
        if t := self._active_table():
            t.focus()

    def _apply_search(self) -> None:
        q = self._search_query
        if q:
            creds = [c for c in self.state.creds if
                     q in (c.username or "").lower() or
                     q in (c.password or "").lower() or
                     q in (c.hash or "").lower() or
                     q in (c.secret or "").lower() or
                     q in (c.domain or "").lower() or
                     q in (c.source or "").lower()]
            hosts = [h for h in self.state.hosts if
                     q in (h.ip or "").lower() or
                     q in (h.hostname or "").lower() or
                     q in (h.operating_system or "").lower() or
                     q in (h.role or "").lower()]
            links = [lnk for lnk in self.state.links if
                     q in lnk.protocol.lower() or
                     q in lnk.status.lower()]
            tgts = [t for t in (self.state.targets or []) if
                    q in t.name.lower() or
                    q in (t.user or "").lower() or
                    q in (t.group or "").lower() or
                    q in (t.object or "").lower() or
                    q in (t.computer or "").lower() or
                    q in (t.domain or "").lower() or
                    q in (t.principal or "").lower()]
        else:
            creds = self.state.creds
            hosts = self.state.hosts
            links = self.state.links
            tgts = self.state.targets or []
        self._render_creds(creds)
        self._render_hosts(hosts)
        self._render_matrix(links)
        self._render_targets(tgts)

    @on(Input.Changed, "#search_bar")
    def _on_search_changed(self, event: Input.Changed) -> None:
        self._search_query = event.value.lower()
        self._apply_search()

    @on(Input.Submitted, "#search_bar")
    def _on_search_submitted(self, event: Input.Submitted) -> None:
        self._search_query = event.value.lower()
        self._apply_search()
        self._close_search(clear=False)

    def on_key(self, event) -> None:
        bar = self.query_one("#search_bar", Input)
        if event.key == "escape" and bar.display and bar.has_focus:
            self._close_search()
            event.stop()
            return
        if event.key == "escape" and self._visual_mode:
            self._exit_visual_mode()
            event.stop()

    @on(DataTable.RowSelected)
    def _on_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_show_details()

    def action_show_details(self) -> None:
        active = self.query_one(TabbedContent).active
        if active == "creds":
            selected = self._selected_cred()
            if selected is None:
                return
            creds_set(selected.id)
            self.exit()
        elif active == "hosts":
            selected = self._selected_host()
            if selected is None:
                return
            hosts_set(selected.id)
            self.exit()
        elif active == "targets":
            selected = self._selected_target()
            if selected is None:
                return
            targets_set(selected.id)
            self.exit()
        else:
            selected = self._selected_link()
            if selected is None:
                return
            self._set_status(
                f"link id={selected.id} cred={selected.cred_id} host={selected.host_id} {selected.protocol}/{selected.status}"
            )

    def _set_status(self, value: str) -> None:
        self.query_one("#status", Static).update(value)

    def _on_add_cred(self, values: list[str] | None) -> None:
        if values is None:
            return
        try:
            username, password, hash_, secret, domain = values
            cred = creds_add(
                username=username or None,
                password=password or None,
                hash=hash_ or None,
                secret=secret or None,
                domain=domain or None,
            )
            self.notify(f"{cred.username or '-'}  added (id={cred.id})", title="Credential added", severity="information")
            self._refresh_all()
        except MissingEngagementError:
            self.notify("No active engagement.", title="Error", severity="error")
        except Exception as exc:
            self.notify(str(exc), title="Add credential failed", severity="error", markup=False)

    def _on_add_host(self, values: list[str] | None) -> None:
        if values is None:
            return
        try:
            ip, hostname, os_name, role = values
            host = hosts_add(ip=ip or None, hostname=hostname or None, domain=None, operating_system=os_name or None, role=role or None)
            self.notify(f"{host.ip or host.hostname or '-'}  added (id={host.id})", title="Host added", severity="information")
            self._refresh_all()
        except MissingEngagementError:
            self.notify("No active engagement.", title="Error", severity="error")
        except Exception as exc:
            self.notify(str(exc), title="Add host failed", severity="error", markup=False)

    def _on_add_link(self, values: list[str] | None) -> None:
        if values is None:
            return
        try:
            cred_id, host_id, protocol, status = values
            link = access_link(cred_id=int(cred_id), host_id=int(host_id), protocol=protocol, status=status or "unknown")
            self._refresh_all(status_message=f"Access link added: id={link.id}")
        except MissingEngagementError:
            self._set_status("No active engagement. Use `nhi engagement init <name>` first.")
        except Exception as exc:
            self._set_status(f"Create link failed: {exc}")

    def _on_edit_cred(self, values: list[str] | None, cred_id: int) -> None:
        if values is None:
            return
        try:
            username, password, hash_, secret, domain = values
            creds_update(
                cred_id=cred_id,
                username=username or None,
                password=password or None,
                hash=hash_ or None,
                secret=secret or None,
                domain=domain or None,
            )
            self.notify(f"Credential id={cred_id} updated", title="Edited", severity="information")
            self._refresh_all()
        except Exception as exc:
            self.notify(str(exc), title="Edit credential failed", severity="error", markup=False)

    def _on_edit_host(self, values: list[str] | None, host_id: int) -> None:
        if values is None:
            return
        try:
            ip, hostname, os_name, role = values
            hosts_update(
                host_id=host_id,
                ip=ip,
                hostname=hostname or None,
                domain=None,
                operating_system=os_name or None,
                role=role or None,
            )
            self.notify(f"Host id={host_id} updated", title="Edited", severity="information")
            self._refresh_all()
        except Exception as exc:
            self.notify(str(exc), title="Edit host failed", severity="error", markup=False)

    def _on_edit_link(self, values: list[str] | None, link_id: int) -> None:
        if values is None:
            return
        try:
            cred_id, host_id, protocol, status = values
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

    def _on_add_target(self, values: list[str] | None) -> None:
        if values is None:
            return
        try:
            name, user, group, object_, computer, domain, principal = values
            if not name:
                self._set_status("Target name is required.")
                return
            target = targets_add(name=name, user=user or None, group=group or None, object_=object_ or None, computer=computer or None, domain=domain or None, principal=principal or None)
            self.notify(f"'{target.name}' added (id={target.id})", title="Target added", severity="information")
            self._refresh_all()
        except MissingEngagementError:
            self.notify("No active engagement.", title="Error", severity="error")
        except Exception as exc:
            self.notify(str(exc), title="Add target failed", severity="error", markup=False)

    def _on_edit_target(self, values: list[str] | None, target_id: int) -> None:
        if values is None:
            return
        try:
            name, user, group, object_, computer, domain, principal = values
            if not name:
                self._set_status("Target name is required.")
                return
            targets_update(
                target_id=target_id,
                name=name,
                user=user or None,
                group=group or None,
                object_=object_ or None,
                computer=computer or None,
                domain=domain or None,
                principal=principal or None,
            )
            self.notify(f"Target id={target_id} updated", title="Edited", severity="information")
            self._refresh_all()
        except Exception as exc:
            self.notify(str(exc), title="Edit target failed", severity="error", markup=False)

    def _nxc_workspace_name(self) -> str | None:
        try:
            entry = require_engagement()
            return entry.nxc_workspace or entry.name
        except Exception:
            return None

    def _purge_from_nxc(self, entity: str, obj) -> int:
        """Best-effort: also drop the matching row from NXC's own workspace db, if present."""
        workspace = self._nxc_workspace_name()
        if workspace is None:
            return 0
        try:
            if entity == "creds":
                return nxc_delete_credential(workspace, obj.username, obj.domain, obj.password, obj.hash)
            if entity == "hosts":
                return nxc_delete_host(workspace, obj.ip, obj.hostname)
        except Exception:
            return 0
        return 0

    def _confirm_delete_many(self, raw: str | None, entity: str, ids: list[int], objs: list | None = None) -> None:
        self._exit_visual_mode()
        if (raw or "").upper() not in ("Y", "YES"):
            self._set_status("Delete cancelled.")
            return
        errors = []
        nxc_purged = 0
        for i, eid in enumerate(ids):
            try:
                if entity == "creds":
                    creds_remove(eid)
                elif entity == "hosts":
                    hosts_remove(eid)
                else:
                    hosts_remove(eid)
                if objs is not None and entity in ("creds", "hosts"):
                    nxc_purged += self._purge_from_nxc(entity, objs[i])
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            self.notify("; ".join(errors), title="Delete errors", severity="error", markup=False)
        else:
            suffix = f" ({nxc_purged} also removed from NXC db)" if nxc_purged else ""
            self.notify(f"{len(ids)} {entity} deleted{suffix}", title="Deleted", severity="warning")
        self._refresh_all()

    def _confirm_delete(self, raw: str | None, entity: str, entity_id: int, obj=None) -> None:
        if (raw or "").upper() not in ("Y", "YES"):
            return
        try:
            if entity == "creds":
                creds_remove(entity_id)
            elif entity == "hosts":
                hosts_remove(entity_id)
            elif entity == "targets":
                targets_remove(entity_id)
            else:
                access_remove(entity_id)
            nxc_purged = self._purge_from_nxc(entity, obj) if obj is not None and entity in ("creds", "hosts") else 0
            suffix = " (also removed from NXC db)" if nxc_purged else ""
            self.notify(f"{entity.rstrip('s')} id={entity_id} deleted{suffix}", title="Deleted", severity="warning")
            self._refresh_all()
        except Exception as exc:
            self.notify(str(exc), title="Delete failed", severity="error", markup=False)

    def _refresh_all(self, status_message: str | None = None) -> None:
        try:
            creds = creds_list()
            hosts = hosts_list()
            links = access_list()
            tgts = targets_list()
        except MissingEngagementError as exc:
            self._set_status(str(exc))
            self._render_empty()
            return

        prev_creds = self.query_one("#creds_table", DataTable).cursor_row
        prev_hosts = self.query_one("#hosts_table", DataTable).cursor_row
        prev_matrix = self.query_one("#matrix_table", DataTable).cursor_row
        prev_targets = self.query_one("#targets_table", DataTable).cursor_row

        self.state.creds = creds
        self.state.hosts = hosts
        self.state.links = links
        self.state.targets = tgts
        self._render_creds(creds)
        self._render_hosts(hosts)
        self._render_matrix(links)
        self._render_targets(tgts)

        if creds:
            self.query_one("#creds_table", DataTable).move_cursor(row=max(0, min(prev_creds, len(creds) - 1)))
        if hosts:
            self.query_one("#hosts_table", DataTable).move_cursor(row=max(0, min(prev_hosts, len(hosts) - 1)))
        if links:
            self.query_one("#matrix_table", DataTable).move_cursor(row=max(0, min(prev_matrix, len(links) - 1)))
        if tgts:
            self.query_one("#targets_table", DataTable).move_cursor(row=max(0, min(prev_targets, len(tgts) - 1)))
        if status_message:
            self._set_status(status_message)
        else:
            self._set_status(
                "Loaded: "
                f"creds={len(creds)} hosts={len(hosts)} links={len(links)} targets={len(tgts)} | "
                "Keys: h/l tabs, 1/2/3/4 switch, a add, e edit, d delete, s set, L link, / search, ? allowed values, Enter details, r refresh, q quit"
            )

    def _render_empty(self) -> None:
        for table_id in ("creds_table", "hosts_table", "matrix_table", "targets_table"):
            table = self.query_one(f"#{table_id}", DataTable)
            table.clear(columns=True)
            table.add_column("Info")
            table.add_row("No active engagement.")

    def _render_creds(self, creds: list, selection: range | None = None) -> None:
        self._vis_creds = creds
        table = self.query_one("#creds_table", DataTable)
        prev = table.cursor_row
        table.clear(columns=True)
        table.add_column(" ", width=1)
        table.add_column("ID")
        table.add_column("Username")
        table.add_column("Domain")
        table.add_column("Password")
        table.add_column("Hash")
        table.add_column("Secret")
        table.add_column("Source")
        for i, cred in enumerate(creds):
            marker = "▶" if selection is not None and i in selection else " "
            table.add_row(
                marker,
                str(cred.id),
                cred.username or "-",
                cred.domain or "-",
                cred.password or "-",
                cred.hash or "-",
                cred.secret or "-",
                cred.source,
            )
        if selection is not None and creds:
            table.move_cursor(row=max(0, min(prev, len(creds) - 1)))

    def _render_hosts(self, hosts: list, selection: range | None = None) -> None:
        self._vis_hosts = hosts
        table = self.query_one("#hosts_table", DataTable)
        prev = table.cursor_row
        table.clear(columns=True)
        table.add_column(" ", width=1)
        table.add_column("ID")
        table.add_column("IP")
        table.add_column("Hostname")
        table.add_column("OS")
        table.add_column("Role")
        for i, host in enumerate(hosts):
            marker = "▶" if selection is not None and i in selection else " "
            table.add_row(marker, str(host.id), host.ip or "-", host.hostname or "-", host.operating_system or "-", host.role or "-")
        if selection is not None and hosts:
            table.move_cursor(row=max(0, min(prev, len(hosts) - 1)))

    def _render_matrix(self, links: list) -> None:
        self._vis_links = links
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
        if idx is None or idx < 0 or idx >= len(self._vis_creds):
            self._set_status("No credential row selected.")
            return None
        return self._vis_creds[idx]

    def _selected_host(self):
        table = self.query_one("#hosts_table", DataTable)
        idx = table.cursor_row
        if idx is None or idx < 0 or idx >= len(self._vis_hosts):
            self._set_status("No host row selected.")
            return None
        return self._vis_hosts[idx]

    def _selected_link(self):
        table = self.query_one("#matrix_table", DataTable)
        idx = table.cursor_row
        if idx is None or idx < 0 or idx >= len(self._vis_links):
            self._set_status("No access row selected.")
            return None
        return self._vis_links[idx]

    def _render_targets(self, targets: list) -> None:
        self._vis_targets = targets
        table = self.query_one("#targets_table", DataTable)
        table.clear(columns=True)
        table.add_column("ID")
        table.add_column("Name")
        table.add_column("TARGET_USER")
        table.add_column("TARGET_GROUP")
        table.add_column("TARGET_OBJECT")
        table.add_column("TARGET_COMPUTER")
        table.add_column("TARGET_DOMAIN")
        table.add_column("TARGET_PRINCIPAL")
        for target in targets:
            table.add_row(
                str(target.id),
                target.name,
                target.user or "-",
                target.group or "-",
                target.object or "-",
                target.computer or "-",
                target.domain or "-",
                target.principal or "-",
            )

    def _selected_target(self):
        table = self.query_one("#targets_table", DataTable)
        idx = table.cursor_row
        if idx is None or idx < 0 or idx >= len(self._vis_targets):
            self._set_status("No target row selected.")
            return None
        return self._vis_targets[idx]

