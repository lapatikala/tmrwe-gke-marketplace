#!/usr/bin/env python3
"""Static verification of the TMR-WE Marketplace package.

Two kinds of check run here.

The first is a boundary gate: this repository is public, and the TMR-WE
runtime is not. An earlier revision of this package accidentally carried the
full runtime source into a public repository. That must never recur silently,
so this test fails if runtime source reappears — it inspects the real
repository tree rather than a fixture, because only the real tree is what
gets published.

The second is a packaging gate: the files and guards Google Cloud Marketplace
requires are present, and the chart provisions credentials or requires a
complete external credential pair.

Run offline, no dependencies:

    python tests/verify_package.py

Cluster-level install/uninstall testing is described in docs/user-guide.md
and is not attempted here.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

# Runtime package names that must never appear in this public repository.
FORBIDDEN_RUNTIME_DIRS = ("tmr_core", "tmr_sdk", "domains", "research", "evidence")

# Credential material that must never be committed.
SECRET_PATTERNS = (
    re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
    re.compile(r"BEGIN CERTIFICATE"),
    re.compile(r"\bbearer\s+[A-Za-z0-9._-]{16,}", re.IGNORECASE),
)

REQUIRED_FILES = (
    "LICENSE",
    "README.md",
    "schema.yaml",
    "deployer/Dockerfile",
    "docs/user-guide.md",
    "chart/tmrwe/Chart.yaml",
    "chart/tmrwe/values.yaml",
    "chart/tmrwe/templates/application.yaml",
    "chart/tmrwe/templates/deployment.yaml",
    "chart/tmrwe/templates/service.yaml",
    "chart/tmrwe/templates/tester.yaml",
    "tester/Dockerfile",
)

failures: list[str] = []
checks = 0


def check(condition: bool, description: str, detail: str = "") -> None:
    global checks
    checks += 1
    if condition:
        print(f"[PASS] {description}")
    else:
        message = f"{description}{': ' + detail if detail else ''}"
        print(f"[FAIL] {message}")
        failures.append(message)


def tracked_files() -> list[Path]:
    """Every file in the repository except .git internals."""
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file() and ".git" not in path.parts
    ]


def main() -> int:
    files = tracked_files()

    # --- Boundary: no runtime source in a public repository -----------------

    present_runtime_dirs = [
        name for name in FORBIDDEN_RUNTIME_DIRS if (ROOT / name).exists()
    ]
    check(
        not present_runtime_dirs,
        "no runtime source directories are present",
        f"found {present_runtime_dirs}",
    )

    stray_python = [
        path.relative_to(ROOT).as_posix()
        for path in files
        if path.suffix == ".py" and path.parts[len(ROOT.parts)] != "tests"
    ]
    check(
        not stray_python,
        "no Python modules outside tests/",
        f"found {stray_python}",
    )

    # --- Boundary: no credential material -----------------------------------

    leaked: list[str] = []
    for path in files:
        if path.suffix in {".png", ".jpg", ".gz", ".tgz", ".whl"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        # This file names the patterns it searches for; skip itself.
        if path.resolve() == Path(__file__).resolve():
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                leaked.append(path.relative_to(ROOT).as_posix())
                break
    check(not leaked, "no credential material is committed", f"found in {leaked}")

    # --- Packaging: Marketplace-required files ------------------------------

    missing = [name for name in REQUIRED_FILES if not (ROOT / name).is_file()]
    check(not missing, "all Marketplace-required files are present", f"missing {missing}")

    # --- Packaging: the deployer carries config only ------------------------

    dockerfile = (ROOT / "deployer" / "Dockerfile").read_text(encoding="utf-8")
    check(
        "deployer_helm" in dockerfile,
        "deployer builds from the Marketplace deployer base image",
    )
    check(
        not any(name in dockerfile for name in ("tmr_core", "tmr_sdk", "domains")),
        "deployer image copies no runtime source",
    )

    # --- Packaging: the chart provisions credentials safely -----------------

    deployment = (ROOT / "chart" / "tmrwe" / "templates" / "deployment.yaml").read_text(
        encoding="utf-8"
    )
    check(
        "TLS_CERTIFICATE_CRT" in deployment
        and "TLS_CERTIFICATE_KEY" in deployment
        and "authToken" in deployment,
        "chart provisions generated TLS and auth credentials",
    )
    check(
        "must be supplied together" in deployment,
        "chart rejects a partial external credential pair",
    )
    check(
        "--mtls-client-ca-file" in deployment,
        "chart configures mutual TLS client verification",
    )
    check(
        "readOnlyRootFilesystem" in (ROOT / "chart" / "tmrwe" / "values.yaml").read_text(encoding="utf-8"),
        "chart runs with a read-only root filesystem",
    )

    values = (ROOT / "chart" / "tmrwe" / "values.yaml").read_text(encoding="utf-8")
    check(
        "limits" in values and "requests" in values,
        "chart declares explicit CPU and memory budgets",
    )

    # --- Packaging: Application resource ------------------------------------

    application = (ROOT / "chart" / "tmrwe" / "templates" / "application.yaml").read_text(
        encoding="utf-8"
    )
    check(
        "kind: Application" in application and "app.k8s.io" in application,
        "chart declares the Marketplace Application resource",
    )

    tester = (ROOT / "chart" / "tmrwe" / "templates" / "tester.yaml").read_text(
        encoding="utf-8"
    )
    check(
        "marketplace.cloud.google.com/verification: test" in tester
        and "tmrwe.api.v1.WorldEngine/GetCapabilities" in tester
        and "secretKeyRef" in tester,
        "chart declares an authenticated gRPC verification tester",
    )

    # --- Claim discipline ---------------------------------------------------

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "user-guide.md").read_text(encoding="utf-8")
    overclaim = re.compile(r"production[- ]ready", re.IGNORECASE)
    for name, text in (("README.md", readme), ("docs/user-guide.md", guide)):
        claims = overclaim.findall(text)
        negated = len(re.findall(r"not\s+(?:yet\s+)?(?:be\s+)?declared production|not\*\* yet declared production|\*\*not\*\* yet", text, re.IGNORECASE))
        check(
            not claims or negated > 0,
            f"{name} does not claim production readiness",
            f"{len(claims)} unqualified mentions",
        )

    print()
    print(f"{checks - len(failures)}/{checks} checks passed")
    if failures:
        print("PACKAGE VERIFICATION: FAIL", file=sys.stderr)
        return 1
    print("PACKAGE VERIFICATION: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
