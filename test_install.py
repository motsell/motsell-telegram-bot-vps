import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class InstallationTests(unittest.TestCase):
    def run_install(self, directory, prepare=None):
        source = Path(__file__).resolve().parent
        root = Path(directory)
        paths = {
            "/opt/motsell-bot-demo": root / "opt" / "motsell-bot-demo",
            "/etc/motsell-bot-demo.env": root / "etc" / "motsell-bot-demo.env",
            "/etc/systemd/system/motsell-bot-demo.service": root / "etc" / "systemd" / "system" / "motsell-bot-demo.service",
        }
        for path in paths.values():
            path.parent.mkdir(parents=True, exist_ok=True)
        if prepare:
            prepare(paths)
        script = (source / "README.md").read_text().split("```sh\n", 1)[1].split("```", 1)[0]
        script = script.replace("sudo ", "")
        for original, replacement in paths.items():
            script = script.replace(original, str(replacement))
        self.assertNotIn("/opt/", script.replace(str(root) + "/opt/", ""))
        self.assertNotIn("/etc/", script.replace(str(root) + "/etc/", ""))
        return subprocess.run(["/bin/sh", "-c", script], cwd=source, capture_output=True, text=True,
                              env={"PATH": "/usr/bin:/bin"}, timeout=10), paths

    def test_new_install_then_repeat_preserves_files_and_token(self):
        with tempfile.TemporaryDirectory() as directory:
            result, paths = self.run_install(directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            token = paths["/etc/motsell-bot-demo.env"]
            self.assertEqual(token.stat().st_mode & 0o777, 0o600)
            token.write_text("BOT_TOKEN=existing-private-token\n")
            before = hashlib.sha256(token.read_bytes()).hexdigest()
            result, _ = self.run_install(directory)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(hashlib.sha256(token.read_bytes()).hexdigest(), before)

    def test_existing_token_prevents_all_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            def prepare(paths):
                paths["/etc/motsell-bot-demo.env"].write_text("keep-me")
            result, paths = self.run_install(directory, prepare)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(paths["/opt/motsell-bot-demo"].exists())
            self.assertEqual(paths["/etc/motsell-bot-demo.env"].read_text(), "keep-me")

    def test_dangling_symlink_is_not_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "must-not-be-created"
            def prepare(paths):
                os.symlink(destination, paths["/etc/motsell-bot-demo.env"])
            result, paths = self.run_install(directory, prepare)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(destination.exists())
            self.assertTrue(paths["/etc/motsell-bot-demo.env"].is_symlink())


if __name__ == "__main__":
    unittest.main()
