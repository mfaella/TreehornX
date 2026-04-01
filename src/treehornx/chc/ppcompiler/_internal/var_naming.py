import re


ID_RE = r"[A-Za-z_][A-Za-z0-9_]*"
TOKEN_PARENT_ID_RE = r"#"
VAR_PARENT_ID_RE = r"\$"
TOKEN_PARENT_RE = rf"^{TOKEN_PARENT_ID_RE}$"
TOKEN_PARENT_STATE_RE = rf"^{TOKEN_PARENT_ID_RE}:({ID_RE})$"
VAR_PARENT_STATE_RE = rf"^\$({ID_RE})\$$"
TOKEN_FIELD_RE = rf"^{TOKEN_PARENT_ID_RE}({ID_RE})$"
VAR_FIELD_RE = rf"^{VAR_PARENT_ID_RE}({ID_RE})$"
TOKEN_FIELD_STATE_RE = rf"^{TOKEN_PARENT_ID_RE}({ID_RE}):({ID_RE})$"
VAR_FIELD_STATE_RE = rf"^{VAR_PARENT_ID_RE}({ID_RE})\$({ID_RE})\$$"
TOKEN_NODE_STATE_RE = rf"^({ID_RE}):({ID_RE})$"
VAR_NODE_STATE_RE = rf"^({ID_RE})\$({ID_RE})\$$"


def make_parent_name() -> str:
    return "$"


def is_parent_name(name: str) -> bool:
    return name == "$"


def make_parent_state_name(state: str) -> str:
    if not re.match(ID_RE, state):
        raise ValueError(f"Invalid parent state name: {state}")
    return f"${state}$"


def is_parent_state_name(name: str) -> bool:
    return bool(re.match(VAR_PARENT_STATE_RE, name))


def get_parent_state_from_name(name: str) -> str:
    match = re.match(VAR_PARENT_STATE_RE, name)
    if not match:
        raise ValueError(f"Name {name} is not a parent state")
    return match.group(1)


def make_field_name(field: str) -> str:
    if not re.match(ID_RE, field):
        raise ValueError(f"Invalid field name: {field}")
    return f"${field}"


def is_field_name(name: str) -> bool:
    return bool(re.match(VAR_FIELD_RE, name))


def get_field_from_name(name: str) -> str:
    match = re.match(TOKEN_FIELD_RE, name)
    if not match:
        raise ValueError(f"Name {name} is not a field token")
    return match.group(1)


def make_field_state_name(field: str, state: str) -> str:
    if not re.match(ID_RE, field):
        raise ValueError(f"Invalid field name: {field}")
    if not re.match(ID_RE, state):
        raise ValueError(f"Invalid field state name: {state}")
    return f"${field}${state}$"


def is_field_state_name(name: str) -> bool:
    return bool(re.match(VAR_FIELD_STATE_RE, name))


def get_field_state_from_name(name: str) -> tuple[str, str]:
    match = re.match(VAR_FIELD_STATE_RE, name)
    if not match:
        raise ValueError(f"Name {name} is not a field state")
    return match.group(1), match.group(2)


def make_node_state_name(node: str, state: str) -> str:
    if not re.match(ID_RE, node):
        raise ValueError(f"Invalid node name: {node}")
    if not re.match(ID_RE, state):
        raise ValueError(f"Invalid node state name: {state}")
    return f"{node}${state}$"


def is_node_state_name(name: str) -> bool:
    return bool(re.match(VAR_NODE_STATE_RE, name))


def get_node_state_from_name(name: str) -> tuple[str, str]:
    match = re.match(VAR_NODE_STATE_RE, name)
    if not match:
        raise ValueError(f"Name {name} is not a node state")
    return match.group(1), match.group(2)
