---
name: mock-strategy
description: When and how to use Mock/Stub/Fake for external dependencies
triggers:
  - mock
  - patch
  - stub
  - fake
  - external
  - HTTP
  - database
  - file I/O
  - network
  - requests
  - sql
  - redis
---

# Mock Strategy Guide

## When to Mock
| Dependency Type | Mock? | Reason |
|-----------------|-------|--------|
| HTTP/API calls (requests, httpx, urllib) | YES | Network is slow, flaky, unavailable in CI |
| Database (sqlite3, sqlalchemy, psycopg2, pymongo) | YES | Need specific data state, no side effects |
| File I/O (open, pathlib writes) | YES | Avoid disk state pollution between tests |
| Redis/Cache | YES | May not be running in test environment |
| Email/SMTP | YES | Don't send real emails |
| Time/sleep (time.time, datetime.now) | YES | Tests must be deterministic |
| Random | YES | Tests must be deterministic |
| Subprocess | YES | Security and determinism |
| Pure functions (math, string ops) | NO | No side effects, fast, deterministic |
| Built-in data structures (list, dict) | NO | No external dependency |
| Standard library algorithms | NO | Well-tested and fast |

## How to Mock
```python
# CORRECT: mock where it's USED
from unittest.mock import patch

@patch("mymodule.requests.get")
def test_fetch(mock_get):
    mock_get.return_value.json.return_value = {"name": "Alice"}
    result = fetch_user(42)
    assert result == "Alice"
```

## Mock Levels
1. **Mock the function call** — simplest, for direct external calls
2. **Mock the object** — for complex external objects (db connection)
3. **Mock the module** — for when entire module is external (rare)

## Never Mock
- The function under test itself
- Python standard library (except I/O, network, time)
- Simple data classes or value objects
