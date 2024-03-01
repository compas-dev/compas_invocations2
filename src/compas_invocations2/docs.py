import invoke

from compas_invocations2.build import clean
from compas_invocations2.console import chdir


@invoke.task(default=True)
def help(ctx):
    """Lists available tasks and usage."""
    ctx.run("invoke --list")
    print('Use "invoke -h <taskname>" to get detailed help for a task.')


@invoke.task(
    help={
        "rebuild": "True to clean all previously built docs before starting, otherwise False.",
        "doctest": "True to run doctests, otherwise False.",
        "check_links": "True to check all web links in docs for validity, otherwise False.",
    }
)
def docs(ctx, doctest=False, rebuild=False, check_links=False):
    """Builds the HTML documentation."""

    if rebuild:
        clean(ctx)

    with chdir(ctx.base_folder):
        if doctest:
            ctx.run("pytest --doctest-modules")

        opts = "-E" if rebuild else ""
        ctx.run("sphinx-build {} -b html docs dist/docs".format(opts))

        if check_links:
            linkcheck(ctx, rebuild=rebuild)


@invoke.task()
def linkcheck(ctx, rebuild=False):
    """Check links in documentation."""
    print("Running link check...")
    opts = "-E" if rebuild else ""
    ctx.run("sphinx-build {} -b linkcheck docs dist/docs".format(opts))
