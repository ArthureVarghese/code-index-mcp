from code_index_mcp.cache.invalidation import (
    InvalidationPlan,
    calculate_invalidation,
)


def test_only_changed_entity_is_invalidated():
    plan = calculate_invalidation(
        old_hashes={
            "a": "1",
            "b": "2",
            "c": "3",
        },
        new_hashes={
            "a": "1",
            "b": "changed",
            "c": "3",
        },
    )

    assert plan.changed == {"b"}
    assert plan.unchanged == {"a", "c"}


def test_removed_property():
    plan = InvalidationPlan(removed_entities={"x", "y"})
    assert plan.removed == {"x", "y"}


def test_has_changes_true_when_changed():
    plan = InvalidationPlan(changed_entities={"a"})
    assert plan.has_changes is True


def test_has_changes_true_when_removed():
    plan = InvalidationPlan(removed_entities={"a"})
    assert plan.has_changes is True


def test_has_changes_true_when_files_changed():
    plan = InvalidationPlan(changed_files={"f.py"})
    assert plan.has_changes is True


def test_has_changes_true_when_files_removed():
    plan = InvalidationPlan(removed_files={"f.py"})
    assert plan.has_changes is True


def test_has_changes_true_when_search_invalidated():
    plan = InvalidationPlan(invalidate_search={"a"})
    assert plan.has_changes is True


def test_has_changes_true_when_structural():
    plan = InvalidationPlan(structural_changes={"a"})
    assert plan.has_changes is True


def test_has_changes_false_when_empty():
    plan = InvalidationPlan()
    assert plan.has_changes is False


def test_added_and_removed():
    plan = calculate_invalidation(
        old_hashes={"a": "1"},
        new_hashes={"b": "2"},
    )
    assert plan.changed == {"b"}
    assert plan.removed == {"a"}
    assert plan.unchanged == set()
