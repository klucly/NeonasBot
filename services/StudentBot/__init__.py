from typing import Any
from service_setup import SetupServiceData, get_token
from telegram.ext import ApplicationBuilder, CommandHandler
import telegram
import asyncio
from telegram.ext import CallbackQueryHandler, MessageHandler, CallbackContext, filters
from telegram import InlineKeyboardButton

from dataclasses import dataclass


async def idle() -> None:
    while True:
        await asyncio.sleep(1)


def button_request(update: telegram.Update) -> bool:
    return update.message is None


def text_request(update: telegram.Update) -> bool:
    return update.message is not None


async def delete_user_request_if_text(update: telegram.Update) -> None:
    try:
        if text_request(update):
            await update.message.delete()
    except telegram.error.BadRequest:
        pass


@dataclass
class Client:
    id: int
    verified: bool = False
    real_name: str | None = None
    group: str | None = None
    is_inputting_name = False
    messages: list[int] | None = None
    options: dict[str, Any] = None


class StudentBotService:
    def __init__(self, setup_data: SetupServiceData) -> None:
        self.logger = setup_data.logger
        self.clients: dict[int, Client] = dict()
        self.admins: dict[str, list[int]] = {"*": [], "km-31": [], "km-32": [], "km-33": []}
        self.app = ApplicationBuilder().token(get_token("StudentsBot")).build()

    async def run(self) -> None:
        try:
            await self.bot_setup()
            await idle()
        finally:
            await self.app.updater.stop()
            await self.app.stop()

    async def bot_setup(self) -> None:
        self.logger.info("StudentBotService: Starting")

        await self.app.initialize()
        await self.app.start()

        await self.set_commands_interface()
        await self.set_handlers()

        await self.app.updater.start_polling()

    async def set_commands_interface(self) -> None:
        await self.app.bot.set_my_commands([
            telegram.BotCommand(command="/start", description="Start the bot"),
            telegram.BotCommand(command="/menu", description="Open the menu"),
        ])

    async def set_handlers(self) -> None:
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("menu", self.menu))
        self.app.add_handler(CommandHandler("admin", self.self_promote))
        self.app.add_handler(CallbackQueryHandler(self.button_controller))
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, self.text_controller))
    
    async def self_promote(self, update: telegram.Update, context: CallbackContext) -> None:
        if "*" not in self.admins:
            self.admins["*"] = [update.effective_user.id]
        else:
            self.admins["*"].append(update.effective_user.id)

    async def button_controller(self, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query

        if hasattr(Button, query.data):
            await getattr(Button, query.data)(self, update, context)
        else:
            self.logger.error(f"Button: {query.data} not found. User: {query.from_user.name} | {query.message.to_json()}")
            await query.answer(text="Invalid option selected.")

    async def text_controller(self, update: telegram.Update, context: CallbackContext) -> int:
        user = update.effective_user
        client = self.clients[user.id]

        if user.id not in self.clients or not client.is_inputting_name:
            await update.message.delete()
            return telegram.ext.ConversationHandler.END

        client.real_name = update.message.text
        client.is_inputting_name = False
        await update.message.delete()

        await Menu.confirmation_menu(self, client)
        
        return telegram.ext.ConversationHandler.END

    async def send(self, usr_id: int, text: str, interface_control=True, **kwargs) -> telegram.Message:
        messages = self.clients[usr_id].messages

        if not interface_control:
            return await self.app.bot.send_message(usr_id, text, **kwargs)

        try:
            if len(messages) == 0:
                raise telegram.error.BadRequest("No messages found")
            return await self.app.bot.edit_message_text(text, chat_id=usr_id, message_id=messages[-1], **kwargs)
        
        except telegram.error.BadRequest:
            return await self._reset_and_send(usr_id, text, **kwargs)

    async def _reset_and_send(self, usr_id: int, text: str, **kwargs) -> telegram.Message:
        new_message = await self.app.bot.send_message(usr_id, text, **kwargs)

        await self.clear_history(usr_id)
        self.clients[usr_id].messages = [new_message.id]

        return new_message

    async def menu(self, update: telegram.Update, context: CallbackContext) -> None:
        await delete_user_request_if_text(update)

        usr = update.effective_user
        client = self.clients[usr.id]
        if usr.id not in self.clients:
            return
        
        if client.verified:
            await Menu.main_menu(self, update, context)
            return
    
        await self.clear_history(usr.id)
        client.messages = []

        await Menu.unverified_menu(self, update, context)

    async def start(self, update: telegram.Update, context: CallbackContext) -> None:
        user = update.effective_user

        if await self.user_exists(user.id) and self.clients[user.id].verified:
            await self.menu(update, context)
            return

        self.logger.info(f"StudentBotService: Started with {user.name}")
        
        await delete_user_request_if_text(update)
        await self.init_user(user.id)

        if await update.effective_chat.get_member_count() > 2:
            # TODO make it work in groups
            await update.message.reply_text("Cannot be used in groups yet. Sorry!")
        else:
            await Menu.group_choice_menu(self, update, context)

    async def user_exists(self, usr_id: int) -> bool:
        return usr_id in self.clients

    async def init_user(self, usr_id: int) -> None:
        if await self.user_exists(usr_id):
            await self.clear_history(usr_id)

        self.clients[usr_id] = Client(usr_id, messages=[])
        
    async def clear_history(self, usr_id: int) -> None:
        for message in self.clients[usr_id].messages:
            try:
                await self.app.bot.delete_message(usr_id, message)
            except telegram.error.BadRequest:
                pass

    async def get_name_by_id(self, usr_id: int) -> str:
        # TODO unsafe for user with a name and username different
        chat = await self.app.bot.get_chat(usr_id)
        return chat.username

    async def send_verification_request(self, user: Client) -> None:
        name = await self.get_name_by_id(user.id)
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Verify", callback_data="verify_user")],
            [InlineKeyboardButton("Discard", callback_data="discard_user")],
        ])
        verification_text = f"Verify new user @{name} ({user.real_name}) to {user.group}?"

        for admin in self.admins["*"]:
            await self.send(admin, verification_text, False, reply_markup=reply_markup)
        
        if user.group not in self.admins:
            self.logger.warning(f"StudentBotService: no admins found for {user.group}")
            return
        
        for admin in self.admins[user.group]:
            await self.send(admin, verification_text, False, reply_markup=reply_markup)


class Menu:
    @staticmethod
    async def group_choice_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("KM-31", callback_data="group_31")],
            [InlineKeyboardButton("KM-32", callback_data="group_32")],
            [InlineKeyboardButton("KM-33", callback_data="group_33")],
            [InlineKeyboardButton("Not a student", callback_data="group_none")],
        ])
        await service.send(update.effective_user.id, "Choose your group:", reply_markup=reply_markup)
            
    @staticmethod
    async def enter_name_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await service.send(update.effective_user.id, "Enter your full name:")
        service.clients[query.from_user.id].is_inputting_name = True
        
    @staticmethod
    async def confirmation_menu(service: StudentBotService, user: Client) -> None:
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Send for confirmation", callback_data="confirm")],
            [InlineKeyboardButton("Try again", callback_data="restart")],
            [InlineKeyboardButton("Not a student", callback_data="not_a_student")],
        ])
        await service.send(user.id, f"You are {user.real_name} from {user.group}. Correct?", reply_markup=reply_markup)

    @staticmethod
    async def unverified_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Schedule", callback_data="schedule")],
            [InlineKeyboardButton("Register", callback_data="restart")],
            [InlineKeyboardButton("Options", callback_data="options")],
        ])
        await service.send(update.effective_user.id, "You are not registered", reply_markup=reply_markup)

    @staticmethod
    async def schedule_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Mon", callback_data="todo")],
            [InlineKeyboardButton("Tue", callback_data="todo")],
            [InlineKeyboardButton("Wed", callback_data="todo")],
            [InlineKeyboardButton("Thu", callback_data="todo")],
            [InlineKeyboardButton("Fri", callback_data="todo")],
            [InlineKeyboardButton("Sat", callback_data="todo")],
            [InlineKeyboardButton("Sun", callback_data="todo")],
        ])
        await service.send(update.effective_user.id, "Enter the day:", reply_markup=reply_markup)

    @staticmethod
    async def options_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        await service.send(update.effective_user.id, "<Options>")

    @staticmethod
    async def main_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        user = service.clients[update.effective_user.id]

        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Schedule", callback_data="schedule")],
            [InlineKeyboardButton("Materials", callback_data="materials")],
            [InlineKeyboardButton("Debts", callback_data="debts")],
            [InlineKeyboardButton("Options", callback_data="options")],
        ])
        await service.send(user.id, f"Hello, {user.real_name}", reply_markup=reply_markup)


class Button:
    @staticmethod
    async def group_31(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        service.clients[query.from_user.id].group = "km31"
        await query.answer()
        await Menu.enter_name_menu(service, update, context)

    @staticmethod
    async def group_32(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        service.clients[query.from_user.id].group = "km32"
        await query.answer()
        await Menu.enter_name_menu(service, update, context)

    @staticmethod
    async def group_33(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        service.clients[query.from_user.id].group = "km33"
        await query.answer()
        await Menu.enter_name_menu(service, update, context)

    @staticmethod
    async def group_none(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        await Menu.unverified_menu(service, update, context)

    @staticmethod
    async def restart(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        await StudentBotService.start(service, update, context)

    @staticmethod
    async def not_a_student(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        await Menu.unverified_menu(service, update, context)

    @staticmethod
    async def schedule(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        await Menu.schedule_menu(service, update, context)

    @staticmethod
    async def options(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        await Menu.options_menu(service, update, context)

    @staticmethod
    async def confirm(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        await service.send(update.effective_user.id, "Verification request sent! Please wait for confirmation ^^")
        # TODO normal verification
        await service.send_verification_request(service.clients[query.from_user.id])
        service.logger.info(f"StudentBotService: Verification request sent to {query.from_user.name}")

    @staticmethod
    async def verify_user(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        service.clients[query.from_user.id].verified = True

        await update.effective_message.edit_text(f"{query.from_user.name} has been verified")

        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Menu", callback_data="menu")],
        ])
        await service.send(update.effective_user.id, "You have been verified!!! :DD", reply_markup=reply_markup)
        service.logger.info(f"StudentBotService: {query.from_user.name} has been verified")

    @staticmethod
    async def discard_user(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        await update.effective_message.edit_text(f"{query.from_user.name} has been discarded")
        service.logger.info(f"StudentBotService: {query.from_user.name} has been discarded")

    @staticmethod
    async def menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        await Menu.main_menu(service, update, context)

    @staticmethod
    async def materials(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        await service.send(update.effective_user.id, "<Materials>")
    
    @staticmethod
    async def debts(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        await service.send(update.effective_user.id, "<Debts>")
