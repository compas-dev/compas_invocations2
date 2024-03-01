import invoke

from compas_invocations2.console import chdir


@invoke.task()
def test(ctx, doctest=False):
    """Run all tests."""
    with chdir(ctx.base_folder):
        if doctest:
            ctx.run("pytest --doctest-modules")
        else:
            ctx.run("pytest")


@invoke.task()
def testdocs(ctx):
    """Test the examples in the docstrings."""
    print("Running doctest...")
    ctx.run("pytest --doctest-modules")


@invoke.task()
def testcodeblocks(ctx):
    """Test the examples in the code blocks of the docs."""
    print("Running tests on doc code blocks...")
    ctx.run("pytest docs")
