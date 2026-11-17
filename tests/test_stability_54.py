"""5.4: издатель в версионной информации, общий SSL-контекст, COM без ctypes.cast."""
import re
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class VersionInfoTests(unittest.TestCase):
    def test_publisher_in_blob(self):
        import launcher
        blob = launcher.build_version_info()
        self.assertEqual(struct.unpack('<H', blob[:2])[0], len(blob))
        s = launcher.read_version_strings(blob)
        self.assertEqual(s['CompanyName'], 'OlegBFF')
        self.assertEqual(s['FileDescription'], 'Island Pro')
        self.assertIn(b'V\0S\0_\0V\0E\0R\0S\0I\0O\0N\0_\0I\0N\0F\0O\0', blob)
        self.assertEqual(struct.unpack('<I', blob[40:44])[0], 0xFEEF04BD)           # VS_FIXEDFILEINFO.dwSignature

    def test_branding_never_breaks_launch_off_windows(self):
        import launcher
        vpy = Path('/nonexistent/python')
        self.assertEqual(launcher.branded_python(vpy, None), vpy)


class SecurityTests(unittest.TestCase):
    def test_ssl_context_is_shared(self):
        from core import security
        self.assertIs(security.ssl_context(), security.ssl_context())
        src = (ROOT / 'core' / 'security.py').read_text('utf-8')
        self.assertEqual(len(re.findall(r'=\s*ssl\.create_default_context\(\)', src)), 1)     # только в ssl_context()


class ComSafetyTests(unittest.TestCase):
    def test_no_ctypes_cast_of_com_pointers(self):
        """cast() не делает AddRef → двойной Release → access violation при сборке мусора."""
        for rel in ('system/audio_ctl.py', 'modules/spectrum.py', 'system/audio_names.py'):
            code = [ln for ln in (ROOT / rel).read_text('utf-8').splitlines() if not ln.strip().startswith('#')]
            self.assertFalse(any(re.search(r'\bcast\(', ln) for ln in code), rel)


if __name__ == '__main__':
    unittest.main()
