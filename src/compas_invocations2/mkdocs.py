import json

import invoke
import semver

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


@invoke.task(
    help={
        "push": "True to push changes to the remote after pruning, otherwise False.",
        "dry": "True to print which versions would be deleted without actually deleting them.",
    }
)
def prune_docs(ctx, push=True, dry=False):
    """Prunes deployed doc versions, keeping only the latest patch per minor version.

    Fetches the list of deployed versions via mike, groups them by major.minor,
    and deletes any patch version that is not the highest in its group.

    """
    result = ctx.run("mike list --json", hide=True)
    entries = json.loads(result.stdout)

    # latest[(major, minor)] = semver.Version — overwritten whenever a higher patch is seen
    latest = {}
    all_semver = []
    for entry in entries:
        ver_str = entry["version"]
        try:
            v = semver.Version.parse(ver_str)
        except ValueError:
            continue
        all_semver.append(ver_str)
        key = (v.major, v.minor)
        if key not in latest or v.compare(latest[key]) > 0:
            latest[key] = v

    to_keep = [str(v) for v in latest.values()]
    to_delete = [v for v in all_semver if v not in to_keep]

    if dry:
        print("Keep:   {}".format(", ".join(sorted(to_keep)) or "(none)"))
        print("Delete: {}".format(", ".join(sorted(to_delete)) or "(none)"))
        return

    if not to_delete:
        print("No old patch versions to prune.")
        return

    push_flag = "-p" if push else ""
    ctx.run(f"mike delete {push_flag} {' '.join(to_delete)}".strip())
    print(f"Deleted: {', '.join(to_delete)}")
