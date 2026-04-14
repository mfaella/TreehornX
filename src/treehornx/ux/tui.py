from typing import Callable, override

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, Task, TextColumn, TimeElapsedColumn
from rich.text import Text


console = Console()


def warning(message: str, suppressed: bool = False) -> None:
    if not suppressed:
        console.print(f"[black on yellow]WARNING![/black on yellow] {message}")


def critical(message: str, suppressed: bool = False) -> None:
    if not suppressed:
        console.print(f"[black on #ff8c00]CRITICAL![/black on #ff8c00] {message}")


def info(message: str, suppressed: bool = False) -> None:
    if not suppressed:
        console.print(f"[blue]INFO:[/blue] {message}")


def error(message: str, suppressed: bool = False) -> None:
    if not suppressed:
        console.print(f"[black on red]ERROR![/black on red] {message}")


def fail(message: str, suppressed: bool = False) -> None:
    if not suppressed:
        console.print(f"[red]FAIL![/red] {message}")


def success(message: str, suppressed: bool = False) -> None:
    if not suppressed:
        console.print(f"[green]SUCCESS![/green] {message}")


class GreyTimeElapsedColumn(TimeElapsedColumn):
    @override
    def render(self, task: Task) -> Text:
        text = super().render(task)
        text.stylize("bold dim white")
        return text


def progress[T](description: str, func: Callable[[Console], T]) -> T:
    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"), GreyTimeElapsedColumn(), transient=True
    ) as progress:
        progress.add_task(description=description)
        result = func(progress.console)
    return result
