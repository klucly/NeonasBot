import asyncio
import json
import os
from service_setup import SetupServiceData, load_material_db_config
from time import perf_counter
from typing import Iterator
from google.oauth2 import service_account
from google.auth.transport.requests import Request
import psycopg2
import httpx
from typing import Optional, Tuple


LINE = Tuple[Optional[str], Optional[str]]


def parse_line(line: list[str]) -> LINE | None:
    
    material_name = None
    url = None

    if len(line) > 0:
        material_name = line[0]

    if len(line) > 1:
        url = line[1]

    return material_name, url


def parse_range(data) -> Iterator[LINE]:

    for line in data:
        line: list[str]

        parsed_line = parse_line(line)

        if parsed_line is not None:
            yield parsed_line


class MaterialsDataFetcherService:
    def __init__(self, setup_data: SetupServiceData) -> None:
        self.setup_data = setup_data

        self.setup_google_api_connection()
        self.setup_db_connection()


    def setup_google_api_connection(self):
        self.spreadsheet_id = "1bfFIgVgv-dDK0HOcMw1qr861vWI8IXJyTEzcDGYMDDc"

        scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"]
        self.load_creds(scopes)

        self.url = f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}/values:batchGet"
        self.params = {
            "ranges" : [
                "KM31!B3:C15",
                "KM32!B3:C15",
                "KM33!B3:C15"
            ]
        }
        self.headers = {
            "Authorization": f"Bearer {self.credentials.token}"
        }

    def load_creds(self, scopes):
        if "useenv" in os.environ and os.environ["useenv"] == "true":
            self.credentials = \
                service_account.Credentials.from_service_account_info(json.loads(os.environ["googleapicreds"]), scopes=scopes)
        else:
            self.credentials = \
                service_account.Credentials.from_service_account_file("./data/StudentBot/configs/google_api_creds.json", scopes=scopes)

        self.credentials.refresh(Request())

    def setup_db_connection(self) -> None:
        self.db_connection = psycopg2.connect(
            **load_material_db_config()
        )

        self.db_cursor = self.db_connection.cursor()

    async def run(self) -> None:
        self.setup_data.logger.info("Materials data fetcher service: Starting")
        
        try:
            while True:
                await self.mainloop()
        except Exception as e:
            self.setup_data.logger.exception(f"Materials data fetcher service: {e}")

    async def mainloop(self) -> None:
        time_before_parsing = perf_counter()

        self.db_cursor.execute("DELETE FROM materials_km3x")
        
        self.setup_data.logger.info("Materials data fetcher service: Fetching data")
        try:
            info = await self.fetch_data()
        except Exception as e:
            self.setup_data.logger.exception( "Schedule data fetcher service: "
                                             f"Error found while parsing, resetting the credentials {e}")
            self.setup_google_api_connection()

        self.setup_data.logger.info("Materials data fetcher service: Parsing data")
        self.parse_to_db(info)
        self.db_connection.commit()

        self.setup_data.logger.info(f"Materials data fetcher service: Done in {perf_counter()-time_before_parsing:.2f}seconds")

        await asyncio.sleep(2*60)

    def parse_to_db(self, info) -> None:
        for group_number, group in enumerate(("km31", "km32", "km33")):
            data = info["valueRanges"][group_number]["values"]
            for line in parse_range(data):
                self.insert_data(group, line)


    def insert_data(self, group: str, line: LINE) -> None:
        query = f"""
        INSERT INTO materials_km3x ("group", material_name, url)
        VALUES (%s, %s, %s)
        """
        self.db_cursor.execute(query, (group, *line))
        pass

    async def fetch_data(self):
        async with httpx.AsyncClient() as client:
            response = await client.get(self.url, params=self.params, headers=self.headers)
            data = response.json()

            return data
