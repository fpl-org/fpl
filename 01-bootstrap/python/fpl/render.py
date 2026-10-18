"""
# Render

The pipe ends in text a person can read.
"""

import sys

from fpl.pipe import cli


def main() -> None:
    sys.exit(cli("render"))


if __name__ == "__main__":
    main()
