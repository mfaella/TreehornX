from itertools import islice
from treehornx.enum_labels.core.Event import FieldAssignP, FieldHere, Here
from treehornx.enum_labels.core.Label import Label


def no_assignment_to_field(label: Label, field_name: str) -> bool:
    for frame in iter(label):
        if any(isinstance(e, (FieldAssignP, FieldHere)) and e.pfield == field_name for e in frame.events):
            return False
    return True


def last_assignment_to_field(label: Label, field_name: str, ptr_name: str, i: int) -> bool:
    frame = label[i]
    if FieldAssignP(field_name, ptr_name) not in frame.events:
        return False

    for frame in label[i+1:]:
        if frame.events.intersection([FieldAssignP(field_name, ptr_name), FieldAssignP(field_name, None), FieldHere(field_name)]):
            return False

    return True


def ptr_here(label: Label, i: int, ptr_name: str) -> bool:
    frame = label[i]
    return Here(ptr_name) in frame.events
