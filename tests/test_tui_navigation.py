from types import SimpleNamespace
import unittest
from unittest.mock import patch

from textual.containers import VerticalScroll
from textual.widgets import DataTable, Input, Markdown, TabbedContent

from nihil_history.tui import HelpScreen, NihilHistoryTUI, QuickInputScreen


class TuiNavigationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.enterContext(patch("nihil_history.tui.ensure_default_engagement"))
        self.enterContext(patch("nihil_history.tui.load_config", return_value=SimpleNamespace(current_engagement="test")))
        self.enterContext(patch.object(NihilHistoryTUI, "_refresh_all"))

    async def test_arrows_switch_tabs_from_initial_table_without_tab_key(self):
        app = NihilHistoryTUI()
        async with app.run_test() as pilot:
            self.assertEqual(app.focused.id, "creds_table")
            tabs = app.query_one(TabbedContent)
            for tab in ("hosts", "targets", "matrix", "creds"):
                await pilot.press("right")
                self.assertEqual(tabs.active, tab)
                self.assertEqual(app.focused.id, f"{tab}_table")
            await pilot.press("left")
            self.assertEqual(tabs.active, "matrix")
            await pilot.press("right")
            table = app.query_one("#creds_table", DataTable)
            table.add_column("User")
            table.add_rows([("first",), ("second",)])
            table.focus()
            await pilot.press("down")
            self.assertEqual(table.cursor_row, 1)
            await pilot.press("right", "left")
            self.assertIs(app.focused, table)
            self.assertEqual(table.cursor_row, 1)
            await pilot.press("up")
            self.assertEqual(table.cursor_row, 0)

    async def test_switching_after_search_restores_each_table_once(self):
        app = NihilHistoryTUI()
        async with app.run_test() as pilot:
            app.state.creds = [
                SimpleNamespace(id=i, username=name, domain=None, password=None,
                                hash=None, secret=None, source="test")
                for i, name in enumerate(("user", "other"))
            ]
            app._apply_search()
            app.action_search_open()
            bar = app.query_one("#search_bar", Input)
            bar.value = "user"
            await pilot.pause()
            self.assertEqual(app.query_one("#creds_table", DataTable).row_count, 1)
            with patch.object(app, "_render_creds", wraps=app._render_creds) as creds, \
                 patch.object(app, "_render_hosts", wraps=app._render_hosts) as hosts, \
                 patch.object(app, "_render_matrix", wraps=app._render_matrix) as matrix, \
                 patch.object(app, "_render_targets", wraps=app._render_targets) as targets:
                app.action_tab_next()
                await pilot.pause()
                self.assertEqual(app._search_query, "")
                self.assertEqual(bar.value, "")
                self.assertFalse(bar.display)
                self.assertEqual(app.query_one(TabbedContent).active, "hosts")
                self.assertEqual(app.query_one("#creds_table", DataTable).row_count, 2)
                for render in (creds, hosts, matrix, targets):
                    render.assert_called_once()

    async def test_tab_animation_uses_200_ms(self):
        app = NihilHistoryTUI()
        async with app.run_test() as pilot:
            await pilot.wait_for_scheduled_animations()
            underline = app.query_one("TabbedContent Underline")
            with patch.object(app.animator, "animate", wraps=app.animator.animate) as animate:
                await pilot.press("right")
                await pilot.wait_for_scheduled_animations()
                calls = [call for call in animate.call_args_list if call.args[0] is underline]
                self.assertEqual({call.kwargs["attribute"] for call in calls}, {"highlight_start", "highlight_end"})
                for call in calls:
                    self.assertEqual(call.kwargs["duration"], 0.2)

    async def test_help_is_scrollable_and_escape_restores_table_focus(self):
        for size in ((80, 24), (60, 16), (80, 10), (40, 8)):
            with self.subTest(size=size):
                app = NihilHistoryTUI()
                async with app.run_test(size=size) as pilot:
                    table = app.focused
                    await pilot.press("?")
                    self.assertIsInstance(app.screen, HelpScreen)
                    app.screen.query_one(Markdown)
                    scroll = app.screen.query_one("#help-scroll", VerticalScroll)
                    self.assertGreaterEqual(scroll.content_size.height, 3)
                    self.assertGreater(scroll.max_scroll_y, 0)
                    await pilot.press("j")
                    await pilot.wait_for_scheduled_animations()
                    self.assertGreater(scroll.scroll_y, 0)
                    await pilot.press("k")
                    await pilot.wait_for_scheduled_animations()
                    self.assertEqual(scroll.scroll_y, 0)
                    await pilot.press("pagedown")
                    await pilot.wait_for_scheduled_animations()
                    self.assertGreater(scroll.scroll_y, 0)
                    await pilot.press("G")
                    await pilot.wait_for_scheduled_animations()
                    self.assertEqual(scroll.scroll_y, scroll.max_scroll_y)
                    await pilot.press("g")
                    await pilot.wait_for_scheduled_animations()
                    self.assertEqual(scroll.scroll_y, 0)
                    await pilot.press("escape")
                    self.assertNotIsInstance(app.screen, HelpScreen)
                    self.assertIs(app.focused, table)
                    self.assertEqual(app.query_one(TabbedContent).active, "creds")

    async def test_help_can_close_with_question_mark_or_button(self):
        app = NihilHistoryTUI()
        async with app.run_test() as pilot:
            await pilot.press("?", "?")
            self.assertNotIsInstance(app.screen, HelpScreen)
            await pilot.press("?")
            await pilot.click("#help-close")
            self.assertNotIsInstance(app.screen, HelpScreen)

    async def test_arrows_still_move_cursor_in_search_and_forms(self):
        app = NihilHistoryTUI()
        async with app.run_test() as pilot:
            app.action_search_open()
            await pilot.pause()
            bar = app.query_one("#search_bar", Input)
            bar.value = "abc"
            bar.cursor_position = 2
            await pilot.press("left")
            self.assertEqual(bar.cursor_position, 1)
            await pilot.press("right")
            self.assertEqual(bar.cursor_position, 2)
            self.assertEqual(app.query_one(TabbedContent).active, "creds")
            app._close_search()
            app.push_screen(QuickInputScreen("Test", ""))
            await pilot.pause()
            field = app.screen.query_one(Input)
            field.focus()
            field.value = "abc"
            field.cursor_position = 2
            await pilot.press("left")
            self.assertEqual(field.cursor_position, 1)
            await pilot.press("right")
            self.assertEqual(field.cursor_position, 2)


if __name__ == "__main__":
    unittest.main()
