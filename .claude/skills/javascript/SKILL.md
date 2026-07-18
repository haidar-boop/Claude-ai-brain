---
name: javascript
description: Modern JavaScript (ES2022+) patterns, best practices, debugging, performance, testing, and a code review checklist for browser and Node.js code -- covering React, Vue, Express, Node.js, async/await, and Promises. Use this skill whenever the user is writing, reviewing, or debugging JavaScript (.js/.jsx files), even if they call it "JS" or don't mention the language by name.
---

# JavaScript

Modern JavaScript (ES2022+) for browser and Node.js applications (React, Vue, Express, Node.js,
Next.js, Vite, lodash, axios, date-fns, zod).

## Coding patterns

- Use closures to create private state and factory functions instead of relying on classes for simple encapsulation
- Destructure function parameters with default values, e.g. `function f({ a, b = 1 } = {})`, to make call sites self-documenting
- Use the spread operator to copy or merge arrays/objects immutably (e.g. `{ ...state, key: value }`) rather than mutating in place
- Use rest parameters (`...args`) instead of the `arguments` object for variadic functions, since `arguments` is not a real array and is unavailable in arrow functions
- Prefer async/await over chained `.then()`/`.catch()` for sequential asynchronous logic; reserve raw Promise combinators for `Promise.all`/`Promise.race`/`Promise.allSettled`
- Understand event loop ordering: microtasks (Promise callbacks, `queueMicrotask`) drain completely before the next macrotask (`setTimeout`, `setInterval`, I/O callbacks) runs
- Prefer ES modules (`import`/`export`) over CommonJS (`require`/`module.exports`) in new code; ESM is statically analyzable, enabling tree-shaking, while CommonJS resolves at runtime
- Use optional chaining (`?.`) and nullish coalescing (`??`) to safely access nested properties and supply defaults only for null/undefined, not other falsy values like 0 or ''
- Remember that JavaScript classes are sugar over the prototype chain; instance methods live once on `Class.prototype` and are shared, not copied per instance
- Use generator functions (`function*`) and the iterator protocol for lazy sequences or custom `for...of` iteration behavior

## Best practices

- Declare variables with `const` by default and `let` only when reassignment is required; never use `var`, which is function-scoped and hoisted in bug-prone ways
- Always use strict equality (`===`/`!==`) to avoid implicit type coercion surprises like `'' == 0` or `null == undefined`
- Treat objects and arrays as immutable where practical; return new copies instead of mutating shared state, especially in React/Redux state updates
- Ensure every Promise chain or async function has its rejection handled, via `.catch()` or a try/catch around await, to avoid unhandled rejection crashes
- Run ESLint with a strict config plus Prettier in CI and pre-commit hooks to catch bugs and enforce consistent formatting automatically
- Avoid polluting the global scope; keep browser code inside modules or IIFEs instead of attaching ad hoc properties to `window` or `globalThis`
- Use default parameters (`function f(x = 10)`) instead of manual `x = x || 10` checks, which incorrectly override falsy-but-valid values like 0
- Keep module boundaries explicit with named exports for multi-value modules; reserve default exports for a module's single primary value
- Validate and parse external input, such as API responses and form data, with a schema library like zod rather than trusting shapes implicitly
- Prefer Array.prototype methods (map/filter/reduce/find) over manual for-loops for transformations, dropping back to for/for-of when performance or early exit matters

## Debugging strategies

- Use Chrome DevTools' Sources panel to set breakpoints, conditional breakpoints, and logpoints instead of littering code with console.log
- Insert a `debugger;` statement to pause execution at a precise line whenever DevTools is already attached
- Use `console.table()` for arrays of objects, `console.trace()` to print a call stack, and `console.time()`/`console.timeEnd()` to measure elapsed time for a block
- Run Node with `--inspect` or `--inspect-brk` and attach via `chrome://inspect` for full breakpoint debugging of server-side code
- Enable source maps in the build (`devtool` in webpack, `sourcemap` in Vite/esbuild) so stack traces and breakpoints map back to original TypeScript/JSX, not bundled output
- Attach `process.on('unhandledRejection', ...)` and `process.on('uncaughtException', ...)` handlers in Node during development to surface silently swallowed async errors
- Use the Chrome DevTools Performance tab to record a flame chart and locate long tasks blocking the main thread
- Use the Memory tab's heap snapshot comparison to find detached DOM nodes and growing retained closures that indicate a leak
- Run `node --trace-warnings` to get full stack traces for deprecation and process warnings that are otherwise truncated

## Performance and optimization

- Never run long synchronous loops or heavy computation on the main thread; offload to worker_threads (Node) or Web Workers (browser) to avoid blocking the event loop
- Debounce high-frequency events like input/resize so handling waits until activity stops, and throttle events like scroll so handling is capped to a fixed rate
- Memoize expensive pure functions with an arguments-keyed cache, or use `React.useMemo`/`useCallback` in components, to avoid redundant recomputation
- Guard against memory leaks from closures that capture large objects or DOM references longer than needed, and always remove event listeners and clear intervals/timeouts in cleanup code
- Use dynamic `import()` for code splitting and lazy-load routes or components so the initial bundle only ships what's needed for first paint
- Batch DOM reads and writes separately, avoiding interleaved `offsetHeight` reads with style writes, to prevent layout thrashing
- Use `requestAnimationFrame` for visual and animation updates instead of `setTimeout`/`setInterval` so work aligns with the browser's paint cycle
- Keep object shapes consistent, with the same properties assigned in the same order, so V8 can use stable hidden classes instead of falling back to slower dictionary mode
- Avoid `JSON.parse(JSON.stringify(obj))` for deep cloning in hot paths; use `structuredClone` or a targeted copy function instead

## Testing approach

- Use Jest or Vitest as the primary test runner; Vitest is preferred in Vite-based projects for shared config and faster watch mode
- Mock modules with `jest.mock()`/`vi.mock()` or manual `__mocks__` files to isolate the unit under test from network calls, timers, or file I/O
- Test async code by awaiting the call under test and using resolves/rejects matchers, e.g. `await expect(fn()).rejects.toThrow()`
- With React Testing Library, query elements by role, label, or text as a user would rather than by test-id, and drive interactions through `userEvent`
- Use `jest.useFakeTimers()`/`vi.useFakeTimers()` to deterministically test debounce, throttle, and setTimeout-based logic without real delays
- Use Mock Service Worker (MSW) to intercept network requests at the fetch/XHR level for integration-style tests instead of mocking the HTTP client directly
- Use snapshot tests sparingly, only for stable, human-reviewable output, and avoid snapshotting large or frequently changing structures
- Reset mocks and module state between tests with `beforeEach`/`afterEach` (e.g. `jest.clearAllMocks()`) to prevent state leaking across test cases
- Enforce coverage thresholds with `--coverage` in CI to catch untested branches, especially error-handling paths

## Code review checklist

- Flag `==` or `!=` instead of `===`/`!==`, since loose equality triggers implicit type coercion that hides bugs
- Flag async functions or Promise chains with no `.catch()` and no enclosing try/catch, since unhandled promise rejections crash Node processes and fail silently in browsers
- Flag `var` declarations, since they are function-scoped and hoisted in ways that cause bugs in loops and conditionals that let/const avoid
- Flag functions that mutate their object/array parameters in place instead of returning a new value, since callers may not expect their arguments to change
- Flag React `useEffect`/`useMemo`/`useCallback` hooks with missing or incorrect dependency arrays, which cause stale closures or effects that don't rerun when they should
- Flag "floating" promises, an async call whose result is neither awaited nor explicitly handled, which can cause unpredictable ordering or swallowed errors
- Flag array index used as a React list key when the list can reorder, insert, or delete, since it causes incorrect reconciliation and stale component state
- Flag mixing `require()` and `import` in the same file or inconsistently across a codebase without a clear interop reason
- Flag direct property access on potentially null/undefined values where optional chaining (`?.`) or an explicit guard should be used instead
- Flag deeply nested `.then()` callback chains ("callback hell") that should be flattened with async/await for readability and error handling

## Documentation style

JSDoc comments (`/** ... */`) above functions and classes using `@param`, `@returns`, and `@throws`
tags; types are expressed in JSDoc even in plain JS files so editors and optional checkJs-based
TypeScript checking can use them.
