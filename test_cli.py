"""
test_cli.py — CLI parsing and dispatch tests

Tests three things:
  1. Parser routes each command to the correct cmd_ function
  2. Subcommand args land on the namespace with correct types and defaults
  3. Missing required commands raise SystemExit (argparse error path)

These tests mock the cmd_ functions so no filesystem or network activity
occurs. They do NOT test business logic — that lives in the module tests.
"""

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Stub out imports that cli.py pulls in at module level.
# These do not exist in the test environment.
# ---------------------------------------------------------------------------

def _stub_module(name, **attrs):
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# Stubs must not leak into the rest of the test suite during collection.
_STUB_NAMES = ["config", "main", "network", "validator", "crawler", "indexer", "ingest"]
_ORIG_MODULES = {name: sys.modules.get(name) for name in _STUB_NAMES}

_stub_module("config",
    SNAPSHOTS_DIR="/tmp/yggcrawl/data",
    ARCHIVE_DIR="/tmp/yggcrawl/data/archive",
    SNAPSHOT_FILE="/tmp/yggcrawl/data/current.json",
    SNAPSHOT_HASH_FILE="/tmp/yggcrawl/data/current.json.sha256",
    NODE_ID="test-node",
    MAX_URLS_PER_RUN=10,
)
_stub_module("main",
    run_once=MagicMock(return_value={"processed": 0, "snapshot_hash": "abc", "diff_written": False}),
    run_loop=MagicMock(),
    get_node_state=MagicMock(return_value={"queue_size": 0, "seen_size": 0, "index_size": 0}),
    phase_save_and_archive=MagicMock(return_value="abc"),
    sync_peers=MagicMock(return_value={
        "attempted": 2, "accepted": 1, "rejected": 1,
        "snapshot_hash": None,
        "details": [],
    }),
)
_stub_module("network", run_server=MagicMock())
_stub_module("validator", validate_snapshot=MagicMock(return_value=True))
_stub_module("ingest", ingest_outbox=MagicMock(return_value={"accepted": 0, "rejected": 0, "skipped": 0}))

crawler_mod = _stub_module("crawler")
crawler_mod.Crawler = MagicMock

indexer_mod = _stub_module("indexer")
indexer_mod.Indexer = MagicMock


import cli  # noqa: E402  — must come after stubs

# Restore original modules so other test modules import the real code.
for _name, _orig in _ORIG_MODULES.items():
    if _orig is None:
        sys.modules.pop(_name, None)
    else:
        sys.modules[_name] = _orig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse(argv):
    """Parse argv using the real parser, return (args, func_name)."""
    parser = cli.build_parser()
    args = parser.parse_args(argv)
    return args


# ---------------------------------------------------------------------------
# Routing tests
# ---------------------------------------------------------------------------

class TestCommandRouting(unittest.TestCase):

    def test_run_routes_to_cmd_run(self):
        args = parse(["run"])
        self.assertIs(args.func, cli.cmd_run)

    def test_loop_routes_to_cmd_loop(self):
        args = parse(["loop"])
        self.assertIs(args.func, cli.cmd_loop)

    def test_serve_routes_to_cmd_serve(self):
        args = parse(["serve"])
        self.assertIs(args.func, cli.cmd_serve)

    def test_status_routes_to_cmd_status(self):
        args = parse(["status"])
        self.assertIs(args.func, cli.cmd_status)

    def test_diff_routes_to_cmd_diff(self):
        args = parse(["diff"])
        self.assertIs(args.func, cli.cmd_diff)

    def test_verify_routes_to_cmd_verify(self):
        args = parse(["verify"])
        self.assertIs(args.func, cli.cmd_verify)

    def test_seeds_list_routes_to_cmd_seeds(self):
        args = parse(["seeds", "list"])
        self.assertIs(args.func, cli.cmd_seeds)
        self.assertEqual(args.seeds_command, "list")

    def test_peers_list_routes_to_cmd_peers(self):
        args = parse(["peers", "list"])
        self.assertIs(args.func, cli.cmd_peers)
        self.assertEqual(args.peers_command, "list")


# ---------------------------------------------------------------------------
# Argument default tests
# ---------------------------------------------------------------------------

class TestArgumentDefaults(unittest.TestCase):

    def test_loop_defaults(self):
        args = parse(["loop"])
        self.assertIsNone(args.max_runs)
        self.assertEqual(args.sleep_seconds, 5)
        self.assertEqual(args.sync_every, 5)
        self.assertEqual(args.snapshot_every, 5)
        self.assertEqual(args.max_backoff_iterations, 32)

    def test_loop_explicit_values(self):
        args = parse([
            "loop",
            "--max-runs", "20",
            "--sleep-seconds", "10",
            "--sync-every", "3",
            "--snapshot-every", "7",
            "--max-backoff-iterations", "16",
        ])
        self.assertEqual(args.max_runs, 20)
        self.assertEqual(args.sleep_seconds, 10)
        self.assertEqual(args.sync_every, 3)
        self.assertEqual(args.snapshot_every, 7)
        self.assertEqual(args.max_backoff_iterations, 16)

    def test_serve_default_port(self):
        args = parse(["serve"])
        self.assertEqual(args.port, 8080)

    def test_serve_explicit_port(self):
        args = parse(["serve", "--port", "9090"])
        self.assertEqual(args.port, 9090)

    def test_diff_json_flag_default_false(self):
        args = parse(["diff"])
        self.assertFalse(args.json)

    def test_diff_json_flag_set(self):
        args = parse(["diff", "--json"])
        self.assertTrue(args.json)

    def test_verify_verbose_default_false(self):
        args = parse(["verify"])
        self.assertFalse(args.verbose)

    def test_verify_verbose_short_flag(self):
        args = parse(["verify", "-v"])
        self.assertTrue(args.verbose)

    def test_global_home_flag(self):
        args = parse(["--home", "/tmp/mynode", "status"])
        self.assertEqual(args.home, "/tmp/mynode")

    def test_home_defaults_to_none(self):
        args = parse(["run"])
        self.assertIsNone(args.home)


# ---------------------------------------------------------------------------
# Error path tests
# ---------------------------------------------------------------------------

class TestErrorPaths(unittest.TestCase):

    def test_no_command_exits(self):
        parser = cli.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args([])

    def test_unknown_command_exits(self):
        parser = cli.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["frobnicate"])

    def test_loop_bad_int_exits(self):
        parser = cli.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["loop", "--max-runs", "not-a-number"])


# ---------------------------------------------------------------------------
# resolve_node_home tests (pure logic, no filesystem)
# ---------------------------------------------------------------------------

class TestResolveNodeHome(unittest.TestCase):

    def test_explicit_arg_takes_precedence(self):
        result = cli.resolve_node_home("/explicit/path")
        self.assertEqual(result, Path("/explicit/path"))

    def test_env_var_used_when_no_explicit(self):
        with patch.dict("os.environ", {"YGGCRAWL_HOME": "/from/env"}):
            result = cli.resolve_node_home(None)
        self.assertEqual(result, Path("/from/env"))

    def test_default_used_when_nothing_set(self):
        with patch.dict("os.environ", {}, clear=True):
            # Ensure YGGCRAWL_HOME is absent
            import os
            os.environ.pop("YGGCRAWL_HOME", None)
            result = cli.resolve_node_home(None)
        self.assertEqual(result, Path.home() / ".yggcrawl")

    def test_explicit_beats_env(self):
        with patch.dict("os.environ", {"YGGCRAWL_HOME": "/from/env"}):
            result = cli.resolve_node_home("/explicit/path")
        self.assertEqual(result, Path("/explicit/path"))


# ---------------------------------------------------------------------------
# load_lines_file tests
# ---------------------------------------------------------------------------

class TestLoadLinesFile(unittest.TestCase):

    def test_missing_file_returns_empty(self):
        result = cli.load_lines_file(Path("/nonexistent/path/seeds.txt"))
        self.assertEqual(result, [])

    def test_comments_and_blanks_stripped(self, tmp_path=None):
        import tempfile
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("# comment\n")
            f.write("\n")
            f.write("https://example.org\n")
            f.write("  https://example.com  \n")
            fname = f.name

        result = cli.load_lines_file(Path(fname))
        self.assertEqual(result, ["https://example.org", "https://example.com"])

        Path(fname).unlink()


# ---------------------------------------------------------------------------
# sync routing and argument tests
# ---------------------------------------------------------------------------

class TestSyncCommand(unittest.TestCase):

    def test_sync_routes_to_cmd_sync(self):
        args = parse(["sync"])
        self.assertIs(args.func, cli.cmd_sync)

    def test_sync_verbose_default_false(self):
        args = parse(["sync"])
        self.assertFalse(args.verbose)

    def test_sync_verbose_flag(self):
        args = parse(["sync", "--verbose"])
        self.assertTrue(args.verbose)

    def test_sync_verbose_short_flag(self):
        args = parse(["sync", "-v"])
        self.assertTrue(args.verbose)

    def test_sync_no_peers_prints_message(self):
        """cmd_sync with empty peers list must not call main.sync_peers."""
        import sys
        from io import StringIO
        from unittest.mock import patch

        main_mod = cli.main
        main_mod.sync_peers.reset_mock()

        args = parse(["sync"])
        args.home = None

        empty_node_files = {"seeds": [], "peers": [], "config": {}}

        with patch.object(cli, "_init_node", return_value=(Path("/tmp"), empty_node_files)):
            buf = StringIO()
            with patch("sys.stdout", buf):
                cli.cmd_sync(args)

        output = buf.getvalue()
        self.assertIn("No peers configured", output)

        main_mod.sync_peers.assert_not_called()

    def test_sync_calls_main_sync_peers(self):
        """cmd_sync with peers must delegate to main.sync_peers."""
        main_mod = cli.main
        main_mod.sync_peers.reset_mock()

        args = parse(["sync"])
        args.home = None

        node_files = {
            "seeds": [],
            "peers": ["http://[300:a::1]/snapshot.json"],
            "config": {},
        }

        from unittest.mock import patch, MagicMock
        fake_indexer = MagicMock()

        with patch.object(cli, "_init_node", return_value=(Path("/tmp"), node_files)), \
             patch.object(cli, "Indexer", return_value=fake_indexer):
            from io import StringIO
            with patch("sys.stdout", StringIO()):
                cli.cmd_sync(args)

        main_mod.sync_peers.assert_called_once_with(
            fake_indexer,
            ["http://[300:a::1]/snapshot.json"],
        )

    def test_sync_output_contains_counts(self):
        """cmd_sync prints accepted/rejected counts from main.sync_peers result."""
        import sys
        from io import StringIO
        from unittest.mock import patch, MagicMock

        args = parse(["sync"])
        args.home = None
        args.verbose = False

        node_files = {
            "seeds": [],
            "peers": ["http://[300:a::1]/snapshot.json", "http://[300:b::1]/snapshot.json"],
            "config": {},
        }

        fake_indexer = MagicMock()

        with patch.object(cli, "_init_node", return_value=(Path("/tmp"), node_files)), \
             patch.object(cli, "Indexer", return_value=fake_indexer):
            buf = StringIO()
            with patch("sys.stdout", buf):
                cli.cmd_sync(args)

        output = buf.getvalue()
        self.assertIn("Accepted", output)
        self.assertIn("Rejected", output)
        # sync_peers does not save a snapshot, so no hash line expected

    def test_sync_verbose_shows_summary(self):
        """--verbose flag is accepted; with no details, output is still the summary counts."""
        import sys
        from io import StringIO
        from unittest.mock import patch, MagicMock

        args = parse(["sync", "--verbose"])
        args.home = None

        node_files = {
            "seeds": [],
            "peers": ["http://[300:a::1]/snapshot.json", "http://[300:b::1]/snapshot.json"],
            "config": {},
        }

        fake_indexer = MagicMock()

        with patch.object(cli, "_init_node", return_value=(Path("/tmp"), node_files)), \
             patch.object(cli, "Indexer", return_value=fake_indexer):
            buf = StringIO()
            with patch("sys.stdout", buf):
                cli.cmd_sync(args)

        output = buf.getvalue()
        # Summary counts always present
        self.assertIn("Accepted", output)
        self.assertIn("Rejected", output)


# ---------------------------------------------------------------------------
# _looks_like_url tests
# ---------------------------------------------------------------------------

class TestLooksLikeUrl(unittest.TestCase):

    def test_https_accepted(self):
        self.assertTrue(cli._looks_like_url("https://example.org"))

    def test_http_accepted(self):
        self.assertTrue(cli._looks_like_url("http://example.org"))

    def test_ipv6_peer_accepted(self):
        self.assertTrue(cli._looks_like_url("http://[300:abcd::1]/snapshot.json"))

    def test_bare_domain_rejected(self):
        self.assertFalse(cli._looks_like_url("example.org"))

    def test_ftp_rejected(self):
        self.assertFalse(cli._looks_like_url("ftp://example.org"))

    def test_empty_rejected(self):
        self.assertFalse(cli._looks_like_url(""))

    def test_whitespace_only_rejected(self):
        self.assertFalse(cli._looks_like_url("   "))


# ---------------------------------------------------------------------------
# append_entry tests
# ---------------------------------------------------------------------------

class TestAppendEntry(unittest.TestCase):

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self.path = Path(self._tmpdir) / "entries.txt"

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_add_to_empty_file(self):
        self.path.write_text("", encoding="utf-8")
        result = cli.append_entry(self.path, "https://example.org")
        self.assertEqual(result, "added")
        self.assertIn("https://example.org", self.path.read_text())

    def test_add_to_nonexistent_file(self):
        # append_entry opens with mode "a" — creates file if absent
        result = cli.append_entry(self.path, "https://example.org")
        self.assertEqual(result, "added")
        self.assertIn("https://example.org", self.path.read_text())

    def test_duplicate_returns_duplicate(self):
        self.path.write_text("https://example.org\n", encoding="utf-8")
        result = cli.append_entry(self.path, "https://example.org")
        self.assertEqual(result, "duplicate")

    def test_duplicate_does_not_write(self):
        self.path.write_text("https://example.org\n", encoding="utf-8")
        cli.append_entry(self.path, "https://example.org")
        lines = [l for l in self.path.read_text().splitlines() if l.strip()]
        self.assertEqual(lines, ["https://example.org"])

    def test_distinct_entries_both_written(self):
        self.path.write_text("", encoding="utf-8")
        cli.append_entry(self.path, "https://a.org")
        cli.append_entry(self.path, "https://b.org")
        content = self.path.read_text()
        self.assertIn("https://a.org", content)
        self.assertIn("https://b.org", content)

    def test_entry_ends_with_newline(self):
        self.path.write_text("", encoding="utf-8")
        cli.append_entry(self.path, "https://example.org")
        self.assertTrue(self.path.read_text().endswith("\n"))

    def test_comment_lines_not_counted_as_duplicates(self):
        self.path.write_text("# https://example.org\n", encoding="utf-8")
        result = cli.append_entry(self.path, "https://example.org")
        self.assertEqual(result, "added")


# ---------------------------------------------------------------------------
# seeds add / peers add routing tests
# ---------------------------------------------------------------------------

class TestAddSubcommandRouting(unittest.TestCase):

    def test_seeds_add_routes_to_cmd_seeds(self):
        args = parse(["seeds", "add", "https://example.org"])
        self.assertIs(args.func, cli.cmd_seeds)
        self.assertEqual(args.seeds_command, "add")
        self.assertEqual(args.url, "https://example.org")

    def test_peers_add_routes_to_cmd_peers(self):
        args = parse(["peers", "add", "http://[300:abcd::1]/snapshot.json"])
        self.assertIs(args.func, cli.cmd_peers)
        self.assertEqual(args.peers_command, "add")
        self.assertEqual(args.url, "http://[300:abcd::1]/snapshot.json")

    def test_seeds_add_requires_url_arg(self):
        parser = cli.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["seeds", "add"])

    def test_peers_add_requires_url_arg(self):
        parser = cli.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["peers", "add"])


if __name__ == "__main__":
    unittest.main()
