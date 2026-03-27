from __future__ import annotations

from typing import Any

from frozendict import frozendict

from treehornx.enum_labels.core.Dir import Down, Internal, Up
from treehornx.enum_labels.core.Event import (
    ERR,
    LOF,
    NOP,
    OOM,
    Event,
    Exit,
    FieldAssignP,
    FieldHere,
    Here,
    Rewind,
    Rewind2,
)
from treehornx.enum_labels.core.Frame import Frame
from treehornx.enum_labels.core.Label import Label


def _dir_to_json(dir_value: Up | Internal | Down) -> dict[str, Any]:
    match dir_value:
        case Up():
            return {"type": "Up"}
        case Internal():
            return {"type": "Internal"}
        case Down(child=child):
            return {"type": "Down", "child": child}


def _dir_from_json(obj: dict[str, Any]) -> Up | Internal | Down:
    match obj["type"]:
        case "Up":
            return Up()
        case "Internal":
            return Internal()
        case "Down":
            return Down(obj["child"])
        case _:
            raise ValueError(f"unknown dir type: {obj['type']}")


def _event_to_json(event: Event) -> dict[str, Any]:
    match event:
        case NOP():
            return {"type": "NOP"}
        case OOM():
            return {"type": "OOM"}
        case ERR():
            return {"type": "ERR"}
        case LOF():
            return {"type": "LOF"}
        case Exit():
            return {"type": "Exit"}
        case FieldAssignP(pfield=pfield, p=p):
            return {"type": "FieldAssignP", "pfield": pfield, "p": p}
        case Here(p=p):
            return {"type": "Here", "p": p}
        case FieldHere(pfield=pfield):
            return {"type": "FieldHere", "pfield": pfield}
        case Rewind(i=i):
            return {"type": "Rewind", "i": i}
        case Rewind2(i=i, p=p):
            return {"type": "Rewind2", "i": i, "p": p}
        case _:
            raise ValueError(f"unsupported event: {event}")


def _event_from_json(obj: dict[str, Any]) -> Event:
    match obj["type"]:
        case "NOP":
            return NOP()
        case "OOM":
            return OOM()
        case "ERR":
            return ERR()
        case "LOF":
            return LOF()
        case "Exit":
            return Exit()
        case "FieldAssignP":
            return FieldAssignP(pfield=obj["pfield"], p=obj["p"])
        case "Here":
            return Here(p=obj["p"])
        case "FieldHere":
            return FieldHere(pfield=obj["pfield"])
        case "Rewind":
            return Rewind(i=obj["i"])
        case "Rewind2":
            return Rewind2(i=obj["i"], p=obj["p"])
        case _:
            raise ValueError(f"unknown event type: {obj['type']}")


def _active_child_to_json(active_child: frozendict[str | int, bool]) -> list[dict[str, Any]]:
    return [{"key": key, "value": value} for key, value in active_child.items()]


def _active_child_from_json(entries: list[dict[str, Any]]) -> frozendict[str | int, bool]:
    return frozendict({entry["key"]: entry["value"] for entry in entries})


def frame_to_json(frame: Frame) -> dict[str, Any]:
    return {
        "index": frame.index,
        "active": frame.active,
        "pc": frame.pc,
        "upd": dict(frame.upd),
        "isnil": dict(frame.isnil),
        "events": [_event_to_json(event) for event in frame.events],
        "active_child": _active_child_to_json(frame.active_child),
        "enum_vars": dict(frame.enum_vars),
        "enum_fields": dict(frame.enum_fields),
        "prev": None
        if frame.prev is None
        else {
            "dir": _dir_to_json(frame.prev[0]),
            "index": frame.prev[1],
        },
    }


def frame_from_json(obj: dict[str, Any]) -> Frame:
    prev_obj = obj["prev"]
    prev = None if prev_obj is None else (_dir_from_json(prev_obj["dir"]), prev_obj["index"])
    return Frame(
        index=obj["index"],
        active=obj["active"],
        pc=obj["pc"],
        upd=frozendict(obj["upd"]),
        isnil=frozendict(obj["isnil"]),
        events=frozenset(_event_from_json(event) for event in obj["events"]),
        active_child=_active_child_from_json(obj["active_child"]),
        enum_vars=frozendict(obj["enum_vars"]),
        enum_fields=frozendict(obj["enum_fields"]),
        prev=prev,
    )


def label_to_json(label: Label) -> dict[str, Any]:
    return {
        "frame": frame_to_json(label.frame),
        "origin": None if label.origin is None else label_to_json(label.origin),
    }


def label_from_json(obj: dict[str, Any]) -> Label:
    origin_obj = obj["origin"]
    origin = None if origin_obj is None else label_from_json(origin_obj)
    return Label(frame=frame_from_json(obj["frame"]), origin=origin)
