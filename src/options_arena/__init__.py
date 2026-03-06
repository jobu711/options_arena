"""Options Arena - AI-powered options analysis tool."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("options-arena")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
