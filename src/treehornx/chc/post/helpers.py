from treehornx.enum_labels.core.Event import FieldAssignP, FieldHere, Here
from treehornx.enum_labels.core.Label import Label


def no_assignment_to_field(label: Label, field_name: str) -> bool:
    for frame in iter(label):
        if any(isinstance(e, (FieldAssignP, FieldHere)) and e.pfield == field_name for e in frame.events):
            return False
    return True


def get_last_assignment_to_field(label: Label, field_name: str) -> tuple[str, int] | None:
    for frame in reversed(label):
        for e in frame.events:
            if isinstance(e, FieldAssignP) and e.pfield == field_name and e.p is not None:
                return (e.p, frame.index)
    return None


def last_assignment_to_field(label: Label, field_name: str, ptr_name: str, i: int) -> bool:
    last_ass = get_last_assignment_to_field(label, field_name)
    if last_ass is None:
        return False
    return (ptr_name, i) == last_ass


def ptr_here(label: Label, i: int, ptr_name: str) -> bool:
    frame = label[i]
    return Here(ptr_name) in frame.events
