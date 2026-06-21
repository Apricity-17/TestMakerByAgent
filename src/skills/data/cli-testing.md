---
name: cli-testing
description: Strategies for testing command-line interface (CLI) programs, especially Java CLI tools
triggers:
  - CLI
  - main
  - Main
  - main(String
  - command-line
  - subprocess
  - System.exit
  - SecurityManager
  - exit code
  - stdout
  - stderr
  - dispatch
  - args
  - arguments
---

# CLI Testing Strategies

## Key Challenges
1. `System.exit()` kills the JVM — must trap or intercept
2. `main(String[] args)` dispatches to many methods — need to test each case
3. CLI programs often print to stdout/stderr — need to capture output
4. CLI programs may depend on filesystem state (`.gitlet` directory, etc.)

## Pattern 1: SecurityManager for System.exit() (Java)

```java
private static class NoExitSecurityManager extends SecurityManager {
    @Override
    public void checkExit(int status) {
        throw new ExitException(status);
    }
}

static class ExitException extends SecurityException {
    final int status;
    ExitException(int status) { this.status = status; }
}
```

## Pattern 2: MockedStatic for Repository Dispatch (Java + Mockito)

```java
try (MockedStatic<Repository> repo = mockStatic(Repository.class)) {
    Main.main(new String[]{"add", "file.txt"});
    repo.verify(() -> Repository.add("file.txt"));
}
```

## Pattern 3: Subprocess for Integration Tests (Python)

```python
result = subprocess.run(
    ["java", "-ea", "-cp", classpath, "gitlet.Main"] + args,
    capture_output=True, text=True, timeout=10, cwd=tmp_dir
)
assert result.returncode == 0
assert "expected output" in result.stdout
```

## Pattern 4: MockedConstruction for File Dependencies (Java)

```java
try (MockedConstruction<File> mocked = mockConstruction(File.class,
        (mock, ctx) -> when(mock.exists()).thenReturn(false))) {
    // Main.main checks new File(".gitlet").exists() → returns false
    // Verifies: "Not in an initialized Gitlet directory."
}
```

## Pattern 5: Subprocess Integration Test Fixtures (Python)

```python
@pytest.fixture
def cwd_with_gitlet(tmp_path):
    """Create temp dir with .gitlet/ directory."""
    (tmp_path / ".gitlet").mkdir()
    return tmp_path

@pytest.fixture
def tmp_cwd(tmp_path):
    """Clean temp dir without .gitlet/."""
    return tmp_path
```

## Pattern 6: Conditional Skip When Compilation Missing (Python)

```python
import pytest, subprocess
requires_gitlet = pytest.mark.skipif(
    subprocess.run(["which", "java"], capture_output=True).returncode != 0,
    reason="Java not available"
)
```

## Test Checklist for CLI Programs

For each command dispatched by `main()`:
- [ ] Normal path: correct args → delegates correctly
- [ ] Wrong arg count: too few / too many → error message
- [ ] Missing required state: `.gitlet` absent → error message
- [ ] Exception from delegate: `GitletException` → exit(0) or exit(-1)
- [ ] Unknown command: default case → error message

For `checkout`-style multi-arity commands:
- [ ] Each arity variant gets separate test cases
- [ ] Wrong arity → error for each variant
- [ ] Malformed args (e.g., `--` in wrong position)

For `main()` itself:
- [ ] Empty args → error + exit(0)
- [ ] All 20+ cases in switch statement covered
- [ ] Both catch blocks tested (GitletException + generic Exception)
