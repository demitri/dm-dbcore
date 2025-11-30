#!/usr/bin/env python

"""Utility helpers for working with MySQL configuration files."""

from __future__ import annotations

from configparser import ConfigParser
from os.path import expanduser
from pathlib import Path
from typing import Optional


def read_password_from_my_cnf(
    *,
    host: Optional[str] = None,
    user: Optional[str] = None,
    section: Optional[str] = None,
    mycnf_path: str = "~/.my.cnf",
) -> Optional[str]:
    """Return the password stored in a MySQL option file if it matches the criteria.

    Parameters
    ----------
    host:
        Optional hostname to match (compared case-sensitively). If provided and
        the config specifies a different host, no password is returned.
    user:
        Optional username to match. Same behavior as ``host``.
    section:
        Option group within ``.my.cnf`` to inspect; defaults to ``client``. If the
        requested group does not exist, the search falls back to ``client`` and any
        other defined sections.
    mycnf_path:
        Filesystem path to the option file. Defaults to ``~/.my.cnf``.

    Returns
    -------
    str | None
        The password string if found, otherwise ``None``.
    """

    parser = _load_my_cnf_parser(mycnf_path)
    if parser is None:
        return None

    normalized_host = _normalize_host(host) if host else None

    for section_name in _candidate_sections(parser, section):
        options = parser[section_name]

        if normalized_host is not None:
            option_host = options.get("host")
            if option_host is not None and _normalize_host(option_host) != normalized_host:
                continue

        if user is not None:
            option_user = options.get("user")
            if option_user is not None and option_user != user:
                continue

        password = options.get("password") or options.get("passwd")
        if password:
            return password

    return None


def read_connection_options_from_my_cnf(
    *,
    section: Optional[str] = None,
    mycnf_path: str = "~/.my.cnf",
) -> dict[str, str]:
    """Return a mapping of database connection options discovered in ``.my.cnf``.

    The lookup obeys the same section fallback rules as
    :func:`read_password_from_my_cnf`, preferring the requested group when
    available, then ``client``, followed by any other defined group.
    """

    parser = _load_my_cnf_parser(mycnf_path)
    if parser is None:
        return {}

    for section_name in _candidate_sections(parser, section):
        options = parser[section_name]
        extracted: dict[str, str] = {}

        for target, aliases in {
            "host": ("host",),
            "user": ("user",),
            "database": ("database", "db", "schema"),
            "password": ("password", "passwd"),
            "port": ("port",),
        }.items():
            for alias in aliases:
                value = options.get(alias)
                if value:
                    extracted[target] = value
                    break

        if extracted:
            return extracted

    return {}


def _normalize_host(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    if normalized in {"127.0.0.1", "localhost"}:
        return "127.0.0.1"
    return normalized


def _load_my_cnf_parser(mycnf_path: str) -> Optional[ConfigParser]:
    config_path = Path(expanduser(mycnf_path))
    if not config_path.exists():
        return None

    parser = ConfigParser()
    parser.optionxform = str  # preserve case
    try:
        with config_path.open() as handle:
            parser.read_file(handle)
    except OSError:
        return None

    return parser


def _candidate_sections(parser: ConfigParser, section: Optional[str]) -> list[str]:
    if section:
        if parser.has_section(section):
            return [section]
        # Fall back to the default lookup order if the explicit section does not exist.

    seen = set()
    ordered = []
    if parser.has_section("client"):
        ordered.append("client")
        seen.add("client")
    for name in parser.sections():
        if name not in seen:
            ordered.append(name)
    return ordered
