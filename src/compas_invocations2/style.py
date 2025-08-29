import invoke

from compas_invocations2.console import chdir


@invoke.task()
def lint(ctx):
    """Check the consistency of coding style."""

    print("\nRunning ruff linter...")
    ctx.run("ruff check --fix src tests")

    print("\nAll linting is done!")


@invoke.task()
def format(ctx):
    """Reformat the code base using black."""

    print("\nRunning ruff formatter...")
    ctx.run("ruff format src tests")

    print("\nAll formatting is done!")


@invoke.task()
def check(ctx):
    """Check the consistency of documentation, coding style and a few other things."""

    with chdir(ctx.base_folder):
        lint(ctx)
