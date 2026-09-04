import importlib
import os
import shutil
import tempfile
import unittest

import precision_worksheets.fonts as fonts_module


class TestComicFontDetection(unittest.TestCase):
    def setUp(self):
        # get_comic_font_names() caches its result globally, so give every
        # test a fresh module state to test both the found and not-found
        # branches in the same run.
        self.fonts = importlib.reload(fonts_module)
        self._env_backup = {
            key: os.environ.get(key) for key in ("WINDIR", "SystemRoot", "LOCALAPPDATA")
        }
        for key in self._env_backup:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        importlib.reload(fonts_module)

    def test_falls_back_when_no_windows_fonts_dir_present(self):
        names = self.fonts.get_comic_font_names()
        self.assertEqual(names, ("Helvetica", "Helvetica-Bold"))

    def test_registers_real_font_file_when_found(self):
        # Stand in for C:\Windows\Fonts with a real, install-anywhere
        # TrueType font (any valid .ttf proves the detection+registration
        # plumbing works, without needing an actual Windows machine here).
        real_ttf = "/usr/share/fonts/truetype/andika/Andika-Regular.ttf"
        if not os.path.isfile(real_ttf):
            self.skipTest("no local TrueType font available to stand in for comic.ttf")

        tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmpdir, ignore_errors=True)
        fonts_dir = os.path.join(tmpdir, "Fonts")
        os.makedirs(fonts_dir)
        shutil.copy(real_ttf, os.path.join(fonts_dir, "comic.ttf"))
        shutil.copy(real_ttf, os.path.join(fonts_dir, "comicbd.ttf"))
        os.environ["WINDIR"] = tmpdir

        names = self.fonts.get_comic_font_names()
        self.assertEqual(names, ("ComicSansMS", "ComicSansMS-Bold"))


if __name__ == "__main__":
    unittest.main()
