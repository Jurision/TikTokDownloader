import builtins
import sys
import unittest
from unittest.mock import Mock, patch

import main


class MainPanelModeTests(unittest.TestCase):
    def test_should_run_panel_mode_reads_environment(self):
        with patch.dict("os.environ", {"DOUK_PANEL_MODE": "1"}, clear=False):
            self.assertTrue(main.should_run_panel_mode())

        with patch.dict("os.environ", {"DOUK_PANEL_MODE": "true"}, clear=False):
            self.assertTrue(main.should_run_panel_mode())

        with patch.dict("os.environ", {"DOUK_PANEL_MODE": "0"}, clear=False):
            self.assertFalse(main.should_run_panel_mode())

    def test_should_run_panel_mode_accepts_yes_and_mixed_case_values(self):
        for value in ["yes", "YeS", "TRUE"]:
            with self.subTest(value=value):
                with patch.dict("os.environ", {"DOUK_PANEL_MODE": value}, clear=False):
                    self.assertTrue(main.should_run_panel_mode())

    def test_should_run_panel_mode_rejects_empty_and_unset_values(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(main.should_run_panel_mode())

        with patch.dict("os.environ", {"DOUK_PANEL_MODE": ""}, clear=False):
            self.assertFalse(main.should_run_panel_mode())

    def test_panel_host_and_port_defaults(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(main.panel_host(), "127.0.0.1")
            self.assertEqual(main.panel_port(), 5555)

    def test_panel_host_reads_environment(self):
        with patch.dict("os.environ", {"DOUK_PANEL_HOST": "0.0.0.0"}, clear=False):
            self.assertEqual(main.panel_host(), "0.0.0.0")

    def test_panel_port_reads_environment(self):
        with patch.dict("os.environ", {"DOUK_PANEL_PORT": "7777"}, clear=False):
            self.assertEqual(main.panel_port(), 7777)

    def test_panel_port_raises_value_error_for_invalid_environment(self):
        with patch.dict("os.environ", {"DOUK_PANEL_PORT": "not-a-port"}, clear=False):
            with self.assertRaises(ValueError):
                main.panel_port()

    def test_run_panel_uses_environment_configuration(self):
        with patch.dict(
            "os.environ",
            {
                "DOUK_PANEL_VOLUME": "CustomVolume",
                "DOUK_PANEL_HOST": "0.0.0.0",
                "DOUK_PANEL_PORT": "7777",
            },
            clear=False,
        ):
            with patch("main.create_panel_app") as create_panel_app:
                with patch("main.Config") as config:
                    with patch("main.Server") as server:
                        app = object()
                        config_instance = object()
                        server_instance = Mock()
                        create_panel_app.return_value = app
                        config.return_value = config_instance
                        server.return_value = server_instance

                        main.run_panel()

        create_panel_app.assert_called_once_with("CustomVolume")
        config.assert_called_once_with(app=app, host="0.0.0.0", port=7777, log_level="info")
        server.assert_called_once_with(config_instance)
        server_instance.run.assert_called_once_with()

    def test_importing_main_does_not_import_cli_application(self):
        original_import = builtins.__import__
        original_main = sys.modules.get("main")
        original_application = sys.modules.get("src.application")

        def fail_cli_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "src.application":
                raise AssertionError("CLI import should not run while importing main")
            return original_import(name, globals, locals, fromlist, level)

        try:
            sys.modules.pop("main", None)
            sys.modules.pop("src.application", None)

            with patch("builtins.__import__", side_effect=fail_cli_import):
                imported_main = __import__("main")

            self.assertTrue(hasattr(imported_main, "should_run_panel_mode"))
            self.assertNotIn("src.application", sys.modules)
        finally:
            if original_main is None:
                sys.modules.pop("main", None)
            else:
                sys.modules["main"] = original_main

            if original_application is None:
                sys.modules.pop("src.application", None)
            else:
                sys.modules["src.application"] = original_application

    def test_main_runs_panel_without_importing_cli_when_panel_mode_enabled(self):
        original_import = builtins.__import__

        def fail_cli_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "src.application":
                raise AssertionError("CLI import should not run in panel mode")
            return original_import(name, globals, locals, fromlist, level)

        with patch.dict("os.environ", {"DOUK_PANEL_MODE": "1"}, clear=False):
            with patch("main.run_panel") as run_panel:
                with patch("builtins.__import__", side_effect=fail_cli_import):
                    self.assertIsNone(main.main())

        run_panel.assert_called_once_with()

    def test_main_runs_cli_when_panel_mode_is_disabled(self):
        cases = [
            ({}, "unset"),
            ({"DOUK_PANEL_MODE": "0"}, "zero"),
            ({"DOUK_PANEL_MODE": "false"}, "false"),
        ]

        for env, label in cases:
            with self.subTest(label=label):
                cli_runner = object()

                with patch.dict("os.environ", env, clear=True):
                    with patch("main.run_panel") as run_panel:
                        run_cli = Mock(return_value=cli_runner)
                        with patch("main.run_cli", run_cli):
                            with patch("main.run_async") as run_async:
                                self.assertIsNone(main.main())

                run_panel.assert_not_called()
                run_cli.assert_called_once_with()
                run_async.assert_called_once_with(cli_runner)


if __name__ == "__main__":
    unittest.main()
