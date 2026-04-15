from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ACTION_FILE = REPO_ROOT / "action.yml"


def find_composer_command() -> list[str]:
    composer = shutil.which("composer")
    if composer is not None:
        return [composer]

    if shutil.which("cmd.exe") is not None:
        return ["cmd.exe", "/c", "composer"]

    raise AssertionError("Unable to find a Composer executable")


def find_php_command() -> list[str]:
    php = shutil.which("php")
    if php is not None:
        return [php]

    if shutil.which("cmd.exe") is not None:
        return ["cmd.exe", "/c", "php"]

    raise AssertionError("Unable to find a PHP executable")


COMPOSER = find_composer_command()
PHP = find_php_command()


def uses_windows_composer_from_wsl() -> bool:
    return COMPOSER[0].lower().endswith("cmd.exe")


def windows_to_wsl_path(path: str) -> Path:
    drive, rest = path[:1], path[2:]
    return Path("/mnt") / drive.lower() / rest.replace("\\", "/").lstrip("/")


def wsl_to_windows_path(path: Path) -> str:
    raw_path = str(path)
    if not raw_path.startswith("/mnt/"):
        return raw_path

    drive = raw_path[5]
    rest = raw_path[7:]
    return f"{drive.upper()}:\\{rest.replace('/', '\\')}"


def composer_repo_url(path: Path) -> str:
    if uses_windows_composer_from_wsl():
        return wsl_to_windows_path(path)

    return path.as_posix()


@contextmanager
def temporary_directory(prefix: str):
    if uses_windows_composer_from_wsl():
        temp_result = run(["cmd.exe", "/c", "echo", "%TEMP%"], cwd=REPO_ROOT)
        windows_temp = temp_result.stdout.strip()
        temp_root = windows_to_wsl_path(windows_temp)
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=prefix, dir=temp_root) as directory:
            yield directory
        return

    with tempfile.TemporaryDirectory(prefix=prefix) as directory:
        yield directory


def run(command: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if check and result.returncode != 0:
        raise AssertionError(
            f"Command failed: {' '.join(command)}\n"
            f"cwd: {cwd}\n"
            f"exit: {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    return result


def write_json(path: Path, payload: dict) -> None:
    path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf-8")


def init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    run(["git", "init", "--initial-branch=main"], cwd=path)
    run(["git", "config", "user.name", "Codex"], cwd=path)
    run(["git", "config", "user.email", "codex@example.com"], cwd=path)


def commit_all(path: Path, message: str) -> None:
    run(["git", "add", "."], cwd=path)
    run(["git", "commit", "-m", message], cwd=path)


def tag(path: Path, name: str) -> None:
    run(["git", "tag", name], cwd=path)


def make_package_repo(path: Path, payload: dict, message: str, tag_name: str | None = None) -> None:
    init_git_repo(path)
    write_json(path / "composer.json", payload)
    commit_all(path, message)
    if tag_name is not None:
        tag(path, tag_name)


def update_package_repo(path: Path, payload: dict, message: str, tag_name: str | None = None) -> None:
    write_json(path / "composer.json", payload)
    commit_all(path, message)
    if tag_name is not None:
        tag(path, tag_name)


def load_locked_version(lock_path: Path, package_name: str) -> str:
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    packages = payload.get("packages", []) + payload.get("packages-dev", [])

    for package in packages:
        if package.get("name") == package_name:
            return package["version"]

    raise AssertionError(f"Missing locked package: {package_name}")


def assert_action_structure() -> None:
    action = ACTION_FILE.read_text(encoding="utf-8")

    required_fragments = [
        "composer update $PACKAGES_TO_UPDATE --with-all-dependencies --no-install --no-scripts",
        "composer update --with-all-dependencies --no-install --no-scripts",
        "${{ github.action_path }}/scripts/validate_locked_targets.php",
        "${{ github.action_path }}/scripts/report_full_rebuild_churn.php",
        "/tmp/composer.lock.before-full-rebuild",
    ]

    for fragment in required_fragments:
        if fragment not in action:
            raise AssertionError(f"Missing expected action fragment: {fragment}")

    if 'composer show --locked --format=json "$PACKAGE_NAME"' in action:
        raise AssertionError("Validator still relies on composer show --locked for locked versions")


def alias_fixture() -> None:
    with temporary_directory(prefix="composer-alias-fixture-") as temp_dir:
        root = Path(temp_dir)
        package_repo = root / "aliased-package"
        project = root / "project"

        make_package_repo(
            package_repo,
            {
                "name": "fixture/aliased-package",
                "type": "library",
                "require": {"php": ">=8.1"},
                "extra": {"branch-alias": {"dev-main": "1.0.x-dev"}},
            },
            "Initial aliased package",
        )

        project.mkdir()
        write_json(
            project / "composer.json",
            {
                "name": "fixture/alias-project",
                "repositories": [{"type": "vcs", "url": composer_repo_url(package_repo)}],
                "require": {"fixture/aliased-package": "dev-main"},
                "minimum-stability": "dev",
                "prefer-stable": True,
            },
        )

        run([*COMPOSER, "update", "--no-install", "--no-scripts"], cwd=project)

        show_result = run(
            [*COMPOSER, "show", "--locked", "--format=json", "fixture/aliased-package"],
            cwd=project,
        )
        show_payload = json.loads(show_result.stdout)
        locked_version = load_locked_version(project / "composer.lock", "fixture/aliased-package")
        targets_file = project / "targets.txt"
        targets_file.write_text("fixture/aliased-package\tdev-main\n", encoding="utf-8")

        if "dev-main" not in show_payload["versions"]:
            raise AssertionError("Expected dev-main in composer show versions for aliased package")

        if "1.0.x-dev" not in show_payload["versions"]:
            raise AssertionError("Expected branch alias in composer show versions for aliased package")

        if locked_version != "dev-main":
            raise AssertionError(f"Expected composer.lock to store dev-main, got {locked_version}")

        run(
            [
                *PHP,
                composer_repo_url(REPO_ROOT / "scripts" / "validate_locked_targets.php"),
                composer_repo_url(targets_file),
                "composer.lock",
            ],
            cwd=project,
        )

        root_payload = json.loads((project / "composer.json").read_text(encoding="utf-8"))
        root_payload["require"]["fixture/aliased-package"] = "1.0.x-dev"
        write_json(project / "composer.json", root_payload)
        run([*COMPOSER, "update", "--no-install", "--no-scripts"], cwd=project)

        alias_locked_version = load_locked_version(project / "composer.lock", "fixture/aliased-package")
        if alias_locked_version != "dev-main":
            raise AssertionError(f"Expected branch-alias lock version to stay dev-main, got {alias_locked_version}")

        targets_file.write_text("fixture/aliased-package\t1.0.x-dev\n", encoding="utf-8")
        run(
            [
                *PHP,
                composer_repo_url(REPO_ROOT / "scripts" / "validate_locked_targets.php"),
                composer_repo_url(targets_file),
                "composer.lock",
            ],
            cwd=project,
        )

        root_payload = json.loads((project / "composer.json").read_text(encoding="utf-8"))
        root_payload["require"]["fixture/aliased-package"] = "1.0.x"
        write_json(project / "composer.json", root_payload)
        run([*COMPOSER, "update", "--no-install", "--no-scripts"], cwd=project)

        release_locked_version = load_locked_version(project / "composer.lock", "fixture/aliased-package")
        if release_locked_version != "dev-main":
            raise AssertionError(
                f"Expected release-line branch alias to keep dev-main in composer.lock, got {release_locked_version}"
            )

        targets_file.write_text("fixture/aliased-package\t1.0.x\n", encoding="utf-8")
        run(
            [
                *PHP,
                composer_repo_url(REPO_ROOT / "scripts" / "validate_locked_targets.php"),
                composer_repo_url(targets_file),
                "composer.lock",
            ],
            cwd=project,
        )


def fallback_fixture() -> None:
    with temporary_directory(prefix="composer-fallback-fixture-") as temp_dir:
        root = Path(temp_dir)
        project = root / "project"
        package_a = root / "package-a"
        package_b = root / "package-b"
        package_c = root / "package-c"
        package_d = root / "package-d"

        make_package_repo(
            package_d,
            {"name": "fixture/package-d", "type": "library", "version": "1.0.0"},
            "package-d 1.0.0",
            "1.0.0",
        )
        make_package_repo(
            package_c,
            {"name": "fixture/package-c", "type": "library", "version": "1.0.0"},
            "package-c 1.0.0",
            "1.0.0",
        )
        make_package_repo(
            package_b,
            {
                "name": "fixture/package-b",
                "type": "library",
                "version": "1.0.0",
                "require": {"fixture/package-d": "1.0.0"},
            },
            "package-b 1.0.0",
            "1.0.0",
        )
        make_package_repo(
            package_a,
            {
                "name": "fixture/package-a",
                "type": "library",
                "version": "1.0.0",
                "require": {"fixture/package-c": "1.0.0"},
            },
            "package-a 1.0.0",
            "1.0.0",
        )

        project.mkdir()
        write_json(
            project / "composer.json",
            {
                "name": "fixture/root-project",
                "repositories": [
                    {"type": "vcs", "url": composer_repo_url(package_a)},
                    {"type": "vcs", "url": composer_repo_url(package_b)},
                    {"type": "vcs", "url": composer_repo_url(package_c)},
                    {"type": "vcs", "url": composer_repo_url(package_d)},
                ],
                "require": {
                    "fixture/package-a": "1.0.0",
                    "fixture/package-b": "^1.0 || ^2.0",
                },
                "minimum-stability": "dev",
                "prefer-stable": True,
            },
        )

        run([*COMPOSER, "update", "--no-install", "--no-scripts"], cwd=project)

        update_package_repo(
            package_d,
            {"name": "fixture/package-d", "type": "library", "version": "2.0.0"},
            "package-d 2.0.0",
            "2.0.0",
        )
        update_package_repo(
            package_c,
            {
                "name": "fixture/package-c",
                "type": "library",
                "version": "2.0.0",
                "conflict": {"fixture/package-d": "<2.0.0"},
            },
            "package-c 2.0.0",
            "2.0.0",
        )
        update_package_repo(
            package_b,
            {
                "name": "fixture/package-b",
                "type": "library",
                "version": "2.0.0",
                "require": {"fixture/package-d": "2.0.0"},
            },
            "package-b 2.0.0",
            "2.0.0",
        )
        update_package_repo(
            package_a,
            {
                "name": "fixture/package-a",
                "type": "library",
                "version": "2.0.0",
                "require": {"fixture/package-c": "2.0.0"},
            },
            "package-a 2.0.0",
            "2.0.0",
        )

        root_payload = json.loads((project / "composer.json").read_text(encoding="utf-8"))
        root_payload["require"]["fixture/package-a"] = "2.0.0"
        write_json(project / "composer.json", root_payload)

        scoped = run(
            [
                *COMPOSER,
                "update",
                "fixture/package-a",
                "--with-all-dependencies",
                "--no-install",
                "--no-scripts",
            ],
            cwd=project,
            check=False,
        )

        if scoped.returncode == 0:
            raise AssertionError("Expected scoped update to fail before full fallback")

        if "conflict" not in f"{scoped.stdout}\n{scoped.stderr}".lower():
            raise AssertionError("Expected scoped update failure to include a dependency conflict")

        before_full_rebuild = project / "composer.lock.before-full-rebuild"
        shutil.copyfile(lock_path := project / "composer.lock", before_full_rebuild)

        run(
            [*COMPOSER, "update", "--with-all-dependencies", "--no-install", "--no-scripts"],
            cwd=project,
        )

        targets_file = project / "targets.txt"
        targets_file.write_text("fixture/package-a\t2.0.x\n", encoding="utf-8")
        updated_packages_file = project / "updated_packages.txt"
        updated_packages_file.write_text("fixture/package-a\n", encoding="utf-8")
        expected_versions = {
            "fixture/package-a": "2.0.0",
            "fixture/package-b": "2.0.0",
            "fixture/package-c": "2.0.0",
            "fixture/package-d": "2.0.0",
        }

        for package_name, expected_version in expected_versions.items():
            locked_version = load_locked_version(lock_path, package_name)
            if locked_version != expected_version:
                raise AssertionError(
                    f"Expected {package_name} to be locked to {expected_version}, got {locked_version}"
                )

        run(
            [
                *PHP,
                composer_repo_url(REPO_ROOT / "scripts" / "validate_locked_targets.php"),
                composer_repo_url(targets_file),
                "composer.lock",
            ],
            cwd=project,
        )

        churn_report = run(
            [
                *PHP,
                composer_repo_url(REPO_ROOT / "scripts" / "report_full_rebuild_churn.php"),
                composer_repo_url(before_full_rebuild),
                "composer.lock",
                composer_repo_url(updated_packages_file),
            ],
            cwd=project,
        )

        report_output = f"{churn_report.stdout}\n{churn_report.stderr}"
        for package_name in ("fixture/package-b", "fixture/package-c", "fixture/package-d"):
            if package_name not in report_output:
                raise AssertionError(f"Expected churn report to mention {package_name}")


def reference_only_churn_fixture() -> None:
    with temporary_directory(prefix="composer-churn-fixture-") as temp_dir:
        root = Path(temp_dir)
        before_lock = root / "before.lock"
        after_lock = root / "after.lock"
        bumped_packages_file = root / "updated_packages.txt"

        write_json(
            before_lock,
            {
                "packages": [
                    {
                        "name": "fixture/reference-only-change",
                        "version": "dev-main",
                        "source": {"reference": "1111111"},
                        "dist": {"reference": "1111111"},
                    },
                    {
                        "name": "fixture/bumped-package",
                        "version": "dev-main",
                        "source": {"reference": "aaaaaaa"},
                        "dist": {"reference": "aaaaaaa"},
                    },
                ]
            },
        )
        write_json(
            after_lock,
            {
                "packages": [
                    {
                        "name": "fixture/reference-only-change",
                        "version": "dev-main",
                        "source": {"reference": "2222222"},
                        "dist": {"reference": "2222222"},
                    },
                    {
                        "name": "fixture/bumped-package",
                        "version": "dev-main",
                        "source": {"reference": "bbbbbbb"},
                        "dist": {"reference": "bbbbbbb"},
                    },
                ]
            },
        )
        bumped_packages_file.write_text("fixture/bumped-package\n", encoding="utf-8")

        churn_report = run(
            [
                *PHP,
                composer_repo_url(REPO_ROOT / "scripts" / "report_full_rebuild_churn.php"),
                composer_repo_url(before_lock),
                composer_repo_url(after_lock),
                composer_repo_url(bumped_packages_file),
            ],
            cwd=root,
        )

        report_output = f"{churn_report.stdout}\n{churn_report.stderr}"
        if "fixture/reference-only-change" not in report_output:
            raise AssertionError("Expected churn report to include reference-only dependency changes")

        if "1111111" not in report_output or "2222222" not in report_output:
            raise AssertionError("Expected churn report to show the before and after references")

        if "fixture/bumped-package" in report_output:
            raise AssertionError("Expected churn report to ignore explicitly bumped packages")


def main() -> None:
    assert_action_structure()
    alias_fixture()
    fallback_fixture()
    reference_only_churn_fixture()
    print("PASS: action structure, alias handling, fallback behavior, and churn reporting verified")


if __name__ == "__main__":
    main()
