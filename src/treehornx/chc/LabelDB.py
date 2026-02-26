import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, TextIO, override

from loguru import logger

from .core import Dir, Label
from .core.event import ERR, LOF, NOP, OOM, Event, Exit, FieldAssignP, Here, Rewind, Rewind2

# logger.add("labels.log", enqueue=True, level="DEBUG")


class FrameJsonEncoder(json.JSONEncoder):
    @override
    def default(self, o: Any):
        if isinstance(o, (Event, Dir)):
            return str(o)
        return super().default(o)


class LabelDB:
    def __init__(self):
        self.db: set[Label] = set()
        self.origin_index: defaultdict[Label | None, set[Label]] = defaultdict(set)

    def add(self, label: Label):
        self.db.add(label)
        self.origin_index[label.origin].add(label)
        # with open("labels.log", "a") as labels_file:
        #     jsonlabel = {
        #         "id": label.id,
        #         "origin_id": label.origin.id if label.origin else None,
        #         "frames": list(f.__dict__ for f in label.iter()),
        #     }
        #     json_label_str = json.dumps(jsonlabel, indent=2, cls=FrameJsonEncoder)
        #     labels_file.write(json_label_str + "\n")

    def find_by_origin(self, origin: Label) -> Iterable[Label]:
        if origin not in self.db:
            raise KeyError(f"Origin label {origin.id} not found in LabelDB.")
        return self.origin_index[origin]

    def dump(self, stream: TextIO):
        labels = list(
            {
                "id": label.id,
                "origin_id": label.origin.id if label.origin else None,
                "frames": list(f.__dict__ for f in label.iter()),
            }
            for label in self.db
        )

        json.dump(labels, stream, indent=2, cls=FrameJsonEncoder)
