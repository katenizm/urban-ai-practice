"""
Irkutsk urban metrics.

The package stores project metadata. The analysis pipeline lives in
``notebooks/practice_02.ipynb`` and the dashboard builder in ``dashboard.py``.
"""

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("my_package")
except PackageNotFoundError:
    __version__ = "0.0.0"

__author__ = "Ekaterina Kumanina"
__email__ = "katenizm@gmail.com"
__credits__ = []
__license__ = "BSD-3"
