import invoke

from compas_invocations2.console import chdir


@invoke.task(
    help={
        "clean": "True to clean the site directory before building, otherwise False.",
        "verbose": "True to nicely format the output, otherwise False.",
    }
)
def docs(ctx, clean=False, verbose=False):
    """Builds the HTML documentation based on mkdocs."""
    clean_flag = "--clean" if clean else ""
    verbose_flag = "--verbose" if verbose else ""

    with chdir(ctx.base_folder):
        ctx.run("mkdocs build {} {} -d dist/docs".format(clean_flag, verbose_flag))
