"""Tests for WideEventLogger class."""

import pytest
from bot_detector.wide_event.core import WideEventLogger


def test_set_and_get():
    """Test basic set and get operations."""
    logger = WideEventLogger()
    token = logger.set({"key": "value"})
    assert logger.get() == {"key": "value"}
    logger.reset(token)


def test_set_empty_dict():
    """Test setting an empty dictionary."""
    logger = WideEventLogger()
    token = logger.set({})
    assert logger.get() == {}
    logger.reset(token)


def test_get_without_set():
    """Test get returns empty dict when no set has been called."""
    logger = WideEventLogger()
    assert logger.get() == {}


def test_reset_without_set_raises():
    """Test reset raises TypeError when called with None."""
    logger = WideEventLogger()
    # ContextVar requires a valid token, not None
    with pytest.raises(TypeError, match="expected an instance of Token, got None"):
        logger.reset(None)


def test_reset_to_previous_state():
    """Test reset restores previous context state."""
    logger = WideEventLogger()
    token1 = logger.set({"key1": "value1"})
    assert logger.get() == {"key1": "value1"}

    token2 = logger.set({"key2": "value2"})
    assert logger.get() == {"key2": "value2"}

    logger.reset(token2)
    assert logger.get() == {"key1": "value1"}  # State before token2

    logger.reset(token1)
    assert logger.get() == {}  # State before token1


def test_add_shallow_value():
    """Test add merges new key-value pairs at the top level."""
    logger = WideEventLogger()
    token = logger.set({"existing": "value"})

    logger.add({"new_key": "new_value"})
    assert logger.get() == {"existing": "value", "new_key": "new_value"}

    logger.reset(token)


def test_add_empty_dict():
    """Test add with empty dict doesn't change context."""
    logger = WideEventLogger()
    token = logger.set({"key": "value"})

    logger.add({})
    assert logger.get() == {"key": "value"}

    logger.reset(token)


def test_add_nested_dict_merge():
    """Test add merges nested dictionaries recursively."""
    logger = WideEventLogger()
    token = logger.set(
        {"outer": {"inner": "unchanged", "inner_nested": {"deep": "original"}}}
    )

    logger.add(
        {
            "outer": {
                "inner": "updated",
                "inner_nested": {"deep": "merged", "new_deep": "added"},
            }
        }
    )

    result = logger.get()
    assert result["outer"]["inner"] == "updated"
    assert result["outer"]["inner_nested"]["deep"] == "merged"
    assert result["outer"]["inner_nested"]["new_deep"] == "added"
    logger.reset(token)


def test_add_overwrites_shallow_keys():
    """Test add overwrites existing keys at the top level."""
    logger = WideEventLogger()
    token = logger.set({"key": "original"})

    logger.add({"key": "overwritten"})
    assert logger.get() == {"key": "overwritten"}

    logger.reset(token)


def test_add_overwrites_nested_keys():
    """Test add overwrites nested dictionary values."""
    logger = WideEventLogger()
    token = logger.set({"level1": {"level2": "original"}})

    logger.add({"level1": {"level2": "overwritten"}})

    assert logger.get() == {"level1": {"level2": "overwritten"}}
    logger.reset(token)


def test_add_multiple_times():
    """Test add can be called multiple times to accumulate data."""
    logger = WideEventLogger()
    token = logger.set({"first": 1})

    logger.add({"second": 2})
    logger.add({"third": 3})

    assert logger.get() == {"first": 1, "second": 2, "third": 3}
    logger.reset(token)


def test_merge_with_non_dict_arg_a():
    """Test _merge raises TypeError when first argument is not a dict."""
    logger = WideEventLogger()
    with pytest.raises(TypeError, match="Both arguments must be dicts"):
        logger._merge("not_a_dict", {"key": "value"})  # type: ignore


def test_merge_with_non_dict_arg_b():
    """Test _merge raises TypeError when second argument is not a dict."""
    logger = WideEventLogger()
    with pytest.raises(TypeError, match="Both arguments must be dicts"):
        logger._merge({"key": "value"}, "not_a_dict")  # type: ignore


def test_merge_with_none_arg():
    """Test _merge raises TypeError when either argument is None."""
    logger = WideEventLogger()
    with pytest.raises(TypeError, match="Both arguments must be dicts"):
        logger._merge({"key": "value"}, None)  # type: ignore

    with pytest.raises(TypeError, match="Both arguments must be dicts"):
        logger._merge(None, {"key": "value"})  # type: ignore


def test_merge_with_list_value():
    """Test _merge handles list values correctly."""
    logger = WideEventLogger()
    result = logger._merge({"list": [1, 2, 3]}, {"list": [4, 5, 6]})
    assert result["list"] == [4, 5, 6]


def test_merge_with_mixed_types():
    """Test _merge handles mixed types in dictionaries."""
    logger = WideEventLogger()
    result = logger._merge(
        {"key1": "string", "key2": 123, "key3": True, "key4": None},
        {"key1": "updated", "key2": 456, "key5": "new"},
    )
    assert result == {
        "key1": "updated",
        "key2": 456,
        "key3": True,
        "key4": None,
        "key5": "new",
    }


def test_merge_with_empty_dicts():
    """Test _merge handles empty dictionaries."""
    logger = WideEventLogger()
    result = logger._merge({}, {"key": "value"})
    assert result == {"key": "value"}

    result = logger._merge({"key": "value"}, {})
    assert result == {"key": "value"}

    result = logger._merge({}, {})
    assert result == {}


def test_merge_preserves_original_dict():
    """Test _merge doesn't modify the original dictionaries."""
    dict_a = {"key": "value"}
    dict_b = {"key": {"nested": "value"}}

    logger = WideEventLogger()
    _ = logger._merge(dict_a.copy(), dict_b)
    assert dict_a == {"key": "value"}
    assert dict_b == {"key": {"nested": "value"}}


def test_add_modifies_context():
    """Test add merges new data into existing context."""
    logger = WideEventLogger()
    _ = logger.set({"key1": "value1"})

    # Add new data
    logger.add({"key2": "value2"})
    result = logger.get()
    assert result == {"key1": "value1", "key2": "value2"}


def test_deeply_nested_merge():
    """Test _merge handles deeply nested dictionaries."""
    logger = WideEventLogger()
    result = logger._merge(
        {"a": {"b": {"c": {"d": "original"}}}}, {"a": {"b": {"c": {"d": "merged"}}}}
    )
    assert result["a"]["b"]["c"]["d"] == "merged"


def test_complex_nested_structure():
    """Test _merge with complex nested structure."""
    logger = WideEventLogger()
    result = logger._merge(
        {"users": {"user1": {"name": "Alice", "age": 30}, "user2": {"name": "Bob"}}},
        {
            "users": {
                "user1": {"name": "Alice Updated", "email": "alice@example.com"},
                "user3": {"name": "Charlie", "age": 25},
            }
        },
    )
    assert result == {
        "users": {
            "user1": {"name": "Alice Updated", "age": 30, "email": "alice@example.com"},
            "user2": {"name": "Bob"},
            "user3": {"name": "Charlie", "age": 25},
        }
    }


def test_add_with_deeply_nested_struct():
    """Test add with deeply nested dictionary structure."""
    logger = WideEventLogger()
    _ = logger.set(
        {
            "config": {
                "database": {
                    "host": "localhost",
                    "port": 3306,
                    "settings": {"ssl": False},
                }
            }
        }
    )

    logger.add({"config": {"database": {"port": 5432, "settings": {"ssl": True}}}})

    result = logger.get()
    assert result["config"]["database"]["host"] == "localhost"
    assert result["config"]["database"]["port"] == 5432
    assert result["config"]["database"]["settings"]["ssl"] is True


def test_multiple_add_on_nested_struct():
    """Test multiple add calls on nested structure."""
    logger = WideEventLogger()
    token = logger.set({"level1": {"level2": {"level3": "value"}}})

    logger.add({"level1": {"level2": {"level4": "new"}}})
    logger.add({"level1": {"level5": "added"}})

    result = logger.get()
    assert result["level1"]["level2"]["level3"] == "value"
    assert result["level1"]["level2"]["level4"] == "new"
    assert result["level1"]["level5"] == "added"
    logger.reset(token)


def test_set_different_data_types():
    """Test set with various data types."""
    logger = WideEventLogger()

    token1 = logger.set({"int": 42, "float": 3.14, "bool": True, "str": "hello"})
    assert logger.get() == {"int": 42, "float": 3.14, "bool": True, "str": "hello"}
    logger.reset(token1)

    token2 = logger.set({"list": [1, 2, 3], "dict": {"nested": "value"}})
    assert logger.get() == {"list": [1, 2, 3], "dict": {"nested": "value"}}
    logger.reset(token2)
