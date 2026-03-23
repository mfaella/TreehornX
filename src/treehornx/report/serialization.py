import json
import pickle

from treehornx.enum_labels.LabelDB import LabelDB
from treehornx.enum_labels.PairDB import PairDB
from treehornx.report.format import (
    label_from_light_json,
    label_to_light_json,
    pair_from_light_json,
    pair_to_light_json,
)


def serialize(file_path: str, labels: LabelDB, pairs: PairDB):
    pickle_object = {"labels": labels, "pairs": pairs}
    with open(file_path, "wb") as f:
        pickle.dump(pickle_object, f)
    # json_object = {"labels": [], "pairs": [], "ancestors": []}
    # for label in labels:
    #     label_id = labels.id(label)
    #     json_label = {"id": label_id, "label": label_to_light_json(label, labels)}
    #     json_object["labels"].append(json_label)
    #     for ancestor in labels.ancestors(label):
    #         ancestor_id = labels.id(ancestor)
    #         json_object["ancestors"].append({"label_id": label_id, "ancestor_id": ancestor_id})
    # for pair in pairs:
    #     json_pair = pair_to_light_json(pair, labels)
    #     json_object["pairs"].append(json_pair)

    # with open(file_path, "w") as f:
    #     json.dump(json_object, f, indent=2)


def deserialize(file_path: str) -> tuple[LabelDB, PairDB]:
    # with open(file_path, "r") as f:
    #     json_object = json.load(f)

    # labels = LabelDB()
    # json_object["labels"].sort(key=lambda x: x["id"])
    # for json_label in json_object["labels"]:
    #     label = label_from_light_json(json_label["label"], labels)
    #     labels.add(label)

    # for json_ancestor in json_object["ancestors"]:
    #     label_id = json_ancestor["label_id"]
    #     ancestor_id = json_ancestor["ancestor_id"]
    #     labels.add_ancestor(labels.find_by_id(label_id), labels.find_by_id(ancestor_id))

    # pairs = PairDB()
    # for json_pair in json_object["pairs"]:
    #     pair = pair_from_light_json(json_pair, labels)
    #     pairs.add(pair)
    #
    with open(file_path, "rb") as f:
        pickle_object = pickle.load(f)
        labels = pickle_object["labels"]
        pairs = pickle_object["pairs"]

    return labels, pairs
