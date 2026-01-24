#!/usr/bin/env python
"""
dm-dbcore
SQLAlchemy database connection wrapper with multi-database support,
metadata caching, and custom type adapters.
"""

from setuptools import setup, find_packages
import pathlib

# Read the README file
here = pathlib.Path(__file__).parent.resolve()
long_description = (here / "README.md").read_text(encoding="utf-8")

setup(
    name="dm-dbcore",
    version="0.1.0",
    description="SQLAlchemy database connection wrapper with metadata caching and multi-database support",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/demitri/dm-dbcore", 
    author="Demitri Muna",
    author_email="pypi@nightlightresearch.com",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Database",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    keywords="sqlalchemy, database, postgresql, mysql, sqlite, orm",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "sqlalchemy>=2.0.0",
    ],
    extras_require={
        "postgresql": ["psycopg[binary]>=3.0"],
        "mysql": ["pymysql>=1.0.0"],
        "numpy": ["numpy>=1.20.0"],
        "dev": ["pytest>=7.0", "black", "flake8"],
    },
    project_urls={
        "Bug Reports": "https://github.com/demitri/dm-dbcore/issues",
        "Source": "https://github.com/demitri/dm-dbcore",
    },
)
