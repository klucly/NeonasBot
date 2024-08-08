from dataclasses import dataclass
import logging
import json
from enum import Enum, auto
import os

class GlobalEvents(Enum):
    Exit = auto()


@dataclass
class SetupServiceData:
    logger: logging.Logger
    shared: dict

def _clear_unwanted_characters(s: str) -> str:
    return s.replace('\n', '').replace('\r', '').replace('\t', '').replace('  ', ' ').strip()

def get_token(id_: str):
    if "useenv" in os.environ and os.environ["useenv"] == "true":
        return _clear_unwanted_characters(json.loads(os.environ["botstokens"])[id_])
    
    with open('data\\tokens.json') as f:
        return _clear_unwanted_characters(json.load(f)[id_])


def load_student_db_config(filename='./data/StudentBot/stud_db_config.json') -> dict[str, str]:
    if "useenv" in os.environ and os.environ["useenv"] == "true":
        return json.loads(os.environ["studdbconfig"])
    
    with open(filename, 'r') as file:
        return json.load(file)


def load_schedule_db_config(filename='./data/StudentBot/schedule_db_config.json') -> dict[str, str]:
    if "useenv" in os.environ and os.environ["useenv"] == "true":
        return json.loads(os.environ["scheduledbconfig"])
    
    with open(filename, 'r') as file:
        return json.load(file)
