from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import Sequence

import click
import typer
from rich.console import Console
from rich.table import Table

from .config import load_config
from .connect import connect_command
from .detect import detect_all
from .paths import AgentName, agent_display_name
from .register import default_agent_name, register_command

console = Console()


def setup_command(platform_url: str | None = None) -> None:
    config = load_config()
    if not config or not config.get("api_token"):
        console.print()
        console.print("  [bold]Step 1:[/bold] Sign in to AgentNet")
        register_command(
            platform_url=platform_url,
            auto_agent_name=default_agent_name(),
            auto_visibility="private",
        )
    else:
        console.print()
        console.print("  [green]✓[/green] Already signed in to AgentNet")

    console.print("  [bold]Step 2:[/bold] Detect local agents")
    results = detect_all()
    _print_detected_agents(results)

    targets = _available_targets(results)
    if not targets:
        console.print("\n  [dim]All detected agents are already configured.[/dim]\n")
        return

    console.print()
    console.print(
        f"  [bold]Step 3:[/bold] Choose agents to configure "
        f"([green]all recommended[/green], {len(targets)} available)"
    )
    selected, connect_all = _select_targets(targets)
    if not selected:
        console.print("\n  [dim]No agents configured.[/dim]\n")
        return

    if connect_all:
        connect_command(connect_all=True)
        return

    for agent_name in selected:
        connect_command(agent_name=agent_name)


def _available_targets(results) -> list[str]:
    return [r.agent_name for r in results if r.detected and not r.already_connected]


def _select_targets(targets: list[str]) -> tuple[list[str], bool]:
    mode = _radio_menu(
        "How would you like to set up AgentNet?",
        (
            "Configure all detected agents (recommended)",
            "Choose agents individually",
            "Skip agent configuration",
        ),
        default=0,
    )

    if mode == 0:
        return targets, True
    if mode == 2:
        return [], False

    labels = [agent_display_name(AgentName(agent_name)) for agent_name in targets]
    selected_indexes = _multi_select_menu(
        "Which agents should AgentNet configure?",
        labels,
        default_selected=range(0),
    )
    return [targets[idx] for idx in selected_indexes], False


def _radio_menu(question: str, options: Sequence[str], *, default: int = 0) -> int:
    if not _use_terminal_menu():
        _print_radio_snapshot(question, options, default)
        try:
            choice = typer.prompt(f"  Select [1-{len(options)}]", default=str(default + 1)).strip()
        except click.Abort:
            console.print()
            return default
        return _parse_menu_choice(choice, len(options), default=default)

    selected = default
    with _raw_terminal():
        with _hidden_cursor():
            rendered_lines = 0
            while True:
                rendered_lines = _draw_menu(_radio_lines(question, options, selected), rendered_lines)
                key = _read_key()
                if key == "up":
                    selected = (selected - 1) % len(options)
                elif key == "down":
                    selected = (selected + 1) % len(options)
                elif key == "enter":
                    return selected
                elif key.isdigit() and 1 <= int(key) <= len(options):
                    return int(key) - 1
                elif key == "ctrl_c":
                    raise KeyboardInterrupt


def _multi_select_menu(
    question: str,
    options: Sequence[str],
    *,
    default_selected: range,
) -> list[int]:
    if not _use_terminal_menu():
        _print_multi_snapshot(question, options, set(default_selected), 0)
        try:
            choice = typer.prompt(f"  Select agents [1-{len(options)}]", default="none").strip().lower()
        except click.Abort:
            console.print()
            return [idx for idx in default_selected]
        return _parse_multi_choice(choice, len(options), default_selected=set(default_selected))

    cursor = 0
    checked = set(default_selected)
    explicit_none = False
    with _raw_terminal():
        with _hidden_cursor():
            rendered_lines = 0
            while True:
                rendered_lines = _draw_menu(_multi_lines(question, options, checked, cursor), rendered_lines)
                key = _read_key()
                if key == "up":
                    cursor = (cursor - 1) % len(options)
                elif key == "down":
                    cursor = (cursor + 1) % len(options)
                elif key == "space":
                    if cursor in checked:
                        checked.remove(cursor)
                    else:
                        checked.add(cursor)
                    explicit_none = False
                elif key == "enter":
                    return _finalize_multi_selection(
                        checked,
                        option_count=len(options),
                        cursor=cursor,
                        explicit_none=explicit_none,
                    )
                elif key == "a":
                    checked = set(range(len(options)))
                    explicit_none = False
                elif key == "n":
                    checked = set()
                    explicit_none = True
                elif key.isdigit() and 1 <= int(key) <= len(options):
                    idx = int(key) - 1
                    if idx in checked:
                        checked.remove(idx)
                    else:
                        checked.add(idx)
                    explicit_none = False
                elif key == "ctrl_c":
                    raise KeyboardInterrupt


def _print_radio_snapshot(question: str, options: Sequence[str], selected: int) -> None:
    console.print()
    console.print(f"  [bold]{question}[/bold]")
    for idx, option in enumerate(options):
        marker = "[green]●[/green]" if idx == selected else "[dim]○[/dim]"
        console.print(f"  {marker} {option}")


def _print_multi_snapshot(
    question: str,
    options: Sequence[str],
    checked: set[int],
    cursor: int,
) -> None:
    console.print()
    console.print(f"  [bold]{question}[/bold]")
    console.print("  [dim]Enter numbers like 1,3, type all to select all, or press Enter to skip.[/dim]")
    for idx, option in enumerate(options):
        marker = "[bold]>[/bold]" if idx == cursor else " "
        box = "[x]" if idx in checked else "[ ]"
        console.print(f"  {marker} {box} {idx + 1}. {option}")


def _radio_lines(question: str, options: Sequence[str], selected: int) -> list[str]:
    lines = [f"  {_ansi_bold(question)}", ""]
    for idx, option in enumerate(options):
        marker = _ansi_green("●") if idx == selected else _ansi_dim("○")
        lines.append(f"  {marker} {option}")
    lines.append("")
    lines.append(_ansi_dim(f"  Select [1-{len(options)}] ({selected + 1}):"))
    lines.append(_ansi_dim("  Use ↑/↓ to move, Enter to select, or type a number."))
    return lines


def _multi_lines(
    question: str,
    options: Sequence[str],
    checked: set[int],
    cursor: int,
) -> list[str]:
    lines = [f"  {_ansi_bold(question)}", ""]
    for idx, option in enumerate(options):
        marker = ">" if idx == cursor else " "
        box = "[x]" if idx in checked else "[ ]"
        lines.append(f"  {marker} {box} {idx + 1}. {option}")
    lines.append("")
    lines.append(_ansi_dim("  Use ↑/↓ to move, Space to toggle, Enter to confirm."))
    lines.append(_ansi_dim("  Type a number to toggle it. Press a for all, n for none."))
    return lines


def _draw_menu(lines: Sequence[str], previous_line_count: int) -> int:
    if previous_line_count:
        sys.stdout.write(f"\033[{previous_line_count}F\r")
    for line in lines:
        sys.stdout.write(f"\r\033[2K{line}\r\n")
    sys.stdout.flush()
    return len(lines)


def _ansi_bold(text: str) -> str:
    return f"\033[1m{text}\033[0m"


def _ansi_dim(text: str) -> str:
    return f"\033[2m{text}\033[0m"


def _ansi_green(text: str) -> str:
    return f"\033[32m{text}\033[0m"


def _parse_menu_choice(choice: str, option_count: int, *, default: int) -> int:
    if not choice:
        return default
    try:
        selected = int(choice)
    except ValueError:
        console.print(f"  [yellow]![/yellow] Invalid selection, using {default + 1}.")
        return default
    if selected < 1 or selected > option_count:
        console.print(f"  [yellow]![/yellow] Out-of-range selection, using {default + 1}.")
        return default
    return selected - 1


def _parse_multi_choice(choice: str, option_count: int, *, default_selected: set[int]) -> list[int]:
    if choice in ("all", "a"):
        return list(range(option_count))
    if choice in ("", "none", "no", "n", "skip"):
        return []

    selected: list[int] = []
    for part in choice.replace(" ", "").split(","):
        if not part:
            continue
        try:
            idx = int(part)
        except ValueError:
            console.print(f"  [yellow]![/yellow] Ignoring invalid selection: {part}")
            continue
        if idx < 1 or idx > option_count:
            console.print(f"  [yellow]![/yellow] Ignoring out-of-range selection: {idx}")
            continue
        zero_based = idx - 1
        if zero_based not in selected:
            selected.append(zero_based)

    return selected or [idx for idx in range(option_count) if idx in default_selected]


def _finalize_multi_selection(
    checked: set[int],
    *,
    option_count: int,
    cursor: int,
    explicit_none: bool,
) -> list[int]:
    if checked:
        return [idx for idx in range(option_count) if idx in checked]
    if explicit_none:
        return []
    return [cursor]


def _use_terminal_menu() -> bool:
    return console.is_terminal and sys.stdin.isatty() and sys.stdout.isatty()


def _read_key() -> str:
    if os.name == "nt":
        import msvcrt

        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            code = msvcrt.getwch()
            return {"H": "up", "P": "down"}.get(code, "")
        if ch == "\r":
            return "enter"
        if ch == " ":
            return "space"
        if ch == "\x03":
            return "ctrl_c"
        return ch.lower()

    ch = sys.stdin.read(1)
    if ch == "\x1b":
        seq = sys.stdin.read(2)
        return {"[A": "up", "[B": "down"}.get(seq, "")
    if ch in ("\r", "\n"):
        return "enter"
    if ch == " ":
        return "space"
    if ch == "\x03":
        return "ctrl_c"
    return ch.lower()


@contextmanager
def _raw_terminal():
    if os.name == "nt":
        yield
        return

    import termios
    import tty

    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original)


@contextmanager
def _hidden_cursor():
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()
    try:
        yield
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()


def _print_detected_agents(results) -> None:
    table = Table(
        box=None,
        pad_edge=False,
        show_edge=False,
        padding=(0, 2),
        show_header=True,
        header_style="bold dim",
    )
    table.add_column("Agent", min_width=18)
    table.add_column("Status", min_width=14)
    table.add_column("Setup")

    for result in results:
        display = agent_display_name(AgentName(result.agent_name))
        if result.already_connected:
            setup = "[green]configured[/green]"
        elif result.detected:
            setup = "[cyan]will configure[/cyan]"
        else:
            setup = "[dim]skipped[/dim]"
        status = "[green]detected[/green]" if result.detected else "[dim]not found[/dim]"
        table.add_row(display, status, setup)

    console.print()
    console.print(table)
