#!/usr/bin/env python3
"""Exports the coverage cell's reports: lcov for libcppjit, Cobertura XML for cppjit.

libcppjit is built with clang's source-based instrumentation, so the coverage
mapping travels inside the installed extension and the raw profiles land where
LLVM_PROFILE_FILE pointed the test run. llvm-profdata merges them into one
indexed profile and llvm-cov renders lcov for the sources under src/ only:
headers from LLVM, CppInterOp and the C++ standard library are instantiated in
cppjit's translation units too, and llvm-cov reports everything it mapped
unless told which sources count.

The Python report is rendered from the repository root, where the pyproject's
[tool.coverage.paths] maps the site-packages install back onto python/cppjit;
the test run itself, from test/, cannot apply that mapping.

Both reports are checked before they leave: llvm-cov falls back to every file
when its source filter matches nothing, and an unmapped Python report keeps
site-packages paths that Codecov cannot place in the repository.

Usage: export_coverage.py --llvm-prefix DIR --profiles DIR --python-data FILE
                          --source-root DIR --out DIR
"""

import argparse
import importlib.util
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PACKAGE = "cppjit"


def installed_package_dir(package: str = PACKAGE) -> Path:
    """The directory of the installed package, located without importing it."""
    spec = importlib.util.find_spec(package)
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError(f"{package} is not installed")
    return Path(next(iter(spec.submodule_search_locations)))


def extension_in(package_dir: Path, package: str = PACKAGE) -> Path:
    """The one extension module inside the package directory."""
    found = sorted(package_dir.glob(f"lib{package}*"))
    if len(found) != 1:
        raise RuntimeError(f"expected one lib{package}* in {package_dir}, found {found}")
    return found[0]


def merge_command(llvm_prefix: Path, profiles: Path, profdata: Path) -> list[str]:
    raw = sorted(profiles.glob("*.profraw"))
    if not raw:
        raise RuntimeError(f"no .profraw under {profiles}; "
                           "was LLVM_PROFILE_FILE set for the test run?")
    return [str(llvm_prefix / "bin" / "llvm-profdata"), "merge", "-sparse",
            "-o", str(profdata), *map(str, raw)]


def export_command(llvm_prefix: Path, profdata: Path, extension: Path,
                   sources: Path) -> list[str]:
    return [str(llvm_prefix / "bin" / "llvm-cov"), "export", "-format=lcov",
            f"-instr-profile={profdata}", str(extension), str(sources)]


def check_lcov(text: str, sources: Path) -> None:
    """Every record must sit under `sources`."""
    files = [line[3:] for line in text.splitlines() if line.startswith("SF:")]
    if not files:
        raise RuntimeError("the lcov report names no source file")
    prefix = f"{sources}{os.sep}"
    outside = [f for f in files if not f.startswith(prefix)]
    if outside:
        raise RuntimeError(f"lcov records outside {sources}: {outside[:5]}")


def xml_command(rcfile: Path, out: Path) -> list[str]:
    return [sys.executable, "-m", "coverage", "xml", f"--rcfile={rcfile}",
            "-o", str(out)]


def check_xml(text: str, package_root: str = f"python/{PACKAGE}/") -> None:
    """Every file must be a repository path under the package sources."""
    names = [c.get("filename", "") for c in ET.fromstring(text).iter("class")]
    if not names:
        raise RuntimeError("the XML report names no file")
    outside = [n for n in names if not n.startswith(package_root)]
    if outside:
        raise RuntimeError(f"XML records outside {package_root}: {outside[:5]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--llvm-prefix", type=Path, required=True,
                        help="LLVM install whose bin/ holds llvm-profdata and llvm-cov")
    parser.add_argument("--profiles", type=Path, required=True,
                        help="directory holding the .profraw files")
    parser.add_argument("--python-data", type=Path, required=True,
                        help="coverage.py data file written by pytest-cov")
    parser.add_argument("--source-root", type=Path, required=True,
                        help="the cppjit checkout")
    parser.add_argument("--out", type=Path, required=True,
                        help="directory receiving cppjit.lcov and python.xml")
    args = parser.parse_args()

    root = Path(os.path.abspath(args.source_root))
    sources = root / "src"
    args.out.mkdir(parents=True, exist_ok=True)

    profdata = args.profiles / f"{PACKAGE}.profdata"
    subprocess.run(merge_command(args.llvm_prefix, args.profiles, profdata), check=True)
    extension = extension_in(installed_package_dir())
    lcov = subprocess.run(export_command(args.llvm_prefix, profdata, extension, sources),
                          check=True, capture_output=True, text=True).stdout
    check_lcov(lcov, sources)
    (args.out / f"{PACKAGE}.lcov").write_text(lcov)

    xml_out = args.out / "python.xml"
    subprocess.run(xml_command(root / "pyproject.toml", xml_out), check=True, cwd=root,
                   env={**os.environ, "COVERAGE_FILE": str(args.python_data)})
    check_xml(xml_out.read_text())

    print(f"coverage reports in {args.out}: {PACKAGE}.lcov, python.xml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
