"""The ``aiforge`` command-line interface.

Each subcommand handler imports what it needs lazily, so a lightweight
invocation like ``aiforge --version`` never imports the engine, providers,
or skill system.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import sys
from collections.abc import Sequence
from typing import TYPE_CHECKING

from aiforge.__about__ import __version__

if TYPE_CHECKING:
    from aiforge.skills.registry import SkillRegistry

__all__ = ["main"]


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``aiforge`` console script. Returns the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 1
    try:
        return int(handler(args))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aiforge", description="AIForge: a modular AI coding framework."
    )
    parser.add_argument("--version", action="version", version=f"aiforge {__version__}")
    parser.add_argument(
        "--config",
        default=None,
        help="Path to aiforge.toml (default: ./aiforge.toml or $AIFORGE_CONFIG)",
    )
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run a prompt through the engine.")
    run_parser.add_argument("prompt", help="The prompt to send.")
    run_parser.add_argument("--provider", help="Override the provider to use.")
    run_parser.add_argument("--model", help="Override the model to use.")
    run_parser.add_argument(
        "--skill",
        action="append",
        dest="skills",
        default=[],
        help="Explicit skill name (repeatable).",
    )
    run_parser.add_argument("--system", help="Additional system prompt text.")
    run_parser.add_argument("--max-tokens", type=int, default=None, help="Max output tokens.")
    run_parser.add_argument(
        "--stream", action="store_true", help="Stream the response incrementally."
    )
    run_parser.set_defaults(handler=_cmd_run)

    skills_parser = subparsers.add_parser("skills", help="Inspect the skill registry.")
    skills_subparsers = skills_parser.add_subparsers(dest="skills_command")
    skills_list_parser = skills_subparsers.add_parser("list", help="List skills.")
    skills_list_parser.add_argument("--all", action="store_true", help="Include disabled skills.")
    skills_list_parser.set_defaults(handler=_cmd_skills_list)
    skills_show_parser = skills_subparsers.add_parser("show", help="Show a skill's full manifest.")
    skills_show_parser.add_argument("name")
    skills_show_parser.set_defaults(handler=_cmd_skills_show)

    providers_parser = subparsers.add_parser("providers", help="Inspect registered providers.")
    providers_subparsers = providers_parser.add_subparsers(dest="providers_command")
    providers_list_parser = providers_subparsers.add_parser("list", help="List providers.")
    providers_list_parser.set_defaults(handler=_cmd_providers_list)

    config_parser = subparsers.add_parser("config", help="Inspect configuration.")
    config_subparsers = config_parser.add_subparsers(dest="config_command")
    config_show_parser = config_subparsers.add_parser(
        "show", help="Print the merged configuration."
    )
    config_show_parser.set_defaults(handler=_cmd_config_show)
    config_path_parser = config_subparsers.add_parser(
        "path", help="Print the config file path in use."
    )
    config_path_parser.set_defaults(handler=_cmd_config_path)

    serve_parser = subparsers.add_parser("serve", help="Run the optional HTTP JSON API.")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8420)
    serve_parser.set_defaults(handler=_cmd_serve)

    version_parser = subparsers.add_parser("version", help="Print the version.")
    version_parser.set_defaults(handler=_cmd_version)

    return parser


def _cmd_run(args: argparse.Namespace) -> int:
    from aiforge.api.client import AIForge

    forge = AIForge(config_path=args.config)
    if args.stream:
        for chunk in forge.stream(
            args.prompt,
            provider=args.provider,
            model=args.model,
            skills=args.skills,
            system=args.system,
            max_tokens=args.max_tokens,
        ):
            print(chunk.text, end="", flush=True)
        print()
        return 0
    result = forge.run_detailed(
        args.prompt,
        provider=args.provider,
        model=args.model,
        skills=args.skills,
        system=args.system,
        max_tokens=args.max_tokens,
    )
    response = result.response
    print(response.text)
    if response.cost_usd is not None:
        print(
            f"\n[{result.context.provider_name}/{response.model}] "
            f"cost: ${response.cost_usd:.4f}  tokens: {response.usage.total_tokens}",
            file=sys.stderr,
        )
    return 0


def _cmd_skills_list(args: argparse.Namespace) -> int:
    registry = _build_skill_registry(args.config)
    names = registry.names() if args.all else registry.names(enabled_only=True)
    for name in names:
        manifest = registry.require(name)
        marker = "" if manifest.enabled else " (disabled)"
        print(f"{name}{marker}: {manifest.description}")
    return 0


def _cmd_skills_show(args: argparse.Namespace) -> int:
    registry = _build_skill_registry(args.config)
    print(registry.require(args.name).prompt_guidance())
    return 0


def _build_skill_registry(config_path: str | None) -> SkillRegistry:
    from aiforge.config.loader import load_config
    from aiforge.skills.loader import discover_skills
    from aiforge.skills.registry import SkillRegistry

    config = load_config(project_path=config_path)
    registry = SkillRegistry()
    registry.register_all(discover_skills(extra_dirs=config.skills.extra_dirs))
    registry.apply_policy(enabled=config.skills.enabled, disabled=config.skills.disabled)
    return registry


def _cmd_providers_list(args: argparse.Namespace) -> int:
    from aiforge.providers.registry import ProviderRegistry

    registry = ProviderRegistry()
    registry.discover_entry_points()
    for name in registry.names():
        print(name)
    return 0


def _cmd_config_show(args: argparse.Namespace) -> int:
    from aiforge.config.loader import load_config
    from aiforge.utils.serialization import dumps

    config = load_config(project_path=args.config)
    print(dumps(dataclasses.asdict(config), sort_keys=True))
    return 0


def _cmd_config_path(args: argparse.Namespace) -> int:
    from aiforge.config.loader import DEFAULT_CONFIG_PATH

    path = args.config or os.environ.get("AIFORGE_CONFIG") or str(DEFAULT_CONFIG_PATH)
    print(path)
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from aiforge.server.app import serve

    serve(host=args.host, port=args.port)
    return 0


def _cmd_version(args: argparse.Namespace) -> int:
    print(__version__)
    return 0
