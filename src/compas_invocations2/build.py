import glob
import os
import platform
import shutil
import subprocess
import sys
import tempfile

import invoke

from compas_invocations2.console import chdir
from compas_invocations2.console import confirm


@invoke.task(
    help={
        "docs": "True to clean up generated documentation, otherwise False",
        "bytecode": "True to clean up compiled python files, otherwise False.",
        "builds": "True to clean up build/packaging artifacts, otherwise False.",
    }
)
def clean(ctx, docs=True, bytecode=True, builds=True, ghuser=True):
    """Cleans the local copy from compiled artifacts."""

    with chdir(ctx.base_folder):
        if bytecode:
            for root, dirs, files in os.walk(ctx.base_folder):
                for f in files:
                    if f.endswith(".pyc"):
                        os.remove(os.path.join(root, f))
                if ".git" in dirs:
                    dirs.remove(".git")

        folders = []

        if docs:
            folders.append("docs/api/generated")

        folders.append("dist/")

        if bytecode:
            for t in ("src", "tests"):
                folders.extend(glob.glob("{}/**/__pycache__".format(t), recursive=True))

        if builds:
            folders.append("build/")
            folders.extend(glob.glob("src/**/*.egg-info", recursive=False))

        if ghuser and ctx.get("ghuser"):
            folders.append(os.path.abspath(ctx.ghuser.target_dir))

        for folder in folders:
            shutil.rmtree(os.path.join(ctx.base_folder, folder), ignore_errors=True)


@invoke.task(
    help={"release_type": "Type of release follows semver rules. Must be one of: major, minor, patch, pre_l, pre_n."}
)
def release(ctx, release_type):
    """Releases the project in one swift command!"""
    if release_type not in ("patch", "minor", "major", "pre_l", "pre_n"):
        raise invoke.Exit("The release type parameter is invalid.\nMust be one of: major, minor, patch.")

    # Run formatter
    ctx.run("invoke format")

    # Run checks
    ctx.run("invoke test")

    # Bump version and git tag it
    ctx.run("bump-my-version bump %s --verbose" % release_type)

    # Build project
    ctx.run("python -m build")

    # Prepare the change log for the next release
    prepare_changelog(ctx)

    # Clean up local artifacts
    clean(ctx)

    # Upload to pypi
    if confirm(
        "Everything is ready. You are about to push to git which will trigger a release to pypi.org. Are you sure?",
        assume_yes=False,
    ):
        ctx.run("git push --tags && git push")
    else:
        raise invoke.Exit("You need to manually revert the tag/commits created.")


@invoke.task
def prepare_changelog(ctx):
    """Prepare changelog for next release."""
    UNRELEASED_CHANGELOG_TEMPLATE = "## Unreleased\n\n### Added\n\n### Changed\n\n### Removed\n\n## "

    with chdir(ctx.base_folder):
        # Preparing changelog for next release
        with open("CHANGELOG.md", "r+") as changelog:
            content = changelog.read()
            changelog.seek(0)
            changelog.write(content.replace("## ", UNRELEASED_CHANGELOG_TEMPLATE, 1))

        ctx.run('git add CHANGELOG.md && git commit -m "Prepare changelog for next release"')


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

            cmd = [sys.executable, componentizer_script, source_dir, target_dir, "--ghio", gh_io_folder]
            if prefix:
                cmd += ["--prefix", prefix]

            # The componentizer loads GH_IO.dll through pythonnet. On macOS that means Mono,
            # which needs the native libgdiplus to embed component icons. The embedded Mono
            # does not search the Homebrew prefix the way the `mono` CLI does, so we point it
            # there via DYLD_LIBRARY_PATH. We also run the interpreter directly instead of
            # through `ctx.run` (which spawns a shell): macOS SIP strips DYLD_* across the
            # protected /bin/sh, so otherwise the variable never reaches the subprocess.
            subprocess.run(cmd, env=_componentizer_env(), check=True)


def _componentizer_env():
    """Return the environment for the componentizer subprocess.

    On macOS this forces the Mono runtime (pythonnet may otherwise default to a
    .NET Core runtime that cannot load the net48 ``GH_IO.dll`` / ``System.Drawing``)
    and adds the Homebrew library directories to ``DYLD_LIBRARY_PATH`` so Mono can
    find ``libgdiplus``. On other platforms the current environment is returned
    unchanged.
    """
    env = dict(os.environ)
    if platform.system() != "Darwin":
        return env

    env.setdefault("PYTHONNET_RUNTIME", "mono")

    lib_dirs = ["/opt/homebrew/lib", "/usr/local/lib"]
    try:
        brew_prefix = subprocess.check_output(["brew", "--prefix"], text=True).strip()
        lib_dirs.insert(0, os.path.join(brew_prefix, "lib"))
    except (OSError, subprocess.CalledProcessError):
        pass
    if env.get("DYLD_LIBRARY_PATH"):
        lib_dirs.append(env["DYLD_LIBRARY_PATH"])
    env["DYLD_LIBRARY_PATH"] = os.pathsep.join(dict.fromkeys(d for d in lib_dirs if d))
    return env


@invoke.task
def pre_build(ctx):
    """Pre-build steps before building components.

    This is a placeholder for any pre-build steps that might be needed and are to be added but the actual project.

    """
    pass
