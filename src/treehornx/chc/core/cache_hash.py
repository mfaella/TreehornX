def cache_hash[C](cls: type[C]) -> type[C]:
    """
    A class decorator that adds caching to the __hash__ method of a class.
    The class must be immutable (frozen) and hashable.
    """

    original_hash = cls.__hash__

    cached_hash = "__cached_hash__"

    annotations = getattr(cls, "__annotations__", {})
    annotations[cached_hash] = int
    setattr(cls, "__annotations__", annotations)

    def caching_hash(self: C) -> int:
        if not hasattr(self, cached_hash):
            object.__setattr__(self, cached_hash, original_hash(self))
        return getattr(self, cached_hash)

    cls.__hash__ = caching_hash
    return cls
