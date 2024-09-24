"""CLI for managing cellophane projects"""

import rich_click as click

from .dev import main

if __name__ == "__main__":
    click.rich_click.DEFAULT_STRING = "[{}]"
    main()  # pylint: disable=no-value-for-parameter
