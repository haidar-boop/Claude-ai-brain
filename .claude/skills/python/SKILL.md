---
name: python
description: Python coding best practices, idiomatic patterns, debugging strategies, performance optimization, testing approach, and a code review checklist -- covering Django, FastAPI, Flask, pytest, SQLAlchemy, pandas, numpy, and general Python 3 code. Use this skill whenever the user is writing, reviewing, refactoring, debugging, or optimizing Python code, or asks about Python tooling like pip, venv, or pytest -- even if they don't explicitly say "Python" or ask for "best practices."
---

# Python

Python language, ecosystem, and idiomatic patterns for scripting, web backends, and data work
(Django, FastAPI, Flask, pytest, SQLAlchemy, Celery, requests, numpy, pandas, pydantic, httpx, click).

## Coding patterns

- Use context managers (the `with` statement, or `@contextlib.contextmanager`) for resource management instead of manual try/finally acquire-release pairs
- Prefer list/dict/set comprehensions and generator expressions over `map()`/`filter()` calls or manual accumulation loops
- Use decorators to wrap cross-cutting concerns like caching (`functools.lru_cache`), timing, or retries without touching the wrapped function's core logic
- Choose `dataclasses.dataclass` for mutable, attribute-heavy records and `typing.NamedTuple` for small immutable tuples that need named fields
- Write generator functions (`yield`) or generator expressions for lazily evaluated, memory-efficient iteration instead of materializing large lists
- Annotate function signatures with type hints per PEP 484, using PEP 604 union syntax (`int | None`) instead of `Optional[int]` on Python 3.10+
- Use `async def`/`await` with asyncio for I/O-bound concurrency, and `asyncio.gather`/`asyncio.TaskGroup` to run coroutines concurrently
- Add `__slots__` to classes instantiated in bulk to cut per-instance memory overhead and prevent accidental attribute creation
- Structure packaging around `pyproject.toml` with `[build-system]` and `[project]` tables instead of a legacy `setup.py`
- Use `pathlib.Path` for filesystem paths instead of string-based `os.path` manipulation

## Best practices

- Follow PEP 8 for naming, layout, and import ordering, enforced with a formatter like black and a linter like ruff
- Pin dependencies with a lockfile (poetry.lock, uv.lock, or pip-tools' requirements.txt) so builds are reproducible
- Isolate project dependencies in a virtual environment (venv or uv venv) rather than installing into the system interpreter
- Keep public API surface explicit with `__all__` in modules intended for wildcard import or as package entry points
- Prefer composition and small, focused functions over deep inheritance hierarchies
- Use the logging module instead of print for anything beyond a throwaway script, with proper levels and handlers configured
- Validate and parse external input at the boundary (e.g., with pydantic models) rather than trusting raw dicts deep in the call stack
- Raise specific exception types and catch narrowly; let unexpected exceptions propagate instead of swallowing them
- Use `is`/`is not` for identity comparisons such as None checks, and `==`/`!=` only for value equality
- Keep functions small with a single clear responsibility, and document the why in docstrings rather than restating the code

## Debugging strategies

- Drop `breakpoint()` into code to enter pdb at that exact line instead of manually importing pdb and calling `set_trace()`
- Use pdb commands (n, s, c, l, p, w) interactively, and `pdb.post_mortem()` to inspect state after an unhandled exception
- Configure the logging module with appropriate levels (DEBUG/INFO/WARNING/ERROR) instead of scattering print statements
- Capture full stack traces with `traceback.print_exc()` or `traceback.format_exc()` when logging caught exceptions
- Use faulthandler (or `python -X faulthandler`) to dump tracebacks on segfaults or hangs in C-extension-heavy code
- Use ipdb for a friendlier interactive debugging session with tab completion and syntax highlighting over stock pdb
- Inspect live object state with `dir()`, `vars()`, and `inspect.signature()` during an interactive debugging session
- Reproduce race conditions and deadlocks with `sys.settrace` or threading-aware logging rather than guessing from symptoms

## Performance and optimization

- Profile before optimizing: use cProfile with pstats, or snakeviz for visualization, to find real hotspots instead of guessing
- Use py-spy to sample a running production process's call stack without adding instrumentation or restarting it
- Reach for the right built-in data structure: set/dict for O(1) membership tests instead of scanning a list
- Prefer a generator over building a full list when a large sequence is only iterated once, to avoid holding it all in memory
- Use `collections.deque` instead of a list for FIFO queues or frequent left-end insertion and removal
- Build strings with `''.join(...)` instead of repeated `+=` concatenation in a loop, since str is immutable and `+=` reallocates
- Move CPU-bound hot loops to vectorized numpy operations or a compiled extension instead of hand-optimizing pure Python
- Memoize expensive, pure function calls with `functools.lru_cache` or `functools.cache`
- Avoid premature optimization: keep code readable until a profiler shows a specific bottleneck actually matters
- Use multiprocessing or `concurrent.futures.ProcessPoolExecutor` for CPU-bound parallelism, since the GIL blocks true thread parallelism for pure-Python CPU work

## Testing approach

- Use pytest as the primary test runner instead of unittest, taking advantage of plain assert statements and test auto-discovery
- Use pytest fixtures for setup and teardown of shared resources, scoping them (function, module, session) to control reuse
- Use `@pytest.mark.parametrize` to run the same test logic across many input/output cases without duplicating test code
- Mock external dependencies such as APIs, databases, or the filesystem with `unittest.mock.Mock`/`MagicMock`/`patch` to isolate the unit under test
- Measure coverage with coverage.py (via pytest-cov) and treat gaps as a signal to investigate, not a target to game
- Use `pytest.raises` as a context manager to assert that specific exceptions are raised under specific conditions
- Use the built-in `tmp_path` fixture for filesystem-touching tests instead of writing to real paths
- Write property-based tests with hypothesis for functions with a large input space instead of enumerating examples by hand
- Mark slow integration tests separately (e.g., `@pytest.mark.integration`) so fast unit tests can run independently in CI

## Code review checklist

- Flag mutable default arguments such as `def f(x=[])`: the default is created once and shared across calls; require `None` with in-function initialization
- Flag bare `except:` clauses that swallow all exceptions including KeyboardInterrupt and SystemExit; require a specific exception type
- Flag `== None` or `!= None` comparisons; require `is None` or `is not None`
- Flag string concatenation with `+=` inside a loop building up a result; require `''.join(...)` or a list accumulator
- Flag modules or packages missing `__all__` when they are designed for wildcard import or as a public package entry point
- Flag mutable objects such as lists or dicts used as class-level attributes that are meant to be per-instance state
- Flag broad `except Exception` blocks that silently discard errors without logging or re-raising
- Flag missing type hints on public function signatures in library code, which weakens static analysis and IDE support
- Flag manual `open()`/`close()` resource handling without a `with` block, which leaks handles on exceptions
- Flag `type(x) == SomeClass` comparisons instead of `isinstance(x, SomeClass)`, which breaks correctly for subclasses

## Documentation style

Write PEP 257-compliant docstrings on every public module, class, and function: a concise imperative
one-line summary, followed by a blank line and a structured Args/Returns/Raises section (Google or
NumPy style) for anything with parameters or non-trivial behavior.
