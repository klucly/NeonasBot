import asyncio
from dataclasses import dataclass
import json
import telegram
from telegram.ext import ApplicationBuilder, CommandHandler
from functools import partial

from service_setup import SetupServiceData, get_token
CHATS = ".\\data\\Example\\chats.json"


@dataclass
class CommandDataWrapper:
    setup_data: SetupServiceData
    active_chats: list[int]

def load_chats() -> list[int]:
    with open(CHATS, "r") as f:
        return json.load(f)
    
def save_chats(chats: list[int]) -> None:
    with open(CHATS, "w") as f:
        json.dump(chats, f)


class ExampleService:
    def __init__(self, setup_data: SetupServiceData):
        self.setup_data = setup_data
        self.app = ApplicationBuilder().token(get_token("Example")).build()

    async def run(self):
        self.setup_data.logger.info("Example service: Starting")

        try:
            await self.bot_setup()

            while True:
                await self.mainloop()
        finally:
            await self.app.updater.stop()
            await self.app.stop()

    async def bot_setup(self):
        await self.app.initialize()
        await self.app.start()

        await self.app.bot.set_my_commands([
            telegram.BotCommand(command="/start", description="Start the bot"),
            telegram.BotCommand(command="/huh", description="Huh?"),
        ])

        chats = load_chats()
        wrapper = CommandDataWrapper(self.setup_data, chats)

        self.app.add_handler(
            CommandHandler("start", partial(self.Commands.start, wrapper)))
        self.app.add_handler(
            CommandHandler("huh", partial(self.Commands.huh, wrapper)))

        await self.app.updater.start_polling()

    async def mainloop(self):
        ...
        await asyncio.sleep(2)

    class Commands:
        @staticmethod
        async def start(wrapper: CommandDataWrapper, update: telegram.Update, context: telegram.ext.CallbackContext):
            logger = wrapper.setup_data.logger
            chat_id = update.message.chat_id

            if chat_id in wrapper.active_chats:
                await update.message.reply_text("I know you")
            else:
                wrapper.active_chats.append(chat_id)
                save_chats(wrapper.active_chats)
                logger.info(f"Example service: {chat_id} joined")

                await update.message.reply_text("New here")

        @staticmethod
        async def huh(wrapper: CommandDataWrapper, update: telegram.Update, context: telegram.ext.CallbackContext):
            logger = wrapper.setup_data.logger

            user = update.message.from_user
            logger.info(f"Example service: {user.name} ({user.id}) requested heh")

            await update.message.reply_text("heh")
