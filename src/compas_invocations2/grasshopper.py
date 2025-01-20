"""
Adapted from: https://github.com/diffCheckOrg/diffCheck/blob/main/invokes/yakerize.py

Yakerize.py was originally developed as part of the DiffCheck plugin by
Andrea Settimi, Damien Gilliard, Eleni Skevaki, Marirena Kladeftira (IBOIS, CRCL, EPFL) in 2024.
It is distributed under the MIT License, provided this attribution is retained.
"""

import os
import shutil
import tempfile

import invoke
import requests
import toml

from compas_invocations2.console import chdir

YAK_URL = r"https://files.mcneel.com/yak/tools/latest/yak.exe"


def _download_yak_executable(target_dir: str):
    response = requests.get(YAK_URL)
    if response.status_code != 200:
        raise ValueError(f"Failed to download the yak.exe from url:{YAK_URL} with error : {response.status_code}")

    with open(os.path.join(target_dir, "yak.exe"), "wb") as f:
        f.write(response.content)


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
            invoke.Exit(f"Failed to delete {file_path}: {e}")


def _get_version_from_toml(toml_file: str) -> str:
    pyproject_data = toml.load(toml_file)
    version = pyproject_data.get("tool", {}).get("bumpversion", {}).get("current_version", None)
    if not version:
        invoke.Exit("Failed to get version from pyproject.toml. Please provide a version number.")
    return version


def _get_user_object_path(context):
    if hasattr(context, "ghuser_cpython"):
        print("checking ghuser_cpython")
        return os.path.join(context.base_folder, context.ghuser_cpython.target_dir)
    elif hasattr(context, "ghuser"):
        print("checking ghuser")
        return os.path.join(context.base_folder, context.ghuser.target_dir)
    else:
        return None


@invoke.task(
    help={
        "manifest_path": "Path to the manifest file.",
        "logo_path": "Path to the logo file.",
        "gh_components_dir": "(Optional) Path to the directory containing the .ghuser files.",
        "readme_path": "(Optional) Path to the readme file.",
        "license_path": "(Optional) Path to the license file.",
        "version": "(Optional) The version number to set in the manifest file.",
        "target_rhino": "(Optional) The target Rhino version for the package. Defaults to 'rh8'.",
    }
)
def yakerize(
    ctx,
    manifest_path: str,
    logo_path: str,
    gh_components_dir: str = None,
    readme_path: str = None,
    license_path: str = None,
    version: str = None,
    target_rhino: str = "rh8",
) -> bool:
    """Create a Grasshopper YAK package from the current project."""
    if target_rhino not in ["rh6", "rh7", "rh8"]:
        invoke.Exit("Invalid target Rhino version. Must be one of: rh6, rh7, rh8")

    gh_components_dir = gh_components_dir or _get_user_object_path(ctx)
    if not gh_components_dir:
        invoke.Exit("Please provide the path to the directory containing the .ghuser files.")

    readme_path = readme_path or os.path.join(ctx.base_folder, "README.md")
    if not os.path.exists(readme_path):
        invoke.Exit(f"Readme file not found at {readme_path}. Please provide a valid path.")

    license_path = license_path or os.path.join(ctx.base_folder, "LICENSE")
    if not os.path.exists(license_path):
        invoke.Exit(f"License file not found at {license_path}. Please provide a valid path.")

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

    manifest_target = shutil.copy(manifest_path, target_dir)
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

    try:
        _download_yak_executable(target_dir)
    except ValueError:
        invoke.Exit("Failed to download the yak executable")

    yak_exe_path: str = os.path.join(target_dir, "yak.exe")
    yak_exe_path = os.path.abspath(yak_exe_path)

    with chdir(target_dir):
        try:
            # not using `ctx.run()` here to get properly formatted output (unicode+colors)
            os.system(f"{yak_exe_path} build --platform any")
        except Exception as e:
            invoke.Exit(f"Failed to build the yak package: {e}")
        if not any([f.endswith(".yak") for f in os.listdir(target_dir)]):
            invoke.Exit("No .yak file was created in the build directory.")

        # filename is what tells YAK the target Rhino version..?
        taget_file = next((f for f in os.listdir(target_dir) if f.endswith(".yak")))
        new_filename = taget_file.replace("any-any", f"{target_rhino}-any")
        os.rename(taget_file, new_filename)


@invoke.task(
    help={
        "gh_io_folder": "Folder where GH_IO.dll is located. If not specified, it will try to download from NuGet.",
        "ironpython": "Command for running the IronPython executable. Defaults to `ipy`.",
        "prefix": "(Optional) Append this prefix to the names of the built components.",
    }
)
def build_ghuser_components(ctx, gh_io_folder=None, ironpython=None, prefix=None):
    """Builds Grasshopper components using GH Componentizer."""
    prefix = prefix or getattr(ctx.ghuser, "prefix", None)
    source_dir = os.path.abspath(ctx.ghuser.source_dir)
    target_dir = os.path.abspath(ctx.ghuser.target_dir)
    repo_url = "https://github.com/compas-dev/compas-actions.ghpython_components.git"

    with chdir(ctx.base_folder):
        shutil.rmtree(os.path.join(ctx.base_folder, target_dir), ignore_errors=True)

    # Build IronPython Grasshopper user objects from source
    with chdir(ctx.base_folder):
        with tempfile.TemporaryDirectory("actions.ghcomponentizer") as action_dir:
            ctx.run("git clone {} {}".format(repo_url, action_dir))

            if not gh_io_folder:
                gh_io_folder = tempfile.mkdtemp("ghio")
                import compas_ghpython

                compas_ghpython.fetch_ghio_lib(gh_io_folder)

            if not ironpython:
                ironpython = ctx.get("ironpython") or "ipy"

            gh_io_folder = os.path.abspath(gh_io_folder)
            componentizer_script = os.path.join(action_dir, "componentize_ipy.py")

            cmd = "{} {} {} {}".format(ironpython, componentizer_script, source_dir, target_dir)
            cmd += ' --ghio "{}"'.format(gh_io_folder)
            if prefix:
                cmd += ' --prefix "{}"'.format(prefix)

            ctx.run(cmd)


@invoke.task(
    help={
        "gh_io_folder": "Folder where GH_IO.dll is located. If not specified, it will try to download from NuGet.",
        "prefix": "(Optional) Append this prefix to the names of the built components.",
    }
)
def build_cpython_ghuser_components(ctx, gh_io_folder=None, prefix=None):
    """Builds CPython Grasshopper components using GH Componentizer."""
    prefix = prefix or getattr(ctx.ghuser_cpython, "prefix", None)
    source_dir = os.path.abspath(ctx.ghuser_cpython.source_dir)
    target_dir = os.path.abspath(ctx.ghuser_cpython.target_dir)
    repo_url = "https://github.com/compas-dev/compas-actions.ghpython_components.git"

    with chdir(ctx.base_folder):
        shutil.rmtree(os.path.join(ctx.base_folder, target_dir), ignore_errors=True)

    # Build CPython Grasshopper user objects from source
    with chdir(ctx.base_folder):
        with tempfile.TemporaryDirectory("actions.ghcomponentizer") as action_dir:
            ctx.run("git clone {} {}".format(repo_url, action_dir))

            if not gh_io_folder:
                gh_io_folder = tempfile.mkdtemp("ghio")
                import compas_ghpython

                compas_ghpython.fetch_ghio_lib(gh_io_folder)

            gh_io_folder = os.path.abspath(gh_io_folder)
            componentizer_script = os.path.join(action_dir, "componentize_cpy.py")

            cmd = "{} {} {} {}".format("python", componentizer_script, source_dir, target_dir)
            cmd += ' --ghio "{}"'.format(gh_io_folder)
            if prefix:
                cmd += ' --prefix "{}"'.format(prefix)

            ctx.run(cmd)
