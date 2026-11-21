"""The `vk` command: every step of the voice pipeline. Run `vk <command> --help` for details."""
import argparse
import os
import re
import sys

from . import check, config, dataset, export, fix, kaggle, listen, merge, record, watch

OUTPUTS = {"check": ["voices_checked.zip"], "new-lines": ["voices_checked.zip"], "fix": ["fix.zip"]}
RANGE = re.compile(r"^(\d+)-(\d+)$")
NOT_FINISHED = {
    "RUNNING": "download it when it is COMPLETE (try again in a few minutes)",
    "NONE": "it was never started",
    "ERROR": "it failed; open it on kaggle.com to see the log",
}


def line_range(text):
    found = RANGE.match(text)
    if not found:
        raise argparse.ArgumentTypeError(f"'{text}' is not FIRST-LAST, e.g. 12-15")
    return int(found.group(1)), int(found.group(2))


def cmd_dataset(cfg, args):
    dataset.write(cfg)
    if args.upload:
        dataset.upload(cfg, args.message)
    else:
        print("upload it with: vk dataset --upload")


def cmd_record(cfg, args):
    dataset.check_uploaded(cfg)
    record.build(cfg)
    check.build(cfg)
    watch.forget(cfg)
    print("start them with: vk watch   (or one at a time: vk push part1)")


def cmd_watch(cfg, args):
    watch.watch(cfg, args.parts, start_check=not args.no_check, resume=args.resume)


def cmd_status(cfg, args):
    """One line: what Kaggle says about each notebook of this project (asks once, no waiting)."""
    names = record.part_names(cfg) + ["check"]
    names += [n for n in ("fix", "new-lines") if os.path.isdir(os.path.join(cfg.build, "kaggle", n))]
    print("  ".join(f"{n}={kaggle.kernel_status(cfg.ref(cfg.kernel_slug(n)))}" for n in names))


def cmd_push(cfg, args):
    folder = os.path.join(cfg.build, "kaggle", args.notebook)
    if not os.path.isfile(os.path.join(folder, "kernel-metadata.json")):
        sys.exit(f"{folder} has no notebook: build it first (vk record, vk fix or vk new-lines)")
    if not kaggle.push(folder):
        sys.exit("both Kaggle GPU slots are busy: try again when a notebook finishes (or use vk watch)")


def cmd_fetch(cfg, args):
    files = args.files or OUTPUTS.get(args.notebook, ["voices.zip"])
    slug = cfg.kernel_slug(args.notebook)
    out_dir = args.out or os.path.join(cfg.build, "out", args.notebook)
    status = kaggle.kernel_status(cfg.ref(slug))
    if status != "COMPLETE":
        sys.exit(f"{slug} is {status} on Kaggle, not finished: {NOT_FINISHED.get(status, NOT_FINISHED['RUNNING'])}")
    os.makedirs(out_dir, exist_ok=True)
    found = kaggle.find_output_files(cfg.username, slug, set(files))
    missing = sorted(set(files) - found.keys())
    if missing:
        sys.exit(f"{slug}'s output has no {missing}: has it finished? (kaggle kernels status {cfg.ref(slug)})")
    for name, url in found.items():
        kaggle.download(url, os.path.join(out_dir, name))


def cmd_listen(cfg, args):
    name = os.path.splitext(os.path.basename(args.zip))[0]
    listen.build(cfg, args.zip, args.out or os.path.join(cfg.build, "listen", name), args.compare, args.all)


def cmd_fix(cfg, args):
    fix.build(cfg, args.spellings)
    print("start it with: vk push fix")


def cmd_use_take(cfg, args):
    fix.use_takes(cfg, args.fix_zip, args.base_zip, args.out_zip, args.takes)


def cmd_new_lines(cfg, args):
    check.build(cfg, check.check_line_numbers(cfg, *args.lines))
    print("upload the new sentences first (vk dataset --upload), then start it with: vk push new-lines")


def cmd_merge(cfg, args):
    merge.merge(args.base_zip, args.new_zip, *args.lines, args.out_zip)


def cmd_export(cfg, args):
    export.export(cfg, args.zip, args.out or os.path.join(cfg.build, "app_audio"))


def parser():
    p = argparse.ArgumentParser(prog="vk", description="Clone voices and record lines on Kaggle's free GPUs.")
    p.add_argument("-c", "--config", default="voices.yaml", help="the project file (default: ./voices.yaml)")
    sub = p.add_subparsers(dest="command", required=True, metavar="command")

    s = sub.add_parser("dataset", help="1. build the dataset (sentences, clips) and upload it")
    s.add_argument("--upload", action="store_true", help="create or update the private Kaggle dataset")
    s.add_argument("-m", "--message", default="update", help="version note for an update")
    s.set_defaults(run=cmd_dataset)

    s = sub.add_parser("record", help="2. build the recording notebooks (and the check notebook)")
    s.set_defaults(run=cmd_record)

    s = sub.add_parser("watch", help="2. push the parts as GPU slots free up, then the check")
    which = s.add_mutually_exclusive_group()
    which.add_argument("--parts", nargs="+", metavar="partN", help="only these parts (default: all)")
    which.add_argument("--resume", action="store_true",
                       help="follow the run already started: push only what was not pushed yet")
    s.add_argument("--no-check", action="store_true", help="don't start the check at the end")
    s.set_defaults(run=cmd_watch)

    s = sub.add_parser("push", help="3. start one built notebook on Kaggle (part1, check, fix, new-lines)")
    s.add_argument("notebook")
    s.set_defaults(run=cmd_push)

    s = sub.add_parser("status", help="3. what Kaggle says about each notebook now (NONE: never started)")
    s.set_defaults(run=cmd_status)

    s = sub.add_parser("fetch", help="4. download a notebook's output (only the files you need)")
    s.add_argument("notebook", help="part1, check, fix or new-lines")
    s.add_argument("files", nargs="*", help="output file names (default: the notebook's zip)")
    s.add_argument("--out", help="folder (default: build/out/<notebook>)")
    s.set_defaults(run=cmd_fetch)

    s = sub.add_parser("listen", help="5. web page of flagged lines (checked zip) or of takes (fix zip)")
    s.add_argument("zip")
    s.add_argument("--compare", help="another voices zip to show alongside (for a fix zip: the current clips)")
    s.add_argument("--all", action="store_true", help="every line, not only the flagged ones")
    s.add_argument("--out", help="folder (default: build/listen/<zip name>)")
    s.set_defaults(run=cmd_listen)

    s = sub.add_parser("fix", help="6. build a notebook that re-records clips with spelling variants")
    s.add_argument("spellings", help="YAML file with the lines, speakers and spellings to try")
    s.set_defaults(run=cmd_fix)

    s = sub.add_parser("use-take", help="6. swap picked takes from fix.zip into a voices zip")
    s.add_argument("fix_zip")
    s.add_argument("base_zip")
    s.add_argument("out_zip")
    s.add_argument("takes", nargs="+", help="take names from the listening page, e.g. narrator_003_b2")
    s.set_defaults(run=cmd_use_take)

    s = sub.add_parser("new-lines", help="7. build a notebook that records and checks lines FIRST-LAST")
    s.add_argument("lines", type=line_range, metavar="FIRST-LAST")
    s.set_defaults(run=cmd_new_lines)

    s = sub.add_parser("merge", help="7. add the new lines to the voices zip without renumbering")
    s.add_argument("base_zip")
    s.add_argument("new_zip")
    s.add_argument("lines", type=line_range, metavar="FIRST-LAST")
    s.add_argument("out_zip")
    s.set_defaults(run=cmd_merge)

    s = sub.add_parser("export", help="8. convert a voices zip to small Opus files for an app")
    s.add_argument("zip")
    s.add_argument("--out", help="folder (default: build/app_audio)")
    s.set_defaults(run=cmd_export)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        cfg = config.load(args.config)
        args.run(cfg, args)
    except (config.ConfigError, kaggle.KaggleError, ValueError, OSError) as e:
        sys.exit(f"error: {e}")
    except KeyboardInterrupt:
        sys.exit("stopped (notebooks already started keep running on Kaggle)")


if __name__ == "__main__":
    main()
