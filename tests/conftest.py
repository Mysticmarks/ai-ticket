from __future__ import annotations

import importlib
import inspect
import os
import sys
import tokenize
from collections import defaultdict
from pathlib import Path
from trace import Trace
from typing import Dict, Iterable, List, Set, Tuple
from unittest import mock

import pytest

PROJECT_ROOT = Path.cwd()
SRC_PATH = PROJECT_ROOT / "src"
if SRC_PATH.exists() and str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


@pytest.fixture
def mocker():
    patchers: List[mock._patch] = []

    class _Mocker:
        def patch(self, target, *args, **kwargs):
            patcher = mock.patch(target, *args, **kwargs)
            patched = patcher.start()
            patchers.append(patcher)
            return patched

    try:
        yield _Mocker()
    finally:
        while patchers:
            patchers.pop().stop()


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("cov")
    group.addoption(
        "--cov",
        action="append",
        default=[],
        metavar="MODULE",
        help="Measure coverage for the specified module or package.",
    )
    group.addoption(
        "--cov-report",
        action="append",
        default=[],
        metavar="TYPE",
        help="Generate coverage report of the given type (term-missing, xml).",
    )
    group.addoption(
        "--cov-fail-under",
        action="store",
        default=None,
        type=float,
        metavar="PERCENT",
        help="Fail if the total coverage percentage is below this threshold.",
    )


def pytest_configure(config: pytest.Config) -> None:
    cov_targets: List[str] = config.getoption("--cov")
    if not cov_targets:
        return

    ignoredirs = [sys.prefix, sys.exec_prefix]
    tracer = Trace(count=True, trace=False, ignoredirs=ignoredirs)

    config._trace_cov_tracer = tracer  # type: ignore[attr-defined]
    config._trace_cov_targets = cov_targets  # type: ignore[attr-defined]
    config._trace_cov_fail_under = config.getoption("--cov-fail-under")  # type: ignore[attr-defined]
    config._trace_cov_reports = config.getoption("--cov-report")  # type: ignore[attr-defined]

    sys.settrace(tracer.globaltrace)


def pytest_sessionstart(session: pytest.Session) -> None:
    # Trace already activated during configure.
    tracer: Trace | None = getattr(session.config, "_trace_cov_tracer", None)
    if tracer:
        sys.settrace(tracer.globaltrace)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    tracer: Trace | None = getattr(session.config, "_trace_cov_tracer", None)
    if not tracer:
        return

    sys.settrace(None)
    results = tracer.results()

    executed = _executed_line_mapping(results.counts)
    target_files = _collect_target_files(session.config._trace_cov_targets)  # type: ignore[attr-defined]
    file_stats = _compute_file_stats(target_files, executed)

    total_covered = sum(stats["covered"] for stats in file_stats.values())
    total_lines = sum(stats["statements"] for stats in file_stats.values())
    percent = (total_covered / total_lines * 100.0) if total_lines else 100.0

    reports: List[str] = session.config._trace_cov_reports  # type: ignore[attr-defined]
    terminal = session.config.pluginmanager.get_plugin("terminalreporter")
    if terminal and reports:
        if any(rep in ("term", "term-missing") for rep in reports):
            _write_terminal_report(terminal, file_stats, percent)
        if any(rep == "xml" for rep in reports):
            _write_xml_report(file_stats, percent)

    fail_under = session.config._trace_cov_fail_under  # type: ignore[attr-defined]
    if fail_under is not None and percent < fail_under:
        session.exitstatus = 1
        if terminal:
            terminal.write_line(
                f"FAIL Required test coverage of {fail_under:.2f}% not reached. Total coverage: {percent:.2f}%",
                red=True,
            )


def _executed_line_mapping(counts: Dict[Tuple[str, int], int]) -> Dict[Path, Set[int]]:
    executed: Dict[Path, Set[int]] = defaultdict(set)
    for (filename, lineno), hits in counts.items():
        if hits <= 0:
            continue
        try:
            path = Path(filename).resolve()
        except OSError:
            continue
        executed[path].add(lineno)
    return executed


def _collect_target_files(targets: Iterable[str]) -> Dict[Path, Set[int]]:
    files: Dict[Path, Set[int]] = {}
    for target in targets:
        module = importlib.import_module(target)
        module_files: List[Path] = []
        if getattr(module, "__path__", None):
            for package_path in module.__path__:  # type: ignore[attr-defined]
                for root, _, filenames in os.walk(package_path):
                    for filename in filenames:
                        if filename.endswith(".py"):
                            module_files.append(Path(root, filename).resolve())
        else:
            source_file = inspect.getsourcefile(module)
            if source_file:
                module_files.append(Path(source_file).resolve())

        for file_path in module_files:
            files[file_path] = _determine_executable_lines(file_path)
    return files


def _determine_executable_lines(file_path: Path) -> Set[int]:
    executable: Set[int] = set()
    try:
        with file_path.open("r", encoding="utf-8") as handle:
            tokens = tokenize.generate_tokens(handle.readline)
            for token in tokens:
                if token.type in {tokenize.NEWLINE, tokenize.NL, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT, tokenize.STRING}:
                    continue
                executable.add(token.start[0])
    except OSError:
        return executable
    return executable


def _compute_file_stats(
    target_files: Dict[Path, Set[int]],
    executed: Dict[Path, Set[int]],
) -> Dict[Path, Dict[str, object]]:
    stats: Dict[Path, Dict[str, object]] = {}
    for file_path, executable in target_files.items():
        executed_lines = executed.get(file_path, set())
        covered = len(executable & executed_lines)
        statements = len(executable)
        missing = sorted(executable - executed_lines)
        percent = (covered / statements * 100.0) if statements else 100.0
        stats[file_path] = {
            "statements": statements,
            "covered": covered,
            "missing": missing,
            "percent": percent,
            "executed": sorted(executable_lines)
            if (executable_lines := executable & executed_lines)
            else [],
        }
    return stats


def _write_terminal_report(terminal, file_stats: Dict[Path, Dict[str, object]], percent: float) -> None:
    terminal.write_line("Coverage report:")
    for file_path, stats in sorted(file_stats.items()):
        rel_path = file_path.relative_to(Path.cwd()) if file_path.is_relative_to(Path.cwd()) else file_path
        terminal.write_line(
            f"  {rel_path}: {stats['percent']:.2f}% ({stats['covered']}/{stats['statements']})"
        )
        missing: List[int] = stats["missing"]  # type: ignore[assignment]
        if missing:
            missing_str = ", ".join(str(line) for line in missing)
            terminal.write_line(f"    Missing lines: {missing_str}")
    terminal.write_line(f"Total coverage: {percent:.2f}%")


def _write_xml_report(file_stats: Dict[Path, Dict[str, object]], percent: float) -> None:
    try:
        from xml.etree.ElementTree import Element, SubElement, ElementTree
    except ImportError:
        return

    coverage_el = Element(
        "coverage",
        attrib={
            "branch-rate": "0",
            "line-rate": f"{percent / 100:.4f}",
            "version": "trace-plugin-1",
        },
    )
    packages_el = SubElement(coverage_el, "packages")
    package_el = SubElement(
        packages_el,
        "package",
        attrib={"name": "", "branch-rate": "0", "line-rate": f"{percent / 100:.4f}"},
    )
    classes_el = SubElement(package_el, "classes")

    project_root = Path.cwd()
    for file_path, stats in sorted(file_stats.items()):
        rel_path = file_path.relative_to(project_root) if file_path.is_relative_to(project_root) else file_path
        class_el = SubElement(
            classes_el,
            "class",
            attrib={
                "name": rel_path.stem,
                "filename": str(rel_path),
                "branch-rate": "0",
                "line-rate": f"{stats['percent']/100:.4f}",
            },
        )
        lines_el = SubElement(class_el, "lines")
        executed_lines: List[int] = stats["executed"]  # type: ignore[assignment]
        missing_lines: List[int] = stats["missing"]  # type: ignore[assignment]
        for line in executed_lines:
            SubElement(lines_el, "line", attrib={"number": str(line), "hits": "1"})
        for line in missing_lines:
            SubElement(lines_el, "line", attrib={"number": str(line), "hits": "0"})

    tree = ElementTree(coverage_el)
    tree.write("coverage.xml", encoding="utf-8", xml_declaration=True)
