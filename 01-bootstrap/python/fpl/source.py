"""
# Source

The pipe does not start on FON. This is the ingress.
"""

import sys

from fpl.pipe import cli


def main() -> None:
    sys.exit(cli("source"))


if __name__ == "__main__":
    main()
