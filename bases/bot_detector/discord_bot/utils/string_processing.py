import random
import re
import string


def is_valid_rsn(rsn: str) -> bool:
    return re.fullmatch(r"[\w\d _-]{1,12}", rsn) is not None


def get_random_id(size: int = 4, chars: str = string.digits) -> str:
    return "".join(random.choice(chars) for _ in range(size))


def plus_minus(var, compare):
    diff_control = "-"
    if isinstance(var, float) and var > compare:
        diff_control = "+"

    if isinstance(var, str) and var == str(compare):
        diff_control = "+"

    return diff_control


def to_jagex_name(name: str) -> str:
    return name.lower().replace("_", " ").replace("-", " ").strip()
