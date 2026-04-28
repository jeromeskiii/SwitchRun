"""Module entrypoint for `python -m switchboard`."""

from switchboard.router import main


if __name__ == "__main__":
    raise SystemExit(main())