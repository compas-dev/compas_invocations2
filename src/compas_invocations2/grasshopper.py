"""
Adapted from: https://github.com/diffCheckOrg/diffCheck/blob/main/invokes/yakerize.py

Yakerize.py was originally developed as part of the DiffCheck plugin by
Andrea Settimi, Damien Gilliard, Eleni Skevaki, Marirena Kladeftira (IBOIS, CRCL, EPFL) in 2024.
It is distributed under the MIT License, provided this attribution is retained.
"""

import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List
from typing import Optional

import invoke
import requests
import tomlkit

from compas_invocations2.console import chdir

YAK_URL = r"https://files.mcneel.com/yak/tools/latest/yak.exe"

# The `yak` CLI shipped inside the Rhino application bundle on macOS.
RHINO_YAK_PATHS = [
    "/Applications/Rhino 9.app/Contents/Resources/bin/yak",
    "/Applications/Rhino 8.app/Contents/Resources/bin/yak",
    "/Applications/Rhino 7.app/Contents/Resources/bin/yak",
]


def _download_yak_executable(target_dir: str):
    response = requests.get(YAK_URL)
    if response.status_code != 200:
        raise ValueError(f"Failed to download the yak.exe from url:{YAK_URL} with error : {response.status_code}")

    # absolute, because callers run yak from inside a different working directory
    target_path = os.path.abspath(os.path.join(target_dir, "yak.exe"))
    with open(target_path, "wb") as f:
        f.write(response.content)
    return target_path


def _find_native_yak() -> Optional[str]:
    """Return the path to a natively runnable ``yak`` CLI, if one is installed."""
    for path in RHINO_YAK_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return shutil.which("yak")


def _get_yak_command(download_dir: str) -> List[str]:
    """Return the argv prefix used to invoke yak, downloading ``yak.exe`` if needed.

    The only yak binary McNeel publishes for download is a .NET Framework ``yak.exe``.
    On Windows it runs as-is. Elsewhere it needs a runtime, so we prefer the native
    ``yak`` CLI that ships inside the Rhino application bundle (macOS) or is otherwise
    on PATH, and fall back to running the downloaded ``yak.exe`` under Mono.
    """
    if platform.system() == "Windows":
        return [_download_yak_executable(download_dir)]

    native_yak = _find_native_yak()
    if native_yak:
        return [native_yak]

    mono = shutil.which("mono")
    if not mono:
        raise invoke.Exit(
            "No yak executable available. Install Rhino (which bundles the `yak` CLI) or install Mono (`brew install mono`) so that the downloaded yak.exe can be run."
        )
    return [mono, _download_yak_executable(download_dir)]


def _set_version_in_manifest(manifest_path: str, version: str):
    with open(manifest_path, "r") as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        if "{{ version }}" in line:
            new_lines.append(line.replace("{{ version }}", version))
        else:
            new_lines.append(line)

    with open(manifest_path, "w") as f:
        f.writelines(new_lines)


def _clear_directory(path_to_dir):
    for f in os.listdir(path_to_dir):
        file_path = os.path.join(path_to_dir, f)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            raise invoke.Exit(f"Failed to delete {file_path}: {e}")


def _get_version_from_toml(toml_file: str) -> str:
    with open(toml_file, "r") as f:
        pyproject_data = tomlkit.load(f)
    if not pyproject_data:
        raise invoke.Exit("Failed to load pyproject.toml.")

    version = pyproject_data.get("tool", {}).get("bumpversion", {}).get("current_version", None)
    if not version:
        raise invoke.Exit("Failed to get version from pyproject.toml. Please provide a version number.")
    return version


def _get_package_name(toml_file: str) -> str:
    with open(toml_file, "r") as f:
        pyproject_data = tomlkit.load(f)
    if not pyproject_data:
        raise invoke.Exit("Failed to load pyproject.toml.")

    name = pyproject_data.get("project", {}).get("name", None)
    if not name:
        raise invoke.Exit("Failed to get package name. Is your pyproject.toml missing a '[project]' section?")
    return name


def _sanitize_dependency(dep: str) -> str:
    # HACK: Remove upper bound constraints (e.g., ", <3" or ",<3") as Rhino currenly doesn't support them
    # https://discourse.mcneel.com/t/python-dependencies-with-ordered-comparison-syntax/212304
    sanitized = re.split(r"\s*,\s*[<>=]", dep)[0]
    sanitized = sanitized.split("#")[0].strip()  # Remove inline comments
    return sanitized


def _get_deps_from_requirements(req_filepath: str) -> str:
    with open(req_filepath, "r") as req_file:
        dependencies = []
        for line in req_file:
            line = line.strip()
            if line and not line.startswith("#"):
                dependencies.append(_sanitize_dependency(line))
        return dependencies


def _get_dependencies(base_folder: str) -> List[str]:
    toml_filepath = os.path.join(base_folder, "pyproject.toml")
    with open(toml_filepath, "r") as f:
        toml = tomlkit.load(f)

    dependencies = toml.get("project", {}).get("dependencies")
    if dependencies:
        return [_sanitize_dependency(dep) for dep in dependencies]

    dynamic_deps = toml.get("tool", {}).get("setuptools", {}).get("dynamic", {}).get("dependencies")
    if dynamic_deps and "file" in dynamic_deps:
        req_filepath = os.path.join(base_folder, dynamic_deps["file"])
        return _get_deps_from_requirements(req_filepath)

    return []


def _get_user_object_path(context):
    if hasattr(context, "ghuser_cpython"):
        print("checking ghuser_cpython")
        return os.path.join(context.base_folder, context.ghuser_cpython.target_dir)
    elif hasattr(context, "ghuser"):
        print("checking ghuser")
        return os.path.join(context.base_folder, context.ghuser.target_dir)
    else:
        return None


def _get_yak_setting(ctx, key: str) -> Optional[str]:
    """Return a path configured under the ``yak`` section of the project's tasks.py.

    Relative paths are resolved against ``base_folder``, matching the convention
    used for the ``ghuser`` config sections.
    """
    if not hasattr(ctx, "yak"):
        return None

    value = ctx.yak.get(key)
    if not value:
        return None

    return value if os.path.isabs(value) else os.path.join(ctx.base_folder, value)


def _resolve_yak_path(ctx, key: str, value: Optional[str], description: str) -> str:
    """Resolve a path from the task argument, falling back to the ``yak`` config section."""
    path = value or _get_yak_setting(ctx, key)
    if not path:
        raise invoke.Exit(
            f"Please provide the path to the {description}, either using `--{key.replace('_', '-')}` or by setting `yak.{key}` in the configuration of your tasks.py."
        )
    if not os.path.exists(path):
        raise invoke.Exit(f"{description.capitalize()} not found at {path}. Please provide a valid path.")
    return path


@invoke.task(
    help={
        "manifest_path": "(Optional) Path to the manifest file. Defaults to the `yak.manifest_path` setting.",
        "logo_path": "(Optional) Path to the logo file. Defaults to the `yak.logo_path` setting.",
        "gh_components_dir": "(Optional) Path to the directory containing the .ghuser files.",
        "readme_path": "(Optional) Path to the readme file.",
        "license_path": "(Optional) Path to the license file.",
        "version": "(Optional) The version number to set in the manifest file.",
        "target_rhino": "(Optional) The target Rhino version for the package. Defaults to 'rh8'.",
    }
)
def yakerize(
    ctx,
    manifest_path: str = None,
    logo_path: str = None,
    gh_components_dir: str = None,
    readme_path: str = None,
    license_path: str = None,
    version: str = None,
    target_rhino: str = "rh8",
) -> bool:
    """Create a Grasshopper YAK package from the current project."""
    # https://developer.rhino3d.com/guides/yak/the-anatomy-of-a-package/
    if target_rhino.split("_")[0] not in ["rh6", "rh7", "rh8"]:
        raise invoke.Exit(
            f"""Invalid target Rhino version `{target_rhino}`. Must be one of: rh6, rh7, rh8. 
            Minor version is optional and can be appended with a '_' (e.g. rh8_15)."""
        )
    manifest_path = _resolve_yak_path(ctx, "manifest_path", manifest_path, "manifest file")
    logo_path = _resolve_yak_path(ctx, "logo_path", logo_path, "logo file")

    gh_components_dir = gh_components_dir or _get_user_object_path(ctx)
    if not gh_components_dir:
        raise invoke.Exit("Please provide the path to the directory containing the .ghuser files.")

    readme_path = readme_path or os.path.join(ctx.base_folder, "README.md")
    if not os.path.exists(readme_path):
        raise invoke.Exit(f"Readme file not found at {readme_path}. Please provide a valid path.")

    license_path = license_path or os.path.join(ctx.base_folder, "LICENSE")
    if not os.path.exists(license_path):
        raise invoke.Exit(f"License file not found at {license_path}. Please provide a valid path.")

    version = version or _get_version_from_toml(os.path.join(ctx.base_folder, "pyproject.toml"))
    target_dir = os.path.join(ctx.base_folder, "dist", "yak_package")

    #####################################################################
    # Copy manifest, logo, misc folder (readme, license, etc)
    #####################################################################
    # if target dit exists, make sure it's empty
    if os.path.exists(target_dir) and os.path.isdir(target_dir):
        _clear_directory(target_dir)
    else:
        os.makedirs(target_dir, exist_ok=False)

    # yak only recognizes a manifest named `manifest.yml`, regardless of the source filename
    manifest_target = shutil.copy(manifest_path, os.path.join(target_dir, "manifest.yml"))
    _set_version_in_manifest(manifest_target, version)
    shutil.copy(logo_path, target_dir)

    path_miscdir: str = os.path.join(target_dir, "misc")
    os.makedirs(path_miscdir, exist_ok=False)
    shutil.copy(readme_path, path_miscdir)
    shutil.copy(license_path, path_miscdir)

    for f in os.listdir(gh_components_dir):
        if f.endswith(".ghuser"):
            shutil.copy(os.path.join(gh_components_dir, f), target_dir)

    #####################################################################
    # Yak exe
    #####################################################################

    # yak executable shouldn't be in the target directory, otherwise it will be included in the package
    target_parent = os.sep.join(target_dir.split(os.sep)[:-1])
    try:
        yak_cmd = _get_yak_command(target_parent)
    except ValueError:
        raise invoke.Exit("Failed to download the yak executable")

    with chdir(target_dir):
        try:
            # not using `ctx.run()` here to get properly formatted output (unicode+colors)
            subprocess.run(yak_cmd + ["build", "--platform", "any"], check=True)
        except (OSError, subprocess.CalledProcessError) as e:
            raise invoke.Exit(f"Failed to build the yak package: {e}")
        if not any([f.endswith(".yak") for f in os.listdir(target_dir)]):
            raise invoke.Exit("No .yak file was created in the build directory.")

        # filename is what tells YAK the target Rhino version..?
        taget_file = next((f for f in os.listdir(target_dir) if f.endswith(".yak")))
        new_filename = taget_file.replace("any-any", f"{target_rhino}-any")
        os.rename(taget_file, new_filename)


@invoke.task(help={"yak_file": "Path to the .yak file to publish.", "test_server": "True to publish to the test server."})
def publish_yak(ctx, yak_file: str, test_server: bool = False):
    """Publish a YAK package to the YAK server."""

    if not os.path.exists(yak_file) or not os.path.isfile(yak_file):
        raise invoke.Exit(f"Yak file not found at {yak_file}. Please provide a valid path.")
    if not yak_file.endswith(".yak"):
        raise invoke.Exit("Invalid file type. Must be a .yak file.")

    yak_file = os.path.abspath(yak_file)

    with chdir(ctx.base_folder):
        with tempfile.TemporaryDirectory("actions.publish_yak") as action_dir:
            try:
                yak_cmd = _get_yak_command(action_dir)
            except ValueError:
                raise invoke.Exit("Failed to download the yak executable")

            cmd = yak_cmd + ["push"]
            if test_server:
                cmd += ["--source", "https://test.yak.rhino3d.com"]
            cmd.append(yak_file)

            try:
                subprocess.run(cmd, check=True)
            except (OSError, subprocess.CalledProcessError) as e:
                raise invoke.Exit(f"Failed to publish the yak package: {e}")


def _is_header_line(line: str) -> bool:
    return re.match(r"^#\s+(r|venv|env):", line) is not None


@invoke.task(
    help={
        "version": "New minimum version to set in the header. If not provided, current version is used.",
        "venv": "(Optional) Name of the Rhino virtual environment to use in the components.",
        "dev": "(Defaults to False) If True, the dependency header is ommitted and path to repo is added instead.",
        "envs": "(Optional) List of environments, delimited with `;` which will be added to path using `# env:`.",
    }
)
def update_gh_header(ctx, version: str = None, venv: str = None, dev: bool = False, envs: str = None):
    """Update the minimum version header of all CPython Grasshopper components."""
    toml_filepath = os.path.join(ctx.base_folder, "pyproject.toml")

    new_header = []
    if not dev:
        version = version or _get_version_from_toml(toml_filepath)
        package_name = _get_package_name(toml_filepath)
        new_header.append(f"# r: {package_name}>={version}\n")
    if venv:
        new_header.append(f"# venv: {venv}\n")
    if envs:
        for env in envs.split(";"):
            new_header.append(f"# env: {env.strip()}\n")
    if dev:
        new_header.append(f"# env: {os.path.join(ctx.base_folder, 'src')}\n")
        dependencies = _get_dependencies(ctx.base_folder)
        if dependencies:
            new_header.append(f"# r: {', '.join(dependencies)}\n")

    for file in Path(ctx.ghuser_cpython.source_dir).glob("**/code.py"):
        try:
            with open(file, "r", encoding="utf-8") as f:
                original_content = f.readlines()

            with open(file, "w", encoding="utf-8") as f:
                for line in new_header:
                    f.write(line)
                for line in original_content:
                    if not _is_header_line(line):
                        f.write(line)
            print(f"✅ Updated: {file}")
        except Exception as e:
            print(f"❌ Failed to update {file}: {e}")
