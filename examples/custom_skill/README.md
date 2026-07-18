# Example: an out-of-tree AIForge skill

This is a minimal, installable Python package that adds an "Elixir" skill to
AIForge without touching AIForge's own source tree at all.

## How it works

1. `src/aiforge_skill_elixir/skill.toml` is a normal AIForge skill manifest --
   the same schema as every built-in skill.
2. `src/aiforge_skill_elixir/__init__.py` exposes `load_manifest()`, a
   zero-argument function that parses and returns that manifest.
3. `pyproject.toml` registers `load_manifest` under the `aiforge.skills`
   entry-point group.

## Try it

```bash
pip install -e examples/custom_skill
aiforge skills list --all   # "elixir" now appears
aiforge run "How do I model state in Elixir?" --skill elixir
```

No AIForge core file changed -- this is the exact mechanism AIForge's own
built-in skills use internally, just shipped as a separate installable
package instead of living under `src/aiforge/skills/builtin/`. See
[`docs/skill-creation.md`](../../docs/skill-creation.md) for the full
manifest schema reference.
