"""Reviewed mapping semantics stay pinned for the lifetime of an integration."""

from dataclasses import FrozenInstanceError

import pytest

pytest.importorskip("aiogram_nav")

from aiogram_idle.integrations.nav import NodePolicies


@pytest.mark.parametrize(
    "field,value", [("default", "other"), ("overrides", {}), ("activities", {})]
)
def test_node_policy_definition_cannot_be_reassigned(field, value):
    source = {"form": "draft"}
    policies = NodePolicies(default="none", overrides=source, activities={"form": "form"})
    digest = policies.digest
    source["form"] = "none"
    assert policies.overrides["form"] == "draft"
    with pytest.raises(FrozenInstanceError):
        setattr(policies, field, value)
    assert policies.digest == digest
