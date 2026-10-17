"""Lightweight tests runnable without PySide6, Windows or audio hardware."""
import hashlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from src.donathon import speech_component as c


class MockResponse(io.BytesIO):
    def __init__(self, contents):
        super().__init__(contents)
        self.headers = {"Content-Length": str(len(contents))}
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        self.close()


class SpeechComponentTests(unittest.TestCase):
    def test_install_from_trusted_release_and_reject_corrupt_zip(self):
        contents = io.BytesIO()
        with zipfile.ZipFile(contents, 'w') as z:
            z.writestr('DonathonSpeechWorker/DonathonSpeechWorker.exe', b'pretend worker for installation test')
            z.writestr('DonathonSpeechWorker/_internal/module.dll', b'dummy')
        contents = contents.getvalue()
        manifest = {"version": "0.9.4-beta1", "url": "https://github.com/tester/repo/releases/download/v0.9.4-beta1/speech.zip", "sha256": hashlib.sha256(contents).hexdigest()}
        with tempfile.TemporaryDirectory() as base:
            target = Path(base)/'speech'
            with patch.object(c, 'COMPONENT_DIR', target), patch.object(c, 'read_manifest', return_value=manifest), patch.object(c.urllib.request, 'urlopen', side_effect=lambda *a, **k: MockResponse(contents)):
                messages=[]
                self.assertFalse(c.component_installed())
                c.install_component(messages.append)
                self.assertTrue(c.component_installed())
                self.assertIn('установлен', messages[-1])
                self.assertTrue((target/'DonathonSpeechWorker'/'DonathonSpeechWorker.exe').exists())
        with tempfile.TemporaryDirectory() as base:
            target = Path(base)/'speech'
            bad = {**manifest, 'sha256': '0'*64}
            with patch.object(c, 'COMPONENT_DIR', target), patch.object(c, 'read_manifest', return_value=bad), patch.object(c.urllib.request, 'urlopen', side_effect=lambda *a, **k: MockResponse(contents)):
                with self.assertRaisesRegex(RuntimeError, 'Контрольная сумма'):
                    c.install_component(lambda _: None)
                self.assertFalse(c.component_installed())

    def test_zip_traversal_rejected(self):
        contents = io.BytesIO()
        with zipfile.ZipFile(contents, 'w') as z:
            z.writestr('../escape.exe', b'bad')
            z.writestr('DonathonSpeechWorker/DonathonSpeechWorker.exe', b'test')
        contents = contents.getvalue()
        manifest = {"url": "https://github.com/tester/repo/releases/download/v0.9.4-beta1/speech.zip", "sha256": hashlib.sha256(contents).hexdigest()}
        with tempfile.TemporaryDirectory() as base:
            with patch.object(c, 'COMPONENT_DIR', Path(base)/'speech'), patch.object(c, 'read_manifest', return_value=manifest), patch.object(c.urllib.request, 'urlopen', side_effect=lambda *a, **k: MockResponse(contents)):
                with self.assertRaisesRegex(RuntimeError, 'Небезопасный'):
                    c.install_component(lambda _: None)
                self.assertFalse((Path(base)/'escape.exe').exists())


if __name__ == '__main__':
    unittest.main()
