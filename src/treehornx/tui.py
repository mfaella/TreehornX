"""Terminal output of the CLI."""

import time
from typing import Callable, override

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, Task, TextColumn, TimeElapsedColumn
from rich.text import Text

console = Console()


def warning(message: str) -> None:
    console.print(f"[black on yellow]WARNING![/black on yellow] {message}")


def critical(message: str) -> None:
    console.print(f"[black on #ff8c00]CRITICAL![/black on #ff8c00] {message}")


def info(message: str) -> None:
    console.print(f"[blue]INFO:[/blue] {message}")


def error(message: str) -> None:
    console.print(f"[black on red]ERROR![/black on red] {message}")


def fail(message: str) -> None:
    console.print(f"[red]FAIL![/red] {message}")


def success(message: str) -> None:
    console.print(f"[green]SUCCESS![/green] {message}")


class GreyTimeElapsedColumn(TimeElapsedColumn):
    @override
    def render(self, task: Task) -> Text:
        text = super().render(task)
        text.stylize("bold dim white")
        return text


def progress[T](description: str, func: Callable[[], T]) -> tuple[T, float]:
    """Runs `func` behind a spinner, returns its result and the elapsed time in seconds."""
    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), GreyTimeElapsedColumn(), transient=True
    ) as _progress:
        _progress.add_task(description=description)
        start = time.perf_counter()
        result = func()
        elapsed = time.perf_counter() - start
    return result, elapsed
