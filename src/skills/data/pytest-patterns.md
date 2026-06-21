---
name: pytest-patterns
description: pytest test writing best practices and common patterns
triggers:
  - pytest
  - test
  - fixture
  - conftest
  - parametrize
  - assert
---

# pytest Test Writing Patterns

## Naming Conventions
- Test files: `test_<module>.py`
- Test functions: `test_<function>_<scenario>` or `test_<method>_<scenario>`
- Test classes: `Test<Feature>` (no `__init__`)

## Fixture Design
- Use `conftest.py` for shared fixtures across test files
- Scope fixtures: `function` (default), `class`, `module`, `session`
- Use `yield` fixtures for setup/teardown
- Use `@pytest.fixture(autouse=True)` for global setup

## Parametrize
- `@pytest.mark.parametrize("a,b,expected", [(1,2,3), (0,0,0)])` for multiple inputs
- Use `pytest.param(..., marks=pytest.mark.skip)` to skip specific combos

## Assertions
- Always use plain `assert` — NEVER `self.assertEqual`
- Be specific: `assert result == 42` not `assert result is not None`
- For exceptions: `with pytest.raises(ValueError, match="expected msg"):`
- For approximate floats: `assert result == pytest.approx(3.14, rel=1e-3)`

## Directory Structure
```
tests/
  ├── __init__.py          # empty, required for imports
  ├── conftest.py          # shared fixtures
  ├── test_module_a.py
  └── test_module_b.py
```

## Mock Best Practices
- Mock at the point of USE, not the point of definition
- Patch path: `@patch("mymodule.requests.get")` — module WHERE it's used
- Use `pytest-mock` `mocker` fixture when available
- Always verify: `mock_fn.assert_called_once_with(expected_arg)`
