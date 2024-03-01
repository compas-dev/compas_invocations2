import invoke

from compas_invocations2.console import chdir


@invoke.task()
def lint(ctx):
    """Check the consistency of coding style."""
    print("Running flake8 python linter...")
    folders = ctx.get("lint_folders") or ["src", "tests"]
    ctx.run("flake8 {}".format(" ".join(folders)))

    print("Running black python linter...")
    folders = ctx.get("format_folders") or ["src", "tests"]
    ctx.run("black --check --diff --color {}".format(" ".join(folders)))


@invoke.task()
def format(ctx):
    """Reformat the code base using black."""
    print("Running black python formatter...")
    folders = ctx.get("format_folders") or ["src", "tests"]
    ctx.run("black {}".format(" ".join(folders)))


@invoke.task()
def check(ctx):
    """Check the consistency of documentation, coding style and a few other things."""

    with chdir(ctx.base_folder):
        lint(ctx)

        print("Checking MANIFEST.in...")
        ctx.run("check-manifest")

        print("Checking metadata...")
        ctx.run("python setup.py check --strict --metadata")
