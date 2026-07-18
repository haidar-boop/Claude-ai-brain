---
name: rust
description: Rust ownership, borrowing, error handling with Result/Option, idiomatic patterns, debugging, performance, testing, and a code review checklist -- covering Tokio, Actix, Axum, serde, and Cargo workflows. Use this skill whenever the user is writing, reviewing, or debugging Rust code, hits a borrow-checker error, or asks about ownership, lifetimes, or Cargo.
---

# Rust

Rust ownership model, safety guarantees, and idiomatic systems programming (Actix, Axum, Tokio,
Rocket, serde, clap, anyhow, thiserror, rayon).

## Coding patterns

- Prefer borrowing (`&T` or `&mut T`) over taking ownership in function signatures, and only consume a value when the function truly needs to own or transform it
- Use the `?` operator to propagate errors through `Result` and `Option` chains instead of manual match/unwrap boilerplate
- Chain `Option`/`Result` combinators such as `map`, `and_then`, `unwrap_or_else`, and `ok_or` to transform values without unwrapping early
- Choose generics with trait bounds (`impl Trait` or `<T: Trait>`) for compile-time monomorphized dispatch, and reach for `dyn Trait` trait objects only when runtime polymorphism or heterogeneous collections are actually required
- Implement the `Drop` trait for RAII cleanup, such as closing file handles or releasing locks, instead of requiring callers to remember an explicit close or cleanup call
- Rely on zero-cost iterator and closure abstractions, chaining `iter`/`filter`/`map`/`collect` rather than hand-rolled index loops, since the compiler optimizes the chain to equivalent machine code
- Reach for interior mutability, `RefCell` for single-threaded state and `Mutex`/`RwLock` for shared state across threads, only where the borrow checker's aliasing rules are genuinely too strict for the design, not as a default
- Write match expressions that are exhaustive over enum variants and let the compiler flag missing arms when a new variant is added, instead of defaulting to a catch-all underscore that silently swallows new cases
- Model illegal states as unrepresentable using enums and newtypes instead of booleans or sentinel values that can be combined incorrectly
- Rely on lifetime elision where the compiler can infer it, and write explicit lifetime annotations only when the relationship between borrowed references genuinely needs to be spelled out

## Best practices

- Run `cargo fmt` and `cargo clippy` with warnings denied in CI to enforce consistent style and catch idiomatic issues beyond what rustc flags on its own
- Prefer thiserror for defining structured library error types and anyhow for application-level error handling where callers do not need to match on specific error variants
- Keep public API surface minimal by defaulting items to private and re-exporting deliberately, rather than marking everything `pub`
- Use the newtype pattern, such as a `Meters` wrapper around `f64`, to add type safety around primitive values instead of passing raw numbers or strings everywhere
- Split larger projects into a Cargo workspace of multiple crates so compile units and dependency graphs stay small, decoupled, and parallelizable
- Favor composition and trait-based interfaces over deep struct hierarchies, since Rust deliberately has no implementation inheritance
- Document safety invariants explicitly with a Safety section on every `unsafe fn`, stating exactly what the caller must uphold for the call to be sound
- Keep `Cargo.toml` dependencies minimal and audit them with `cargo audit` or `cargo deny` to avoid pulling in unmaintained or vulnerable crates
- Prefer `impl Trait` return types over boxed trait objects when the concrete return type is known at compile time, avoiding unnecessary heap allocation and dynamic dispatch
- Use a builder pattern for structs with many optional fields instead of constructors with long positional argument lists

## Debugging strategies

- Sprinkle `dbg!` around an expression for quick inline inspection during development; it prints the file, line, and value, then returns the value so it can stay embedded in an expression
- Set `RUST_BACKTRACE=1`, or `RUST_BACKTRACE=full` for a fully unwound trace, to get a stack trace on panic instead of just the panic message and location
- Use rust-gdb or rust-lldb, thin wrappers around gdb and lldb with Rust-aware pretty-printers, to step through a debug build and inspect enum, Vec, and String internals correctly
- Run `cargo expand` to view the fully macro-expanded source, which is essential for debugging derive macros, procedural macros, or confusing trait resolution
- Use `cargo check` for fast iteration during development, since it runs the borrow checker and type checker without the cost of full code generation
- Read borrow checker errors from the top down; the compiler usually names the exact conflicting borrow and suggests a concrete fix, such as cloning, restructuring the borrow's scope, or using `split_at_mut`
- Use `RUST_LOG` together with the tracing or env_logger crates for leveled, filterable log output instead of scattering println statements through async or multi-threaded code
- Run `cargo miri test` to interpret the MIR and catch undefined behavior, such as out-of-bounds access or invalid aliasing, that a normal debug run will not surface
- Use `cargo tree` to inspect the dependency graph when diagnosing duplicate crate versions or unexpected transitive dependencies

## Performance and optimization

- Avoid unnecessary `.clone()` calls; profile first, then replace hot clones with borrows, `Cow`, or reference-counted types like `Rc`/`Arc` only where sharing genuinely is required
- Build with `cargo build --release` and enable `lto = true` plus `codegen-units = 1` in the release profile for maximum cross-crate inlining, accepting the extra build time
- Profile with `perf record`/`perf report` on Linux, or generate flame graphs directly from a Rust binary with `cargo flamegraph`, to find real hotspots before optimizing anything
- Choose the right collection for the access pattern: Vec for contiguous, index-heavy data, VecDeque for double-ended queues, HashMap/HashSet for average O(1) lookup, and BTreeMap when sorted iteration order matters
- Cut heap allocation by preferring stack arrays or SmallVec for small bounded collections, and by calling `Vec::with_capacity` when the final size is known ahead of time to avoid repeated reallocation
- Prefer iterator adapters over manual indexing loops; bounds checks are often elided in iterator chains in ways that error-prone manual index arithmetic does not get for free
- Reach for rayon's parallel iterators to spread CPU-bound data processing across cores with a small code change from a sequential iterator chain
- Set the release profile's panic strategy to abort when stack unwinding on panic is not needed, to shrink binary size and remove unwind table overhead
- Benchmark with criterion instead of ad hoc timing, since it accounts for statistical noise, warm-up effects, and outliers

## Testing approach

- Write unit tests in a `cfg(test)` `tests` module colocated with the code under test, marking each test function with the test attribute
- Run the suite with `cargo test`, adding `--nocapture` to see println/dbg output and `--test-threads=1` when debugging tests that are not safely parallel
- Put cross-module or end-to-end tests in the top-level `tests` directory, where each file compiles as its own integration-test crate against the public API
- Write runnable doctest examples in doc comments with fenced rust code blocks so documentation examples are compiled and executed by `cargo test`, keeping docs from drifting out of date
- Use proptest or quickcheck for property-based testing to generate a wide range of inputs and automatically shrink failing cases, especially for parsers and data structures
- Assert expected panics with the `should_panic` test attribute rather than manually catching unwinding with `catch_unwind`
- Measure coverage with `cargo llvm-cov` or `cargo tarpaulin` and treat uncovered branches as a prompt to investigate, not a target to chase blindly
- Substitute external dependencies such as databases or network clients behind a trait, then fake or mock that trait with mockall or a hand-written test double, so unit tests avoid real I/O

## Code review checklist

- Flag `unwrap`/`expect` calls on `Result`/`Option` in library code or production request-handling paths; require proper error propagation with the `?` operator or explicit handling instead
- Flag `unsafe` blocks that are not strictly necessary, or that lack a Safety comment justifying exactly which invariants are being upheld
- Flag a bare `let _ = result` that silently discards a `Result`, especially for I/O or lock operations; require the error to be logged, handled, or explicitly acknowledged with a clear justification
- Flag overly broad or redundant explicit lifetime annotations where the elision rules would already produce a correct signature
- Flag blocking calls, such as thread sleep, synchronous filesystem access, or a std `Mutex` held across an `await` point, inside async functions, since they stall the executor thread; require the async equivalent or `spawn_blocking`
- Flag a `.clone()` added reflexively just to silence a borrow checker error, without considering whether restructuring ownership or borrowing would avoid the copy entirely
- Flag non-exhaustive match arms that fall back to a catch-all underscore on an enum the crate itself defines, which hides missing-variant bugs whenever the enum grows a new case
- Flag `Rc<RefCell<T>>` or `Arc<Mutex<T>>` introduced by default rather than as a considered choice; question whether restructuring ownership could avoid shared mutable state entirely
- Flag public functions in library crates that return a boxed `dyn Error` or a stringly-typed error instead of a concrete, matchable error enum
- Flag direct slice/Vec indexing with square brackets in code paths that must not panic on out-of-range input; require the `get` method with explicit handling instead

## Documentation style

Use `///` doc comments on public items, an imperative one-line summary followed by a blank line and
extended explanation, and `//!` comments for module- or crate-level overviews; rustdoc renders both
into HTML docs. Include an Examples section with fenced rust code blocks, since they are compiled
and run as doctests by `cargo test`, and add Panics, Errors, or Safety sections whenever a function
can panic, returns a Result whose failure cases are not obvious, or is unsafe.
