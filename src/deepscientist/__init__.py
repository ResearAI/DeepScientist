from importlib.metadata import PackageNotFoundError, version as _package_version

__all__ = ["__version__"]

try:
    __version__ = _package_version("deepscientist")
except PackageNotFoundError:  # pragma: no cover - source checkout fallback
    __version__ = "1.5.9"
