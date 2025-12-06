from unittest import TestCase

from chc.Event import NOP
from chc.Frame import Frame
from chc.Label import Label
from frozendict import frozendict


class TestLabel(TestCase):
    def test_label_creation(self):
        frame = Frame(
            index=0,
            active=True,
            pc=0,
            upd_set=frozenset(),
            isnil_set=frozenset(),
            event=NOP(),
            active_child_set=frozenset(),
            enum_values=frozendict(),
            prev=None,
        )
        label1 = Label.make(None, frame)
        label2 = Label.make(None, frame)
        self.assertIs(label1, label2)  # Cached instances should be the same
