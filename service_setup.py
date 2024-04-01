from dataclasses import dataclass
import logging
import json


@dataclass
class SetupServiceData:
    logger: logging.Logger
    shared: dict

def _clear_unwanted_characters(s: str) -> str:
    return s.replace('\n', '').replace('\r', '').replace('\t', '').replace('  ', ' ').strip()

def get_token(id_: str):
    with open('data\\tokens.json') as f:
        return _clear_unwanted_characters(json.load(f)[id_])
