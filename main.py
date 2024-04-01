import asyncio
import sys
import logging

from service_setup import SetupServiceData
from services.Example import ExampleService


def setup_logger() -> logging.Logger:
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s', 
                                '%m-%d-%Y %H:%M:%S')

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.setFormatter(formatter)

    file_handler = logging.FileHandler('logs.log')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stdout_handler)

    return logger


class Main:
    def __init__(self):
        self.logger = setup_logger()
        self.setup_data = self.create_setup_data()

    def create_setup_data(self) -> SetupServiceData:
        return SetupServiceData(logger=self.logger, shared={})
    
    def run(self):
        try:
            asyncio.run(self.async_run())
        except Exception as e:
            self.logger.exception(e)
        finally:
            self.logger.info("Boot: Exiting...")

    async def async_run(self):
        self.logger.info("Boot: Setting up services")
        example_service = ExampleService(self.setup_data)

        self.logger.info("Boot: Running services")
        async with asyncio.TaskGroup() as tg:
            tg.create_task(example_service.run())

if __name__ == "__main__":
    main = Main()
    main.run()
