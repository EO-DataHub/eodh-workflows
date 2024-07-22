from __future__ import annotations

from setuptools import find_packages, setup

setup(
    packages=find_packages(exclude=["tests", "docs"]),
)
