from functools import wraps
from time import perf_counter
from typing import Any, Callable, Literal, Optional


class Timer:
    """
    A versatile timer for measuring execution time.

    Supports:
    - Context manager (with statement)
    - Function decorator (@timer)
    - Multiple time formats: ms, sec, min, hours
    - Auto-format selection based on elapsed time

    Time formats:
        - 'ms': milliseconds
        - 'sec': seconds
        - 'min': minutes
        - 'hours': hours
        - 'auto': automatically select best format
    """

    # Conversion factors to seconds
    TIME_UNITS = {
        "ms": (1000, "ms"),
        "sec": (1, "s"),
        "min": (1 / 60, "min"),
        "hours": (1 / 3600, "h"),
    }

    def __init__(
        self,
        prefix: Optional[str] = None,
        suffix: Optional[str] = None,
        time_format: Literal["ms", "sec", "min", "hours", "auto"] = "auto",
        silent: bool = False,
        decimals: int = 4,
    ) -> None:
        """
        Initialize Timer.

        Args:
            prefix: Text before time output
            suffix: Text after time output
            time_format: Format for time display ('ms', 'sec', 'min', 'hours', or 'auto')
            silent: If True, suppress exceptions
            decimals: Number of decimal places to show
        """
        self.time_format: str = time_format
        self.silent: bool = silent
        self.prefix: str = prefix or "⏱️  Time: "
        self.suffix: str = suffix or "needed."
        self.decimals: int = decimals
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.elapsed: Optional[float] = None

    def _format_time(self, seconds: float) -> str:
        """Convert seconds to the specified format."""
        if self.time_format == "auto":
            # Automatically select best format
            if seconds < 0.001:
                return f"{seconds * 1_000_000:.{self.decimals}f} μs"
            elif seconds < 1:
                return f"{seconds * 1_000:.{self.decimals}f} ms"
            elif seconds < 60:
                return f"{seconds:.{self.decimals}f} s"
            elif seconds < 3600:
                return f"{seconds / 60:.{self.decimals}f} min"
            else:
                return f"{seconds / 3600:.{self.decimals}f} h"

        # Manual format selection
        if self.time_format not in self.TIME_UNITS:
            raise ValueError(
                f"Invalid time_format: {self.time_format}. "
                f"Choose from: {list(self.TIME_UNITS.keys())} or 'auto'"
            )

        factor, unit = self.TIME_UNITS[self.time_format]
        value = seconds * factor
        return f"{value:.{self.decimals}f} {unit}"

    def __enter__(self) -> "Timer":
        """Start timing for context manager."""
        self.start_time = perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Stop timing and display result."""
        self.end_time = perf_counter()
        self.elapsed = self.end_time - self.start_time  # type: ignore[union-attrs]

        formatted_time = self._format_time(self.elapsed)

        # Show error status if exception occurred
        status = ""
        if exc_type is not None:
            status = f" ❌ ({exc_type.__name__})"

        print(f"{self.prefix}{formatted_time} {self.suffix}{status}")
        return self.silent

    def __call__(self, func: Callable) -> Callable[..., Any]:
        """Use as a decorator."""

        @wraps(func)
        def wrapper(*args, **kwargs):
            with Timer(
                prefix=self.prefix,
                suffix=f"{self.suffix} for {func.__name__}()",
                time_format=self.time_format,  # type: ignore[union-attr]
                silent=self.silent,
                decimals=self.decimals,
            ):
                return func(*args, **kwargs)

        return wrapper
