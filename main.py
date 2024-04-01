import asyncio
import sys
import logging

from service_setup import SetupServiceData
from services.Example import ExampleService
from services.Scheduler import SchedulerService


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
        return SetupServiceData(logger=self.logger, shared=dict())
    
    def run(self):
        asyncio.run(self.async_run())

    async def async_run(self):
        self.logger.info("Boot: Setting up services")
        example_service = ExampleService(setup_data=self.setup_data)
        scheduler_service = SchedulerService(setup_data=self.setup_data)

        try:
            self.logger.info("Boot: Running services")
            async with asyncio.TaskGroup() as tg:
                tg.create_task(example_service.run())
                tg.create_task(scheduler_service.run())

        except Exception as e:
            self.logger.exception(e)
            raise e
        
        finally:
            self.logger.info("Boot: Exiting...")

if __name__ == "__main__":
    main = Main()
    main.run()
