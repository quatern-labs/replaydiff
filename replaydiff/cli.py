"""`replaydiff` console script."""
import sys

USAGE = "usage: replaydiff compare --base <mcap>... --head <mcap> --tolerances <file.yaml> [--json [FILE]]\n       replaydiff init --recording <mcap> [--base <mcap>...] [--out replaydiff.yaml]"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] == "compare":
        from .compare import main as compare_main
        return compare_main(argv[1:])
    if argv and argv[0] == "init":
        from .init import main as init_main
        return init_main(argv[1:])
    print(USAGE, file=sys.stderr)
    return 0 if argv and argv[0] in ("-h", "--help") else 2


if __name__ == "__main__":
    sys.exit(main())
