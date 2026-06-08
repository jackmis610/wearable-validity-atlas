"""CLI entry point.

    python -m wearvalid build [--data DIR] [--out DIR]
"""
import argparse
import os
import sys

from .build import GRADE_LABEL, GRADE_ORDER, build

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(argv=None):
    p = argparse.ArgumentParser(prog="wearvalid")
    sub = p.add_subparsers(dest="cmd")
    b = sub.add_parser("build", help="grade the corpus and write outputs")
    b.add_argument("--data", default=os.path.join(_ROOT, "data"))
    b.add_argument("--out", default=os.path.join(_ROOT, "build"))
    args = p.parse_args(argv)

    if args.cmd != "build":
        p.print_help()
        return 1

    verdicts, counts = build(args.data, args.out)
    print("Graded %d device x claim cells -> %s" % (len(verdicts), args.out))
    for g in GRADE_ORDER:
        print("  %s  %2d  %s" % (g, counts[g], GRADE_LABEL[g]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
