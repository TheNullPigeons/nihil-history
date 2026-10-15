import unittest
from unittest.mock import patch

from typer.testing import CliRunner

from nihil_history import cli


class TuiCliTests(unittest.TestCase):
    def test_tui_mode_flag(self):
        for flags, inline in (([], True), (["--full"], False)):
            with self.subTest(flags=flags), \
                 patch.object(cli, "ensure_default_engagement"), \
                 patch.object(cli, "require_engagement"), \
                 patch.object(cli, "import_nxc_db"), \
                 patch.object(cli, "NihilHistoryTUI") as app:
                result = CliRunner().invoke(cli.app, ["tui", *flags])
                self.assertEqual(result.exit_code, 0, result.output)
                app.return_value.run.assert_called_once_with(inline=inline)

    def test_nhit_mode_flag(self):
        for command, flags, inline in (("nhit", [], True), ("nhit", ["--full"], False),
                                       ("nhitf", [], False), ("nhitf", ["--full"], False)):
            with self.subTest(command=command, flags=flags), \
                 patch("sys.argv", [command, *flags]), \
                 patch.object(cli, "init_db"), \
                 patch.object(cli, "ensure_default_engagement"), \
                 patch.object(cli, "require_engagement"), \
                 patch.object(cli, "import_nxc_db"), \
                 patch.object(cli, "NihilHistoryTUI") as app:
                cli.tui_main()
                app.return_value.run.assert_called_once_with(inline=inline)

    def test_nhit_help_and_invalid_options_do_not_start_ui_or_touch_db(self):
        for flags, exit_code in ((["--help"], 0), (["--invalid"], 2)):
            with self.subTest(flags=flags), \
                 patch("sys.argv", ["nhit", *flags]), \
                 patch.object(cli, "init_db") as init_db, \
                 patch.object(cli, "NihilHistoryTUI") as app, \
                 self.assertRaises(SystemExit) as result:
                cli.tui_main()
            self.assertEqual(result.exception.code, exit_code)
            init_db.assert_not_called()
            app.assert_not_called()


if __name__ == "__main__":
    unittest.main()
