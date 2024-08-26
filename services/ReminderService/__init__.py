from datetime import datetime
from service_setup import SetupServiceData
from services.StudentBot import StudentBotService
from asyncio import sleep


class ReminderService:
    def __init__(self, setup_data: SetupServiceData) -> None:
        self.logger = setup_data.logger
        self.shared = setup_data.shared
        self.service: StudentBotService

    async def get_bot_service(self) -> StudentBotService:
        counter = 0
        while "bot_service" not in self.shared:
            counter += 1
            sleep(0.1)

            if counter > 100:
                self.logger.error("ReminderService: Failed to find bot_service in shared")
                raise RuntimeError("Failed to find bot_service in shared")
            
        return self.shared["bot_service"]

    async def run(self) -> None:
        self.logger.info("ReminderService: Starting")
        self.service = await self.get_bot_service()

        while True:
            await self.mainloop()

    async def mainloop(self) -> None:
        await self.send_morning_reminders_if_needed()
        await self.send_a_few_days_reminder_if_needed()
        await sleep(30*60)

    async def send_morning_reminders_if_needed(self) -> None:
        self.logger.info("ReminderService: Checking for morning reminders")

        if not (datetime.now().hour == 8 and datetime.now().minute < 30 and datetime.now().weekday() < 5):
            return
        
        self.logger.info("ReminderService: Sending morning reminders")

        # TODO God please fix the naming
        for groupname in self.service.groups:
            for chat in self.service.groups_db.get_groups(groupname):
                if not chat.morning_day_schedule:
                    continue

                await self.send_morning_reminders(chat.id, groupname)

    async def send_morning_reminders(self, group_id: int, group_name: str) -> None:
        await self.service.schedule_db.group_send_schedule(group_name, group_id, self.service.schedule_db.get_current_day())

    async def send_a_few_days_reminder_if_needed(self) -> None:
        ...
