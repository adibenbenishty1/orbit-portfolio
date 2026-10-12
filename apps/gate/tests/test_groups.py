# -*- coding: utf-8 -*-
#
# testing for group normalisation
#
# ------------------------------------------------


# imports
# -------
from gate.auth import groups


# convert
# -------
def test_prefixed_group_becomes_service_role():
    assert groups.convert('orbit-catalog-read') == 'catalog:read'


def test_service_name_may_contain_a_dash():
    assert groups.convert('orbit-data-lake-write') == 'data-lake:write'


def test_conversion_is_case_insensitive():
    assert groups.convert('Orbit-Catalog-Admin') == 'catalog:admin'


def test_surrounding_whitespace_is_ignored():
    assert groups.convert('  orbit-catalog-read  ') == 'catalog:read'


# drop
# ----
def test_group_without_the_prefix_is_dropped():
    # the prefix is an allowlist -- an unrelated directory membership must not
    # become part of the authorisation vocabulary
    assert groups.convert('finance-payroll-admin') is None


def test_group_without_a_known_role_is_dropped():
    assert groups.convert('orbit-catalog-superuser') is None


def test_group_with_no_role_at_all_is_dropped():
    assert groups.convert('orbit-catalog') is None


def test_group_that_is_only_a_role_is_dropped():
    assert groups.convert('orbit-read') is None


# normalise
# ---------
def test_normalise_filters_and_sorts():
    assert groups.normalise([
        'orbit-catalog-write',
        'finance-payroll-admin',
        'orbit-catalog-read',
    ]) == ['catalog:read', 'catalog:write']


def test_normalise_deduplicates():
    # two directory spellings collapsing to one entry is the point of
    # normalising, and a duplicated claim would be noise on every request
    assert groups.normalise(['orbit-catalog-read', 'Orbit-Catalog-Read']) == ['catalog:read']


def test_normalise_handles_nothing():
    assert groups.normalise([]) == []
    assert groups.normalise(None) == []


def test_normalise_drops_everything_when_nothing_matches():
    assert groups.normalise(['finance-payroll-admin', 'random']) == []
