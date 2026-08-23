"""Tests for the MySQL option-file readers (no database required).

``.my.cnf`` parsing is pure file handling, so these tests write real option
files to a temporary directory and read them back. Nothing is mocked: the
functions open the paths they are given.

The section fallback rules are the subtle part. An explicitly named group wins
if it exists; otherwise ``client`` is tried first, then every other group in
file order. That ordering decides which password a caller gets, so it is
pinned here rather than left to be rediscovered.
"""

import pytest

from dm_dbcore.mysql import (
    read_connection_options_from_my_cnf,
    read_password_from_my_cnf,
)


@pytest.fixture
def write_cnf(tmp_path):
    """Write an option file and return its path as a string."""
    def _write(contents, name=".my.cnf"):
        path = tmp_path / name
        path.write_text(contents, encoding="utf-8")
        return str(path)

    return _write


# --------------------------------------------------------------------------
# read_password_from_my_cnf
# --------------------------------------------------------------------------

def test_reads_password_from_client_section(write_cnf):
    path = write_cnf("[client]\nuser=alice\npassword=s3cret\n")
    assert read_password_from_my_cnf(mycnf_path=path) == "s3cret"


def test_accepts_the_passwd_spelling(write_cnf):
    """MySQL option files use both `password` and `passwd`."""
    path = write_cnf("[client]\nuser=alice\npasswd=s3cret\n")
    assert read_password_from_my_cnf(mycnf_path=path) == "s3cret"


def test_missing_file_returns_none(write_cnf, tmp_path):
    assert read_password_from_my_cnf(mycnf_path=str(tmp_path / "absent.cnf")) is None


def test_no_password_anywhere_returns_none(write_cnf):
    path = write_cnf("[client]\nuser=alice\nhost=db.example.org\n")
    assert read_password_from_my_cnf(mycnf_path=path) is None


@pytest.mark.parametrize(
    "configured,requested",
    [
        pytest.param("localhost", "127.0.0.1", id="localhost-matches-loopback-ip"),
        pytest.param("127.0.0.1", "localhost", id="loopback-ip-matches-localhost"),
        pytest.param("  db.example.org  ", "db.example.org", id="whitespace-is-stripped"),
    ],
)
def test_host_matching_normalizes_loopback_and_whitespace(write_cnf, configured, requested):
    path = write_cnf(f"[client]\nhost={configured}\npassword=s3cret\n")
    assert read_password_from_my_cnf(host=requested, mycnf_path=path) == "s3cret"


def test_host_mismatch_yields_no_password(write_cnf):
    """A password for the wrong host is worse than no password."""
    path = write_cnf("[client]\nhost=db.example.org\npassword=s3cret\n")
    assert read_password_from_my_cnf(host="other.example.org", mycnf_path=path) is None


def test_user_mismatch_yields_no_password(write_cnf):
    path = write_cnf("[client]\nuser=alice\npassword=s3cret\n")
    assert read_password_from_my_cnf(user="bob", mycnf_path=path) is None


def test_a_section_without_the_key_does_not_filter(write_cnf):
    """A group that names no host applies to any host."""
    path = write_cnf("[client]\npassword=s3cret\n")
    assert read_password_from_my_cnf(host="anything", mycnf_path=path) == "s3cret"


def test_named_section_wins_when_it_exists(write_cnf):
    path = write_cnf(
        "[client]\nuser=alice\npassword=client-pw\n"
        "[myapp]\nuser=alice\npassword=app-pw\n"
    )
    assert read_password_from_my_cnf(section="myapp", mycnf_path=path) == "app-pw"
    assert read_password_from_my_cnf(mycnf_path=path) == "client-pw"


def test_unknown_section_falls_back_to_client_then_the_rest(write_cnf):
    """An absent group is not an error -- the documented fallback order applies."""
    path = write_cnf("[client]\nuser=alice\n[myapp]\npassword=app-pw\n")
    assert read_password_from_my_cnf(section="nosuch", mycnf_path=path) == "app-pw"


def test_client_is_searched_before_other_sections(write_cnf):
    """`client` wins even when it is written last in the file."""
    path = write_cnf("[myapp]\npassword=app-pw\n[client]\npassword=client-pw\n")
    assert read_password_from_my_cnf(mycnf_path=path) == "client-pw"


def test_valueless_options_are_tolerated(write_cnf):
    """Real option files carry bare flags: `no-auto-rehash`, `quick`, `skip-ssl`.

    These have no `=value`. A parser that rejects them cannot read the files it
    exists to read, and the failure surfaces as a configparser ParsingError
    naming a temp path rather than anything a user can act on.
    """
    path = write_cnf(
        "[client]\nuser=alice\npassword=s3cret\n"
        "[mysql]\nno-auto-rehash\nquick\n"
    )
    assert read_password_from_my_cnf(mycnf_path=path) == "s3cret"


def test_an_unreadable_file_raises_rather_than_reading_as_absent(write_cnf):
    """A file that exists but cannot be read is not the same as no file.

    Conflating the two turned the commonest ~/.my.cnf misconfiguration -- wrong
    permissions -- into a silent "no password found", leaving the user with
    MySQL's bare "Access denied" and nothing pointing at the real cause.
    """
    import os
    import stat

    path = write_cnf("[client]\npassword=s3cret\n")
    os.chmod(path, 0o000)
    try:
        if os.access(path, os.R_OK):  # root, or a filesystem ignoring the mode
            pytest.skip("this user can read a mode-000 file; permissions not enforced here")
        with pytest.raises(OSError):
            read_password_from_my_cnf(mycnf_path=path)
    finally:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def test_password_keyword_arguments_are_keyword_only(write_cnf):
    """The signature is keyword-only; positional use is a TypeError, not a silent mismatch."""
    path = write_cnf("[client]\npassword=s3cret\n")
    with pytest.raises(TypeError):
        read_password_from_my_cnf("localhost", "alice", None, path)  # noqa: B026


# --------------------------------------------------------------------------
# read_connection_options_from_my_cnf
# --------------------------------------------------------------------------

def test_reads_all_connection_options(write_cnf):
    path = write_cnf(
        "[client]\nhost=db.example.org\nuser=alice\npassword=s3cret\n"
        "database=mydb\nport=3307\n"
    )
    assert read_connection_options_from_my_cnf(mycnf_path=path) == {
        "host": "db.example.org",
        "user": "alice",
        "password": "s3cret",
        "database": "mydb",
        "port": "3307",
    }


@pytest.mark.parametrize("alias", ["database", "db", "schema"])
def test_database_name_aliases(write_cnf, alias):
    path = write_cnf(f"[client]\n{alias}=mydb\n")
    assert read_connection_options_from_my_cnf(mycnf_path=path)["database"] == "mydb"


def test_only_the_keys_present_are_returned(write_cnf):
    """The result is partial, not a fixed-shape dict with None holes."""
    path = write_cnf("[client]\nuser=alice\n")
    assert read_connection_options_from_my_cnf(mycnf_path=path) == {"user": "alice"}


def test_port_stays_a_string(write_cnf):
    """No int coercion happens here; callers that need an int must convert."""
    path = write_cnf("[client]\nport=3307\n")
    assert read_connection_options_from_my_cnf(mycnf_path=path)["port"] == "3307"


def test_missing_file_returns_empty_mapping(tmp_path):
    assert read_connection_options_from_my_cnf(mycnf_path=str(tmp_path / "absent.cnf")) == {}


def test_a_file_with_no_usable_options_returns_empty_mapping(write_cnf):
    path = write_cnf("[client]\nunrelated=value\n")
    assert read_connection_options_from_my_cnf(mycnf_path=path) == {}


def test_options_named_section_wins_then_falls_back(write_cnf):
    path = write_cnf("[client]\nuser=alice\n[myapp]\nuser=bob\n")
    assert read_connection_options_from_my_cnf(section="myapp", mycnf_path=path) == {"user": "bob"}
    assert read_connection_options_from_my_cnf(section="nosuch", mycnf_path=path) == {"user": "alice"}


def test_options_skip_sections_with_nothing_usable(write_cnf):
    """An empty `client` group must not shadow a later group that has options."""
    path = write_cnf("[client]\n[myapp]\nuser=bob\nhost=db.example.org\n")
    assert read_connection_options_from_my_cnf(mycnf_path=path) == {
        "user": "bob",
        "host": "db.example.org",
    }


# --------------------------------------------------------------------------
# Percent signs
#
# MySQL option-file values are literal, but ConfigParser's default
# BasicInterpolation reads `%` as an escape. That default made a percent sign
# in a password either a crash or, worse, a silent rewrite -- so both shapes
# are pinned here.
# --------------------------------------------------------------------------

def test_password_with_a_single_percent_is_read_literally(write_cnf):
    """`pa%ss` used to raise InterpolationSyntaxError instead of parsing."""
    path = write_cnf("[client]\nuser=alice\npassword=pa%ss\n")
    assert read_password_from_my_cnf(mycnf_path=path) == "pa%ss"


def test_password_with_a_doubled_percent_is_not_collapsed(write_cnf):
    """`100%%safe` must come back as written, not silently shortened."""
    path = write_cnf("[client]\nuser=alice\npassword=100%%safe\n")
    assert read_password_from_my_cnf(mycnf_path=path) == "100%%safe"


def test_percent_paren_password_is_not_treated_as_a_reference(write_cnf):
    """The interpolation syntax proper: `%(user)s` is a password, not a lookup."""
    path = write_cnf("[client]\nuser=alice\npassword=%(user)s\n")
    assert read_password_from_my_cnf(mycnf_path=path) == "%(user)s"


def test_options_reader_also_reads_percents_literally(write_cnf):
    path = write_cnf("[client]\nuser=alice\npassword=pa%ss\ndatabase=db%%1\n")
    options = read_connection_options_from_my_cnf(mycnf_path=path)
    assert options["password"] == "pa%ss"
    assert options["database"] == "db%%1"
