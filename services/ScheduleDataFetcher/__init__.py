import asyncio
import json
import os
from service_setup import SetupServiceData, load_schedule_db_config
from time import perf_counter
from typing import Iterator
from google.oauth2 import service_account
from google.auth.transport.requests import Request
import psycopg2
import httpx


LINE = tuple[str, str, str, str, str, str]


def parse_line(line: list[str], current_day_of_week: list[str], week=1) -> LINE | None:
    if len(line) == 1:
        if line[0]:
            current_day_of_week[0] = line[0]
    if len(line) != 5:
        return

    possible_day_of_week, time, subject, class_type, url = line
    if not time or not subject or not class_type or not url:
        return

    if possible_day_of_week:
        current_day_of_week[0] = possible_day_of_week

    return current_day_of_week[0], time, subject, class_type, week, url


def parse_range(data: list[list[str]], week=1) -> Iterator[LINE]:
    current_day_of_week = [""]

    for line in data:
        line: list[str]

        parsed_line = parse_line(line, current_day_of_week, week)

        if parsed_line is not None:
            yield parsed_line


class ScheduleDataFetcherService:
    def __init__(self, setup_data: SetupServiceData) -> None:
        self.setup_data = setup_data

        self.setup_google_api_connection()
        self.setup_db_connection()

    def setup_google_api_connection(self) -> None:
        self.spreadsheet_id = "1gsxm1onrT76UYZxuT7b-qyO-haWiWk7igKwvSB0LLbg"
        scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"]
        self.load_creds(scopes)

        self.url = f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}/values:batchGet"
        self.params = {
            "ranges": [
                "KM31!A3:E32", "KM31!G3:K32",
                "KM32!A3:E32", "KM32!G3:K32",
                "KM33!A3:E32", "KM33!G3:K32",
            ]
        }
        self.headers = {
            "Authorization": f"Bearer {self.credentials.token}"
        }

    def load_creds(self, scopes) -> None:
        if "useenv" in os.environ and os.environ["useenv"] == "true":
            self.credentials = \
                service_account.Credentials.from_service_account_info(json.loads(os.environ["schedulefileapicreds"]), scopes=scopes)
        else:
            self.credentials = \
                service_account.Credentials.from_service_account_file("./data/StudentBot/configs/schedule_file_api_creds.json", scopes=scopes)

        self.credentials.refresh(Request())
     
    # TODO confidential data 
    def setup_db_connection(self) -> None:
        self.db_connection = psycopg2.connect(
            **load_schedule_db_config()
        )

        self.db_cursor = self.db_connection.cursor()

    async def run(self) -> None:
        self.setup_data.logger.info("Data fetcher service: Starting")
        
        try:
            while True:
                await self.mainloop()
        except Exception as e:
            self.setup_data.logger.exception(f"Data fetcher service: {e}")

    async def mainloop(self) -> None:
        time_before_parsing = perf_counter()

        self.db_cursor.execute("DELETE FROM km31")
        self.db_cursor.execute("DELETE FROM km32")
        self.db_cursor.execute("DELETE FROM km33")
        
        self.setup_data.logger.info("Data fetcher service: Fetching data")
        info = await self.fetch_data()
        self.setup_data.logger.info("Data fetcher service: Parsing data")
        self.parse_to_db(info)
        self.db_connection.commit()

        self.setup_data.logger.info(f"Data fetcher service: Done in {perf_counter()-time_before_parsing:.2f}seconds")

        await asyncio.sleep(2*60)

    def parse_to_db(self, info) -> None:
        for group_number, group in enumerate(("km31", "km32", "km33")):
            for week in (1, 2):
                batch_id = group_number*2 + week-1
                data = info["valueRanges"][batch_id]["values"]

                for line in parse_range(data, week=week):
                    self.insert_data(group, line)

    def insert_data(self, group: str, line: LINE) -> None:
        query = f"""
        INSERT INTO {group} (day_of_week, time, subject, class_type, week, url)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        self.db_cursor.execute(query, line)
        pass

    async def fetch_data(self):
        async with httpx.AsyncClient() as client:
            response = await client.get(self.url, params=self.params, headers=self.headers)
            data = response.json()

            return data
