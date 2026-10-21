from dataclasses import dataclass, field
from itertools import count
from typing import Generic, Iterator, TypeVar


T = TypeVar("T")


@dataclass
class InternedPool(Generic[T]):
    _pool: dict[T, tuple[T, int]] = field(default_factory=dict, init=False)

    def intern(self, item: T) -> T:
        """Return the canonical instance of `item` in the pool, adding it if necessary."""
        if item in self._pool:
            return self._pool[item][0]
        self._pool[item] = item, len(self._pool)
        return item

    def get_id(self, item: T) -> int:
        """Return the unique ID of `item` in the pool, raise if missing."""
        return self._pool[item][1]

    def clear(self) -> None:
        """Clear the pool."""
        self._pool.clear()

    def __iter__(self) -> Iterator[T]:
        """Iterate over the items in the pool."""
        return (item for item, _ in self._pool.values())

    def __len__(self) -> int:
        """Return the number of items in the pool."""
        return len(self._pool)

    def __contains__(self, item: T) -> bool:
        """Return True if `item` is in the pool."""
        return item in self._pool


@dataclass
class InternedPoolView(Generic[T]):
    """A view of an InternedPool that allows iteration and length checking, but not modification."""

    _pool: InternedPool[T]

    def __iter__(self) -> Iterator[T]:
        return self._pool.__iter__()

    def __len__(self) -> int:
        return len(self._pool)

    def __contains__(self, item: T) -> bool:
        return item in self._pool

    def get_id(self, item: T) -> int:
        return self._pool.get_id(item)
