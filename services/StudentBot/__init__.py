from typing import Any
from service_setup import SetupServiceData, get_token
from telegram.ext import ApplicationBuilder, CommandHandler
import telegram
import asyncio
from telegram.ext import CallbackQueryHandler, MessageHandler, CallbackContext, filters
from telegram import InlineKeyboardButton

from dataclasses import dataclass
import yaml
import re


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
    _id: int
    _verified: bool = False
    _real_name: str | None = None
    _group: str | None = None
    _is_inputting_name = False
    _main_message: int | None = None
    _main_message_first = True
    _options: dict[str, Any] = None
    
    @property
    def id(self) -> int:
        return self._id

    @property
    def is_verified(self) -> bool:
        return self._verified
    
    @is_verified.setter
    def is_verified(self, verified: bool) -> None:
        self._verified = verified

    @property
    def real_name(self) -> str | None:
        return self._real_name
    
    @real_name.setter
    def real_name(self, real_name: str) -> None:
        self._real_name = real_name

    @property
    def group(self) -> str | None:
        return self._group
    
    @group.setter
    def group(self, group: str) -> None:
        self._group = group

    @property
    def is_inputting_name(self) -> bool:
        return self._is_inputting_name
    
    @is_inputting_name.setter
    def is_inputting_name(self, is_inputting_name: bool) -> None:
        self._is_inputting_name = is_inputting_name

    @property
    def main_message(self) -> int | None:
        return self._main_message
    
    @main_message.setter
    def main_message(self, main_message: int) -> None:
        self._main_message = main_message

    @property
    def is_main_message_first(self) -> bool:
        return self._main_message_first
    
    @is_main_message_first.setter
    def is_main_message_first(self, main_message_first: bool) -> None:
        self._main_message_first = main_message_first

    @property
    def options(self) -> dict[str, Any] | None:
        return self._options
    
    @options.setter
    def options(self, options: dict[str, Any]) -> None:
        self._options = options


class Admins:
    def __init__(self, service) -> None:
        self.logger = service.logger
        self.groups = service.groups
        self._admins = self.load_admins()

    def get_admins(self, group: str) -> list[int]:
        return self._admins[group]
    
    def add_admin(self, group: str, user_id: int) -> None:
        self.logger.info(f"StudentBotService: Added admin {user_id} to group {group}")
        self._admins[group].append(user_id)
        self.save_admins()

    def save_admins(self) -> None:
        with open("data/Scheduler/admins.yaml", "w") as f:
            yaml.dump(self._admins, f)
    
    def load_admins(self) -> dict[str, list[int]]:
        try:
            with open("data/Scheduler/admins.yaml", "r") as f:
                return yaml.load(f, Loader=yaml.FullLoader)
        
        except FileNotFoundError:
            return {group: [] for group in self.groups}
        except yaml.error.YAMLError as e:
            self.logger.exception(f"StudentBotService: Failed to load verification messages, file is corrupted:\n{e}")
            return {group: [] for group in self.groups}


# Group: {Admin_id: {User_for_verification_id: admin_verification_message_id}}
ADMIN_VERIFIED_MESSAGES = dict[str, dict[int, dict[int, int]]]

class Verification:
    def __init__(self, service) -> None:
        self.logger = service.logger
        self.admins = service.admins
        self.groups = service.groups
        self.service = service
        self._messages = self.load_messages()
        
    def load_messages(self) -> ADMIN_VERIFIED_MESSAGES:
        try:
            with open("data/Scheduler/request_messages.yaml", "r") as f:
                return yaml.load(f, Loader=yaml.FullLoader)
        except FileNotFoundError:
            return {group: {} for group in self.groups}
        except yaml.error.YAMLError as e:
            self.logger.exception(f"StudentBotService: Failed to load verification messages, file is corrupted:\n{e}")
            return {group: {} for group in self.groups}

    async def send(self, client: Client) -> None:
        self.logger.info(f"StudentBotService: Added verification request for {client.id} to group {client.group}")
        
        name = await self.service.get_name_by_id(client.id)
        # User id is being extracted from this message by `Button.verify_user`
        # for verification. Change it only if you know what you're doing.
        verification_text = f"Verify new user {name} [{client.id}] {client.real_name} to {client.group}?"
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Verify", callback_data="verify_user")],
            [InlineKeyboardButton("Discard", callback_data="discard_user")],
        ])
        await self._send_request_to_admins(client, verification_text, reply_markup=reply_markup)
        self.save_messages()

    async def _send_request_to_admins(self, client: Client, text: str, **kwargs):
        for admin in self.admins.get_admins(client.group):
            message_id = await self.service.send_raw(admin, text, **kwargs)
            verification_group = self._messages[client.group]
            verification_group.setdefault(admin, {})[client.id] = message_id

    def save_messages(self):
        with open("data/Scheduler/request_messages.yaml", "w") as f:
            yaml.dump(self._messages, f)

    async def verify(self, client: Client, verifier: Client) -> None:
        self.logger.info(f"StudentBotService: Verified user {client.real_name} [{client.id}] to {client.group}")
        client.is_verified = True

        await self._client_send_verified_message(client)
        await self._send_client_verified_to_admins(client, verifier)

    async def _client_send_verified_message(self, client: Client) -> None:
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Menu", callback_data="menu")],
        ])
        await self.service.send(
            client.id,
            "You have been verified!",
            reply_markup=reply_markup
        )

    async def _send_client_verified_to_admins(self, client: Client, verifier: Client) -> None:
        telegram_username = await self.service.get_name_by_id(client.id)
        verified_admin_text = f"User {telegram_username} [{client.id}] {client.real_name} "\
                            f"has been verified to {client.group} by {verifier.real_name}."
        
        await self._admins_edit_message(client, verified_admin_text)

    async def discard(self, client: Client, verifier: Client) -> None:
        self.logger.info(f"StudentBotService: Discarded user {client.real_name} [{client.id}] from joining {client.group}")

        await self._client_send_discarded_message(client)
        await self._send_client_discarded_to_admins(client, verifier)

    async def _client_send_discarded_message(self, client: Client) -> None:
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Back to registration", callback_data="restart")],
        ])
        await self.service.send(
            client.id,
            "Your verification request has been discarded.",
            reply_markup=reply_markup
        )

    async def _send_client_discarded_to_admins(self, client: Client, verifier: Client) -> None:
        telegram_username = await self.service.get_name_by_id(client.id)
        discarded_admin_text = f"User {telegram_username} [{client.id}] {client.real_name} "\
                            f"has been discarded by {verifier.real_name}."

        await self._admins_edit_message(client, discarded_admin_text)

    async def _admins_edit_message(self, client: Client, text: str):
        for admin in self._messages[client.group]:
            try:
                await self.service.app.bot.edit_message_text(
                    chat_id=admin,
                    message_id=self._messages[client.group][admin][client.id],
                    text=text
                )
            except telegram.error.BadRequest:
                pass
    
    def get_client_from_verification_message(self, message: telegram.Message):
        user_id = int(re.search(r"\[(\d+)\]", message.text).group(1))
        client = self.service.clients[user_id]
        return client


class StudentBotService:
    def __init__(self, setup_data: SetupServiceData) -> None:
        self.logger = setup_data.logger
        self.clients: dict[int, Client] = dict()

        self.groups = "km31", "km32", "km33"
        self.admins = Admins(self)
        self.verification = Verification(self)

        self.app = ApplicationBuilder().token(get_token("StudentsBot")).build()

    def get_client(self, user_id: int) -> Client | None:
        if user_id not in self.clients:
            return None
        return self.clients[user_id]

    def add_client(self, client: Client) -> None:
        self.clients[client.id] = client

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
        self.set_handlers()

        await self.app.updater.start_polling()

    async def set_commands_interface(self) -> None:
        await self.app.bot.set_my_commands([
            telegram.BotCommand(command="/start", description="Start the bot"),
            telegram.BotCommand(command="/menu", description="Open the menu"),
        ])

    def set_handlers(self) -> None:
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("menu", self.menu))
        self.app.add_handler(CommandHandler("admin", self.self_promote))
        self.app.add_handler(CallbackQueryHandler(self.button_controller))
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, self.text_controller))
        self.app.add_handler(MessageHandler(filters.ALL, self.user_input_deleter))
    
    async def user_input_deleter(self, update: telegram.Update, context: CallbackContext) -> None:
        await delete_user_request_if_text(update)
        return telegram.ext.ConversationHandler.END

    async def self_promote(self, update: telegram.Update, context: CallbackContext) -> None:
        await delete_user_request_if_text(update)
        for group in self.groups:
            self.admins.add_admin(group, update.effective_user.id)

    async def button_controller(self, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query

        if not await self.client_exists(query.from_user.id):
            await query.answer(text="Message is broken :0\nWrite /start to fix this >_<")
            return

        if hasattr(Button, query.data):
            await getattr(Button, query.data)(self, update, context)
        else:
            self.logger.error(f"Button: {query.data} not found. User: {query.from_user.name} | {query.message.to_json()}")
            await query.answer(text="Invalid option selected.")

    async def text_controller(self, update: telegram.Update, context: CallbackContext) -> int:
        user = update.effective_user
        client = self.get_client(user.id)

        if client is None or not client.is_inputting_name:
            await update.message.delete()
            return telegram.ext.ConversationHandler.END

        client.real_name = update.message.text
        client.is_inputting_name = False
        await update.message.delete()

        await Menu.confirmation_menu(self, client)
        
        return telegram.ext.ConversationHandler.END

    async def send(self, usr_id: int, text: str, **kwargs) -> int:
        "Returns new message's id"
        
        client = self.get_client(usr_id)
        main_message_id = client.main_message

        if main_message_id is None or not client.is_main_message_first:
            client.is_main_message_first = True
            return await self._reset_and_send(usr_id, text, **kwargs)

        try:
            message = await self.app.bot.edit_message_text(text, chat_id=usr_id, message_id=main_message_id, **kwargs)
            return message.id
        
        except telegram.error.BadRequest:
            return await self._reset_and_send(usr_id, text, **kwargs)

    async def send_raw(self, usr_id: int, text: str, **kwargs) -> int:
        message = await self.app.bot.send_message(usr_id, text, **kwargs)
        client = self.get_client(usr_id)
        client.is_main_message_first = False
        return message.id

    async def _reset_and_send(self, usr_id: int, text: str, **kwargs) -> int:
        new_message = await self.app.bot.send_message(usr_id, text, **kwargs)

        await self.clear_main_message(usr_id)
        client = self.get_client(usr_id)
        client.main_message = new_message.id

        return new_message.id

    async def clear_main_message(self, usr_id: int) -> None:
        message = self.get_client(usr_id).main_message
        try:
            await self.app.bot.delete_message(usr_id, message)
        except telegram.error.BadRequest:
            pass

    async def menu(self, update: telegram.Update, context: CallbackContext) -> None:
        await delete_user_request_if_text(update)

        usr = update.effective_user
        client = self.get_client(usr.id)

        if client is None:
            return
        
        if client.is_verified:
            await Menu.main_menu(self, update, context)
            return

        await Menu.unverified_menu(self, update, context)

    async def start(self, update: telegram.Update, context: CallbackContext) -> None:
        user = update.effective_user

        if await self.client_exists(user.id) and self.get_client(user.id).is_verified:
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

    async def client_exists(self, usr_id: int) -> bool:
        return self.get_client(usr_id) is not None

    async def init_user(self, usr_id: int) -> None:
        if await self.client_exists(usr_id):
            return
        
        self.add_client(Client(usr_id))

    async def get_name_by_id(self, usr_id: int) -> str:
        user = await self.app.bot.get_chat_member(usr_id, usr_id)
        return user.user.name


class Menu:
    @staticmethod
    async def group_choice_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Km-31", callback_data="group_31")],
            [InlineKeyboardButton("Km-32", callback_data="group_32")],
            [InlineKeyboardButton("Km-33", callback_data="group_33")],
            [InlineKeyboardButton("Not a student", callback_data="group_none")],
        ])
        await service.send(update.effective_user.id, "Choose your group:", reply_markup=reply_markup)

    @staticmethod
    async def enter_name_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await service.send(update.effective_user.id, "Enter your full name:")
        client = service.get_client(query.from_user.id)
        client.is_inputting_name = True
        
    @staticmethod
    async def confirmation_menu(service: StudentBotService, client: Client) -> None:
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Send for confirmation", callback_data="confirm")],
            [InlineKeyboardButton("Try again", callback_data="restart")],
            [InlineKeyboardButton("Not a student", callback_data="not_a_student")],
        ])
        await service.send(client.id, f"You are {client.real_name} from {client.group}. Correct?", reply_markup=reply_markup)

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
        user = service.get_client(update.effective_user.id)

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
        client = service.get_client(query.from_user.id)
        client.group = "km31"
        await query.answer()
        await Menu.enter_name_menu(service, update, context)

    @staticmethod
    async def group_32(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        client = service.get_client(query.from_user.id)
        client.group = "km32"
        await query.answer()
        await Menu.enter_name_menu(service, update, context)

    @staticmethod
    async def group_33(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        client = service.get_client(query.from_user.id)
        client.group = "km33"
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
        client = service.get_client(query.from_user.id)
        await service.verification.send(client)

        service.logger.info(f"StudentBotService: {query.from_user.name} sent verification request")

    @staticmethod
    async def verify_user(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()

        verifier = service.get_client(query.from_user.id)
        client = service.verification.get_client_from_verification_message(query.message)
        await service.verification.verify(client, verifier)

    @staticmethod
    async def discard_user(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()

        verifier = service.get_client(query.from_user.id)
        client = service.verification.get_client_from_verification_message(query.message)
        await service.verification.discard(client, verifier)

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
