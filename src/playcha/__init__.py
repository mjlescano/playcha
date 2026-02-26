from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("playcha")
except PackageNotFoundError:
    __version__ = "0.0.3-dev"
