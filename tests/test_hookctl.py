import json
import sys
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace
from tempfile import TemporaryDirectory


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "hooks"))

import hookctl  # noqa: E402


class HookctlGovernanceConfigTests(unittest.TestCase):
    def test_load_governance_config_and_resolve_level(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".governance.yaml").write_text(
                textwrap.dedent(
                    """
                    project_level: standard
                    paths:
                      constitution: governance/constitution.md
                      traceability_source: governance/traceability-source.json
                      module_map: governance/MODULE_MAP.md
                    modules:
                      - name: app
                        paths:
                          - src/app
                        languages:
                          - node
                          - python
                    commands:
                      test: python -m pytest
                    cleanup:
                      whitelist:
                        - "*.tmp"
                    security:
                      entropy_threshold: 3.25
                      allow_nosec: true
                    """
                ).strip(),
                encoding="utf-8",
            )

            config = hookctl.load_governance_config(str(root))

            self.assertEqual(config["project_level"], "standard")
            self.assertEqual(config["paths"]["constitution"], "governance/constitution.md")
            self.assertEqual(config["modules"][0]["languages"], ["node", "python"])
            self.assertIn("*.tmp", config["cleanup"]["whitelist"])
            self.assertEqual(
                hookctl.resolve_level(SimpleNamespace(level=None, lite=False), config),
                "standard",
            )
            self.assertEqual(
                hookctl.resolve_level(SimpleNamespace(level="enterprise", lite=False), config),
                "enterprise",
            )
            self.assertEqual(
                hookctl.resolve_level(SimpleNamespace(level=None, lite=True), config),
                "lite",
            )

    def test_standard_level_skips_governance_integrity_gate(self):
        self.assertFalse(hookctl.should_verify_integrity("lite"))
        self.assertFalse(hookctl.should_verify_integrity("standard"))
        self.assertTrue(hookctl.should_verify_integrity("enterprise"))


class HookctlLanguageDetectionTests(unittest.TestCase):
    def test_detect_languages_returns_multiple_adapters_for_mixed_module(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            module = root / "src" / "api"
            module.mkdir(parents=True)
            (module / "package.json").write_text("{}", encoding="utf-8")
            (module / "handler.py").write_text("print('ok')\n", encoding="utf-8")

            config = hookctl.load_governance_config(str(root))
            languages = hookctl.detect_languages(str(root), "api", config)
            adapter_names = [
                adapter.__class__.__name__
                for adapter in hookctl.get_language_adapters(str(root), "api", config, "standard")
            ]

            self.assertEqual(languages, ["node", "python"])
            self.assertEqual(adapter_names, ["NodeAdapter", "PythonAdapter"])

    def test_java_standard_syntax_check_does_not_run_full_compile_by_default(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pom.xml").write_text("<project />\n", encoding="utf-8")
            calls = []
            original_run_cmd = hookctl.run_cmd
            try:
                hookctl.run_cmd = lambda cmd, cwd=None: calls.append((cmd, cwd)) or (0, "", "")
                config = hookctl.load_governance_config(str(root))
                adapter = hookctl.JavaAdapter(str(root), None, config, "standard")

                self.assertEqual(adapter.check_syntax(), [])
                self.assertEqual(calls, [])
            finally:
                hookctl.run_cmd = original_run_cmd


class HookctlParsingTests(unittest.TestCase):
    def test_parse_verification_cmd_supports_chinese_bold_and_table_formats(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = hookctl.load_governance_config(str(root))

            (root / "task.md").write_text(
                "*   **命令**：`python hooks/finalize.py --global`\n",
                encoding="utf-8",
            )
            self.assertEqual(
                hookctl.parse_verification_cmd(str(root), None, config),
                "python hooks/finalize.py --global",
            )

            (root / "task.md").write_text(
                "| Field | Value |\n"
                "|---|---|\n"
                "| Command | `python -m unittest discover` |\n",
                encoding="utf-8",
            )
            self.assertEqual(
                hookctl.parse_verification_cmd(str(root), None, config),
                "python -m unittest discover",
            )

    def test_parse_traceability_source_supports_json_and_complex_yaml(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_path = root / "traceability-source.json"
            json_path.write_text(
                json.dumps(
                    {
                        "requirements": [
                            {
                                "id": "REQ-JSON",
                                "source": "docs/req.md#json",
                                "prd_section": "JSON Section",
                                "module": "core",
                                "logical_entity": "ConfigLoader",
                                "acceptance_criteria": ["AC-1"],
                                "tests": ["python -m unittest"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            yaml_path = root / "traceability-source.yaml"
            yaml_path.write_text(
                textwrap.dedent(
                    """
                    requirements:
                      - id: REQ-YAML
                        source: docs/req.md#yaml
                        prd_section: |
                          Section one
                          Section two
                        module: core
                        logical_entity: TraceParser
                        acceptance_criteria:
                          - AC-2
                        tests:
                          - python -m unittest tests/test_hookctl.py
                    """
                ).strip(),
                encoding="utf-8",
            )

            json_requirements = hookctl.parse_traceability_source(str(json_path))
            yaml_requirements = hookctl.parse_traceability_source(str(yaml_path))

            self.assertEqual(json_requirements[0]["id"], "REQ-JSON")
            self.assertEqual(yaml_requirements[0]["id"], "REQ-YAML")
            self.assertIn("Section two", yaml_requirements[0]["prd_section"])

    def test_check_path_allowed_parses_nul_porcelain_paths(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []
            original_run_cmd = hookctl.run_cmd

            def fake_run_cmd(cmd, cwd=None):
                calls.append(cmd)
                if "rev-parse" in cmd:
                    return 0, str(root), ""
                if "status --porcelain" in cmd:
                    return 0, " M AI指导.md\0?? tests/test_hookctl.py\0", ""
                return 0, "", ""

            try:
                hookctl.run_cmd = fake_run_cmd
                ok, violations = hookctl.check_path_allowed(
                    str(root),
                    None,
                    ["AI指导.md", "tests"],
                )
            finally:
                hookctl.run_cmd = original_run_cmd

            self.assertTrue(any("--porcelain -z" in call for call in calls))
            self.assertTrue(ok, violations)


class HookctlSecurityScanTests(unittest.TestCase):
    def test_security_scan_reduces_false_positives_and_honors_nosec(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src"
            src.mkdir()
            (src / "app.js").write_text(
                textwrap.dedent(
                    """
                    const userToken = req.body.token;
                    const password = "";
                    const api_key = "A1b2C3d4E5f6G7h8I9j0K1l2M3n4"; // nosec
                    const client_secret = "K9xPq7LmN2vR8sTuY4zAbCdEfGhIjKl";
                    """
                ).strip(),
                encoding="utf-8",
            )
            config = hookctl.load_governance_config(str(root))

            findings = hookctl.run_security_scan(str(root), config=config)

            self.assertEqual(len([f for f in findings if f["type"] == "hardcoded_secret"]), 1)
            self.assertIn("client_secret", findings[0]["summary"])

    def test_security_scan_keeps_unignored_env_as_strong_blocker(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("TOKEN=example_placeholder\n", encoding="utf-8")
            config = hookctl.load_governance_config(str(root))

            findings = hookctl.run_security_scan(str(root), config=config)

            self.assertTrue(any(f["type"] == "unignored_env" for f in findings))


class HookctlCleanupTests(unittest.TestCase):
    """perform_cleanup performs irreversible file deletion/quarantine; guard its boundaries."""

    def _fake_git(self, root, untracked):
        entries = "".join(f"?? {p}\0" for p in untracked)

        def fake_run_cmd(cmd, cwd=None):
            if "rev-parse" in cmd:
                return 0, str(root), ""
            if "status --porcelain" in cmd:
                return 0, entries, ""
            return 0, "", ""

        return fake_run_cmd

    def test_whitelisted_files_deleted_source_preserved(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src"
            src.mkdir()
            (src / "debug.log").write_text("noise\n", encoding="utf-8")
            keep = src / "feature.py"
            keep.write_text("print('keep me')\n", encoding="utf-8")

            original = hookctl.run_cmd
            hookctl.run_cmd = self._fake_git(root, ["src/debug.log", "src/feature.py"])
            try:
                deleted, quarantined, reported, errors = hookctl.perform_cleanup(
                    str(root), None, allowed_paths=["src"]
                )
            finally:
                hookctl.run_cmd = original

            # *.log is whitelisted -> deleted; source .py is NOT -> must survive
            self.assertIn("src\\debug.log", [d.replace("/", "\\") for d in deleted])
            self.assertTrue(keep.exists(), "source file must never be auto-deleted")
            self.assertIn("src\\feature.py", [r.replace("/", "\\") for r in reported])

    def test_binary_artifact_quarantined_not_deleted(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "src"
            src.mkdir()
            artifact = src / "build.exe"
            artifact.write_bytes(b"MZ\x00\x90binary")

            original = hookctl.run_cmd
            hookctl.run_cmd = self._fake_git(root, ["src/build.exe"])
            try:
                deleted, quarantined, reported, errors = hookctl.perform_cleanup(
                    str(root), None, allowed_paths=["src"]
                )
            finally:
                hookctl.run_cmd = original

            self.assertEqual(deleted, [])
            self.assertIn("src\\build.exe", [q.replace("/", "\\") for q in quarantined])
            self.assertFalse(artifact.exists(), "binary should be moved to quarantine")
            qdir = hookctl.get_quarantine_dir(str(root))
            self.assertTrue((Path(qdir) / "build.exe").exists())

    def test_out_of_scope_file_reported_not_touched(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            outside = root / "other"
            outside.mkdir()
            stray = outside / "stray.log"
            stray.write_text("x\n", encoding="utf-8")

            original = hookctl.run_cmd
            hookctl.run_cmd = self._fake_git(root, ["other/stray.log"])
            try:
                deleted, quarantined, reported, errors = hookctl.perform_cleanup(
                    str(root), None, allowed_paths=["src"]
                )
            finally:
                hookctl.run_cmd = original

            # whitelisted by name but outside allowed scope -> reported, never deleted
            self.assertEqual(deleted, [])
            self.assertTrue(stray.exists(), "out-of-scope file must not be deleted")
            self.assertIn("other\\stray.log", [r.replace("/", "\\") for r in reported])


class HookctlIntegrityTests(unittest.TestCase):
    """Governance hash chain: sign, verify, tamper detection, self-reference exclusion."""

    def _make_project(self, tmp):
        root = Path(tmp)
        (root / "docs" / "requirements").mkdir(parents=True)
        (root / "docs" / "traceability").mkdir(parents=True)
        const = root / "docs" / "requirements" / "constitution.md"
        const.write_text(
            "# Constitution\n\ncore_principle: immutability\nsha256_hash: \"\"\n",
            encoding="utf-8",
        )
        (root / "docs" / "traceability" / "traceability-source.json").write_text(
            json.dumps({"requirements": []}), encoding="utf-8"
        )
        (root / "MODULE_MAP.md").write_text("# MODULE_MAP\n", encoding="utf-8")
        config = hookctl.load_governance_config(str(root))
        return root, const, config

    def test_sign_then_verify_passes(self):
        with TemporaryDirectory() as tmp:
            root, const, config = self._make_project(tmp)

            written = hookctl.update_constitution_hash(str(const), str(root), config)
            self.assertIsNotNone(written)
            self.assertEqual(len(written), 64)

            ok, msg = hookctl.verify_governance_integrity(str(root), config)
            self.assertTrue(ok, msg)

    def test_tampered_document_fails_verification(self):
        with TemporaryDirectory() as tmp:
            root, const, config = self._make_project(tmp)
            hookctl.update_constitution_hash(str(const), str(root), config)

            # Tamper with a governed document AFTER signing
            (root / "MODULE_MAP.md").write_text(
                "# MODULE_MAP\nmalicious edit\n", encoding="utf-8"
            )

            ok, msg = hookctl.verify_governance_integrity(str(root), config)
            self.assertFalse(ok)
            self.assertIn("integrity check failed", msg)

    def test_hash_excludes_self_reference_line(self):
        with TemporaryDirectory() as tmp:
            root, const, config = self._make_project(tmp)

            # Hash is computed with the sha256_hash line stripped, so signing
            # must be idempotent: signing twice yields the same digest.
            first = hookctl.update_constitution_hash(str(const), str(root), config)
            second = hookctl.update_constitution_hash(str(const), str(root), config)
            self.assertEqual(first, second)

    def test_missing_hash_line_reports_unsigned(self):
        with TemporaryDirectory() as tmp:
            root, const, config = self._make_project(tmp)
            const.write_text("# Constitution\n\ncore_principle: immutability\n", encoding="utf-8")

            ok, msg = hookctl.verify_governance_integrity(str(root), config)
            self.assertFalse(ok)
            self.assertIn("sha256_hash", msg)


class HookctlRunCmdTests(unittest.TestCase):
    """run_cmd must run list commands with shell=False to prevent injection."""

    def test_list_command_runs_without_shell(self):
        # A list element containing shell metacharacters must be passed through
        # as a literal argv entry, not interpreted by a shell.
        ret, stdout, _ = hookctl.run_cmd(
            [sys.executable, "-c", "import sys; print(sys.argv[1])", "a && b"]
        )
        self.assertEqual(ret, 0)
        self.assertEqual(stdout.strip(), "a && b")

    def test_node_check_uses_list_argv(self):
        captured = {}
        original = hookctl.run_cmd
        try:
            hookctl.run_cmd = lambda cmd, cwd=None: captured.setdefault("cmd", cmd) or (0, "", "")
            with TemporaryDirectory() as tmp:
                root = Path(tmp)
                src = root / "src"
                src.mkdir()
                (src / "app.js").write_text("console.log(1)\n", encoding="utf-8")
                config = hookctl.load_governance_config(str(root))
                adapter = hookctl.NodeAdapter(str(root), None, config, "standard")
                adapter.check_syntax()
        finally:
            hookctl.run_cmd = original

        self.assertIsInstance(captured.get("cmd"), list)
        self.assertEqual(captured["cmd"][:2], ["node", "--check"])


if __name__ == "__main__":
    unittest.main()
