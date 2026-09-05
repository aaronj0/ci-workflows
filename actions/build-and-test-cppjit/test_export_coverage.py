#!/usr/bin/env python3
"""Unit tests for export_coverage."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import export_coverage as ec  # noqa: E402

ROOT = Path("/w/cppjit")
LCOV_OK = ("SF:/w/cppjit/src/cpyrt/Converters.cxx\nDA:1,1\nend_of_record\n"
           "SF:/w/cppjit/src/interop/interop_wrapper.cxx\nDA:1,0\nend_of_record\n")
LCOV_LEAK = LCOV_OK + "SF:/usr/lib/llvm-21/include/llvm/ADT/StringRef.h\nend_of_record\n"
XML = "<coverage><packages><package><classes>{}</classes></package></packages></coverage>"
CLASS = '<class name="{0}" filename="{1}"/>'


class TestExtension(unittest.TestCase):
    def test_the_one_extension_is_found(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "libcppjit.so").touch()
            self.assertEqual(ec.extension_in(Path(d)).name, "libcppjit.so")

    def test_none_or_several_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                ec.extension_in(Path(d))
            (Path(d) / "libcppjit.so").touch()
            (Path(d) / "libcppjit.cpython-313-x86_64-linux-gnu.so").touch()
            with self.assertRaises(RuntimeError):
                ec.extension_in(Path(d))


class TestCommands(unittest.TestCase):
    def test_merge_needs_raw_profiles(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError):
                ec.merge_command(Path("/llvm"), Path(d), Path(d) / "x.profdata")
            (Path(d) / "cppjit-1234_0.profraw").touch()
            cmd = ec.merge_command(Path("/llvm"), Path(d), Path(d) / "x.profdata")
            self.assertEqual(cmd[:3], ["/llvm/bin/llvm-profdata", "merge", "-sparse"])
            self.assertTrue(cmd[-1].endswith("cppjit-1234_0.profraw"))

    def test_export_restricts_to_the_sources(self):
        cmd = ec.export_command(Path("/llvm"), Path("/p/x.profdata"),
                                Path("/sp/cppjit/libcppjit.so"), ROOT / "src")
        self.assertEqual(cmd[:3], ["/llvm/bin/llvm-cov", "export", "-format=lcov"])
        self.assertEqual(cmd[-2:], ["/sp/cppjit/libcppjit.so", "/w/cppjit/src"])


class TestChecks(unittest.TestCase):
    def test_lcov_under_the_sources_passes(self):
        ec.check_lcov(LCOV_OK, ROOT / "src")

    def test_an_empty_lcov_is_an_error(self):
        with self.assertRaises(RuntimeError):
            ec.check_lcov("", ROOT / "src")

    def test_lcov_naming_foreign_headers_is_an_error(self):
        # llvm-cov reports every mapped file when its source filter
        # matched nothing, and exits 0.
        with self.assertRaises(RuntimeError):
            ec.check_lcov(LCOV_LEAK, ROOT / "src")

    def test_xml_with_repository_paths_passes(self):
        ec.check_xml(XML.format(CLASS.format("ll.py", "python/cppjit/ll.py")))

    def test_xml_keeping_site_packages_paths_is_an_error(self):
        # coverage.py leaves the path alone when the mapping target does not
        # exist relative to its working directory.
        text = XML.format(
            CLASS.format("ll.py", "python/cppjit/ll.py")
            + CLASS.format("types.py", "/venv/lib/python3.13/site-packages/cppjit/types.py"))
        with self.assertRaises(RuntimeError):
            ec.check_xml(text)

    def test_an_empty_xml_is_an_error(self):
        with self.assertRaises(RuntimeError):
            ec.check_xml(XML.format(""))


if __name__ == "__main__":
    unittest.main()
