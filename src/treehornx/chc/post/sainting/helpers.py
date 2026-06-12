

from treehornx.chc.post.helpers import no_assignment_to_field
from treehornx.enum_labels.core.Event import FieldAssignP, FieldHere
from treehornx.enum_labels.core.Label import Label


def field_is_nil(lab: Label, j: str) -> bool:
    for frame in reversed(lab):
        if FieldAssignP(j, None) in frame.events:
            return True
        else:
            for event in frame.events:
                if isinstance(event, FieldAssignP) and event.pfield == j:
                    return False
                if event == FieldHere(j):
                    return False
    return False

def missing_child(lab: Label, j: str) -> bool:
    # Version when the free instruction is not allowed
    return field_is_nil(lab, j) or (
        no_assignment_to_field(lab, j) and
        not lab[0].active_child[j]
    )
