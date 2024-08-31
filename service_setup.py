from __future__ import annotations
from dataclasses import dataclass
import logging
import json
from enum import Enum, auto
import os
from typing import Iterable

import psycopg2

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


def load_student_db_config(filename='./data/StudentBot/configs/stud_db_config.json') -> dict[str, str]:
    if "useenv" in os.environ and os.environ["useenv"] == "true":
        return json.loads(os.environ["studdbconfig"])
    
    with open(filename, 'r') as file:
        return json.load(file)


def load_schedule_db_config(filename='./data/StudentBot/configs/schedule_db_config.json') -> dict[str, str]:
    if "useenv" in os.environ and os.environ["useenv"] == "true":
        return json.loads(os.environ["scheduledbconfig"])
    
    with open(filename, 'r') as file:
        return json.load(file)


def load_debts_db_config(filename='./data/StudentBot/configs/debts_db_config.json') -> dict[str, str]:
    if "useenv" in os.environ and os.environ["useenv"] == "true":
        return json.loads(os.environ["debtsdbconfig"])

    with open(filename, 'r') as file:
        return json.load(file)
    

def load_material_db_config(filename='./data/StudentBot/configs/materials_db_config.json') -> dict[str, str]:
    if "useenv" in os.environ and os.environ["useenv"] == "true":
        return json.loads(os.environ["materialdbconfig"])
    
    with open(filename, 'r') as file:
        return json.load(file)


def load_groups_db_config(filename='./data/StudentBot/configs/groups_db_config.json') -> dict[str, str]:
    if "useenv" in os.environ and os.environ["useenv"] == "true":
        return json.loads(os.environ["groupsdbconfig"])
    
    with open(filename, 'r') as file:
        return json.load(file)


@dataclass
class Group:
    _id: int
    _group: str
    _morning_day_schedule: bool
    _a_few_days_reminder: bool
    _group_db: GroupsDB

    @property
    def id(self) -> int:
        return self._id
    
    @property
    def group(self) -> str:
        return self._group
    
    @group.setter
    def group(self, new_group: str) -> None:
        self._group_db.cursor.execute(
            "UPDATE groups SET group = %s WHERE id = %s;",
            (new_group, self._id)
        )
        self._group_db.update_db()
        self._group = new_group

    @property
    def morning_day_schedule(self) -> bool:
        return self._morning_day_schedule
    
    @morning_day_schedule.setter
    def morning_day_schedule(self, new_morning_day_schedule: bool) -> None:
        self._group_db.cursor.execute(
            "UPDATE groups SET morning_day_schedule = %s WHERE id = %s;",
            (new_morning_day_schedule, self._id)
        )
        self._group_db.update_db()
        self._morning_day_schedule = new_morning_day_schedule
    
    @property
    def a_few_days_reminder(self) -> bool:
        return self._a_few_days_reminder
    
    @a_few_days_reminder.setter
    def a_few_days_reminder(self, new_a_few_days_reminder: bool) -> None:
        self._group_db.cursor.execute(
            "UPDATE groups SET a_few_days_reminder = %s WHERE id = %s;",
            (new_a_few_days_reminder, self._id)
        )
        self._group_db.update_db()
        self._a_few_days_reminder = new_a_few_days_reminder


class GroupsDB:
    def __init__(self, logger) -> None:
        self.connection = psycopg2.connect(**load_groups_db_config())
        self.cursor = self.connection.cursor()
        self.logger = logger

    def get_group(self, group_id: int) -> Group | None:
        self.cursor.execute("""
            SELECT *
            FROM groups
            WHERE id = %s
        """, (group_id,))

        group_data = self.cursor.fetchone()
        if group_data is None:
            return None

        return Group(*group_data, _group_db=self)
    
    def group_exists(self, group_id) -> bool:
        return self.get_group(group_id) is not None
    
    def update_db(self) -> None:
        self.connection.commit()

    def add_group(self, group_id: str, group_name: str) -> None:
        self.cursor.execute("""
            INSERT INTO groups (id, "group", morning_day_schedule, a_few_days_reminder)
            VALUES (%s, %s, false, false)
        """, (group_id, group_name))

        self.update_db()
        self.logger.info(f"GroupsDB: Added group {group_name} [{group_id}]")

    def get_groups(self, group: str) -> Iterable[Group]:
        self.cursor.execute("""
            SELECT *
            FROM groups
            WHERE "group" = %s
        """, (group,))

        return (
            Group(*group_info, _group_db=self)
            for group_info in self.cursor.fetchall()
        )
    
    def delete_group(self, group_id: int) -> None:
        self.cursor.execute("""
            DELETE FROM groups
            WHERE id = %s
        """, (group_id,))

        self.update_db()

