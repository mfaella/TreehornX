import json
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import count
from typing import Any, Callable, Iterable, Iterator

from loguru import logger

from .core import Dir, Frame, Label
from .core.Event import Event

# logger.add("labels.log", enqueue=True, level="DEBUG")


# class FrameJsonEncoder(json.JSONEncoder):
#     @override
#     def default(self, o: Any):
#         if isinstance(o, (Event, Dir)):
#             return str(o)
#         if isinstance(o, frozenset):
#             return list(o)
#         return super().default(o)
#
#


@dataclass(slots=True)
class LabelInfo:
    id: int
    ancestors: set[Label] = field(init=False, default_factory=set)
    is_endless_loop_pivot: bool = field(init=False, default=False)


@dataclass
class LabelDB:
    _pool: dict[Label, LabelInfo] = field(default_factory=dict, init=False)
    _origin_index: defaultdict[Label | None, set[Label]] = field(default_factory=lambda: defaultdict(set), init=False)
    _id_index: list[Label] = field(init=False, default_factory=list)
    _id_counter: Callable[[], int] = field(init=False, default_factory=lambda: count().__next__)

    def _save(self, lab: Label):
        if lab not in self._pool:
            lab_id = self._id_counter()
            self._pool[lab] = LabelInfo(lab_id)
            self._origin_index[lab.origin].add(lab)
            self._id_index.append(lab)

    def make(self, origin: Label | None, frame: Frame) -> Label:
        lab = Label(frame, origin)
        self._save(lab)
        return lab

    def add(self, lab: Label):
        self._save(lab)

    def id(self, lab: Label) -> int:
        return self._pool[lab].id

    def find_by_id(self, lab_id: int) -> Label:
        return self._id_index[lab_id]

    def ancestors(self, lab: Label) -> Iterable[Label]:
        return self._pool[lab].ancestors

    def add_ancestor(self, lab: Label, ancestor: Label):
        self._pool[lab].ancestors.add(ancestor)

    def set_endless_loop_pivot(self, lab: Label, is_pivot: bool = True):
        self._pool[lab].is_endless_loop_pivot = is_pivot

    def is_endless_loop_pivot(self, lab: Label) -> bool:
        return self._pool[lab].is_endless_loop_pivot

    def __iter__(self) -> Iterator[Label]:
        return (lab for lab in self._pool)

    def __in__(self, lab: Label) -> bool:
        return lab in self._pool

    def __len__(self) -> int:
        return len(self._pool)

    def find_by_origin(self, origin: Label) -> Iterable[Label]:
        return self._origin_index[origin]


# class LabelDB:
#     def __init__(self):
#         self.db: set[Label] = set()
#         self.origin_index: defaultdict[Label | None, set[Label]] = defaultdict(set)
#         self.ancestors_index: defaultdict[Label, set[Label]] = defaultdict(set)

#     def add(self, label: Label):
#         self.db.add(label)
#         self.origin_index[label.origin].add(label)
#         # with open("labels.log", "a") as labels_file:
#         #     jsonlabel = {
#         #         "id": label.id,
#         #         "origin_id": label.origin.id if label.origin else None,
#         #         "frames": list(f.__dict__ for f in label.iter()),
#         #     }
#         #     json_label_str = json.dumps(jsonlabel, indent=2, cls=FrameJsonEncoder)
#         #     labels_file.write(json_label_str + "\n")

#     def add_ancestor(self, label: Label, ancestor: Label):
#         self.ancestors_index[label].add(ancestor)

#     def find_ancestors(self, label: Label) -> Iterable[Label]:
#         return self.ancestors_index.get(label, set())

#     def find_by_origin(self, origin: Label) -> Iterable[Label]:
#         if origin not in self.db:
#             raise KeyError(f"Origin label {origin.id} not found in LabelDB.")
#         return self.origin_index[origin]

#     def labels(self) -> Iterable[Label]:
#         return self.db

#     def dump(self, stream: TextIO):
#         labels = list(
#             {
#                 "id": label.id,
#                 "origin_id": label.origin.id if label.origin else None,
#                 "frames": list(f.__dict__ for f in label.iter()),
#             }
#             for label in self.db
#         )

#         json.dump(labels, stream, indent=2, cls=FrameJsonEncoder)
