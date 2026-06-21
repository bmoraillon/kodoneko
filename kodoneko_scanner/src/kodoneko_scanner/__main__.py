"""Permet l'invocation `python -m kodoneko_scanner`."""
from .cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
