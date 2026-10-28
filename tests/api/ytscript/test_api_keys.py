import logging

import pytest

from infra.errors import InvalidApiKeyError
from ytscript.api_keys import ApiKeys, api_keys_from_env

KEY = "a" * 40
OTHER = "b" * 40


def test_without_a_key_there_is_no_identity():
    assert ApiKeys([KEY]).authenticate(None) is None


def test_valid_key_returns_stable_id_that_is_not_the_key():
    keys = ApiKeys([KEY, OTHER])
    key_id = keys.authenticate(KEY)
    assert key_id == keys.authenticate(KEY)
    assert key_id != keys.authenticate(OTHER)
    assert KEY not in key_id and len(key_id) == 16


@pytest.mark.parametrize("provided", ["", " ", "c" * 40, KEY + "x", KEY[:-1], KEY.upper()])
def test_unknown_key_is_rejected_with_exact_body(provided):
    with pytest.raises(InvalidApiKeyError) as exc:
        ApiKeys([KEY]).authenticate(provided)
    assert exc.value.to_dict() == InvalidApiKeyError().to_dict()


def test_any_key_is_rejected_when_none_are_configured():
    with pytest.raises(InvalidApiKeyError):
        ApiKeys([]).authenticate(KEY)


def test_short_keys_are_ignored_and_logged(caplog):
    keys = ApiKeys(["curta", KEY])
    with caplog.at_level(logging.WARNING):
        ApiKeys(["curta"])
    assert "menos de 32" in caplog.text
    with pytest.raises(InvalidApiKeyError):
        keys.authenticate("curta")
    assert keys.authenticate(KEY)


def test_keys_are_only_kept_as_digests():
    keys = ApiKeys([KEY])
    assert KEY not in repr(vars(keys))


def test_from_env_splits_on_commas_and_skips_blanks(monkeypatch):
    monkeypatch.setenv("YTSCRIPT_API_KEYS", f" {KEY} , ,{OTHER},")
    keys = api_keys_from_env()
    assert keys.authenticate(KEY) and keys.authenticate(OTHER)


def test_from_env_without_variable_has_no_keys(monkeypatch):
    monkeypatch.delenv("YTSCRIPT_API_KEYS", raising=False)
    with pytest.raises(InvalidApiKeyError):
        api_keys_from_env().authenticate(KEY)
