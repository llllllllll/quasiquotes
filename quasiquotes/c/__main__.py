import argparse

from . import c


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--path',
        default='.',
        help='The path to run c.cleanup on',
    )
    parser.add_argument(
        '--no-recurse',
        action='store_false',
        dest='recurse',
        default=True,
        help='Should cleanup recurse down from PATH?',
    )
    for removed in c.cleanup(**vars(parser.parse_args())):
        print(removed)


main()
