import os
import shutil

import invoke
import requests

YAK_URL = r"https://files.mcneel.com/yak/tools/latest/yak.exe"
FILENAME = "yak.exe"


def _download_yak_executable(target_dir: str):
    response = requests.get(YAK_URL)
    if response.status_code != 200:
        raise ValueError(f"Failed to download the yak.exe from url:{YAK_URL} with error : {response.status_code}")

    with open(os.path.join(target_dir, FILENAME), "wb") as f:
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
    print(f"target dir: {path_to_dir} exists, clearing it.")
    for f in os.listdir(path_to_dir):
        file_path = os.path.join(path_to_dir, f)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            invoke.Exit(f"Failed to delete {file_path}: {e}")


@invoke.task(
    help={
        "gh_components_dir": "Path to the directory containing the .ghuser files.",
        "target_dir": "Path to the directory where the yak package will be created.",
        "manifest_path": "Path to the manifest file.",
        "logo_path": "Path to the logo file.",
        "readme_path": "Path to the readme file.",
        "license_path": "Path to the license file.",
        "version": "The version number to set in the manifest file.",
    }
)
def yakerize(
    ctx,
    gh_components_dir: str,
    target_dir: str,
    manifest_path: str,
    logo_path: str,
    readme_path: str,
    license_path: str,
    version: str,
) -> bool:
    # copy the manifest, logo, readme, license and ghuser files to the target dir
    # update the manifest file with the version number
    # download the yak executable
    # build the yak package

    target_dir = os.path.abspath(target_dir)

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
        invoke.Exit("Failed to download the yak executable: {e}")

    yak_exe_path: str = os.path.join(target_dir, "yak.exe")
    yak_exe_path = os.path.abspath(yak_exe_path)

    path_current: str = os.getcwd()
    os.chdir(target_dir)
    os.system("cd")
    try:
        os.system(f"{yak_exe_path} build --platform win")
    except Exception:
        invoke.Exit(f"Failed to build the yak package: {e}")
    if not any([f.endswith(".yak") for f in os.listdir(target_dir)]):
        invoke.Exit("No .yak file was created in the build directory.")
    os.chdir(path_current)
