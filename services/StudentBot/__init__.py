from service_setup import SetupServiceData, get_token
from telegram.ext import ApplicationBuilder, CommandHandler
import telegram
import asyncio
from telegram.ext import CallbackQueryHandler, MessageHandler, CallbackContext, filters
from telegram import InlineKeyboardButton

from dataclasses import dataclass


async def idle():
    while True:
        await asyncio.sleep(1)

def button_request(update: telegram.Update):
    return update.message is None

@dataclass
class User:
    id: telegram.User
    verified: bool = False
    real_name: str | None = None
    group: str | None = None
    is_inputting_name = False
    messages: list | None = None


class StudentBotService:
    def __init__(self, setup_data: SetupServiceData):
        self.logger = setup_data.logger
        self.users: dict[int, User] = dict()
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
        self.app.add_handler(CallbackQueryHandler(self.button_controller))
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, self.text_controller))
        
    async def button_controller(self, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        self.logger.info(f"Button: {query.data} has been pressed by {query.from_user.name}")

        match query.data:
            case "group-choice:km-31":
                await Button.group_31(self, update, context)
            case "group-choice:km-32":
                await Button.group_32(self, update, context)
            case "group-choice:km-33":
                await Button.group_33(self, update, context)
            case "group-choice:none":
                await Button.group_none(self, update, context)
            case "confirmation:send":
                await Button.group_31(self, update, context)
            case "confirmation:restart":
                await Button.restart(self, update, context)
            case "confirmation:not_a_student":
                await Button.group_31(self, update, context)
            case _:
                self.logger.error(f"Button: {query.data} not found. User: {query.from_user.name} | {query.message.to_json()}")
                await query.answer(text="Invalid option selected.")

    async def text_controller(self, update: telegram.Update, context: CallbackContext) -> int:
        user = update.effective_user

        if user.id not in self.users or not self.users[user.id].is_inputting_name:
            await update.message.delete()
            return telegram.ext.ConversationHandler.END

        self.users[user.id].real_name = update.message.text
        self.users[user.id].is_inputting_name = False
        await update.message.delete()

        await Menu.confirmation_menu(self, self.users[user.id])
        
        return telegram.ext.ConversationHandler.END

    async def start(self, update: telegram.Update, context: CallbackContext) -> None:
        usr_info = update.effective_user

        self.logger.info(f"StudentBotService: Started with {usr_info.name}")

        await self.init_user(usr_info.id)

        if await update.effective_chat.get_member_count() > 2:
            # TODO make it work in groups
            await update.message.reply_text("Cannot be used in groups yet. Sorry!")
        else:
            await Menu.group_choice_menu(self, update, context)

    async def init_user(self, usr_id: int) -> None:
        if usr_id in self.users:
            await self.clear_history(usr_id)

        self.users[usr_id] = User(usr_id, messages=[])
        
    async def clear_history(self, usr_id: int):
        for message in self.users[usr_id].messages:
            try:
                await message.delete()
            except telegram.error.BadRequest:
                pass


class Menu:
    @staticmethod
    async def group_choice_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext):
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("KM-31", callback_data="group-choice:km-31")],
            [InlineKeyboardButton("KM-32", callback_data="group-choice:km-32")],
            [InlineKeyboardButton("KM-33", callback_data="group-choice:km-33")],
            [InlineKeyboardButton("Not a student", callback_data="group-choice:none")],
        ])
                
        service.users[update.effective_user.id].messages.append(
            await service.app.bot.send_message(update.effective_chat.id, "Choose your group:", reply_markup=reply_markup))
        
        if update.message is not None:
            await update.message.delete()
            
    @staticmethod
    async def enter_name_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext):
        query = update.callback_query
        await query.edit_message_text("Enter your full name:")
        service.users[query.from_user.id].is_inputting_name = True
        
    @staticmethod
    async def confirmation_menu(service: StudentBotService, user: User) -> None:
        buttons = [
            [InlineKeyboardButton("Send for confirmation", callback_data="confirmation:send")],
            [InlineKeyboardButton("Try again", callback_data="confirmation:restart")],
            [InlineKeyboardButton("Not a student", callback_data="confirmation:not_a_student")],
        ]
        reply_markup = telegram.InlineKeyboardMarkup(buttons)
        
        try:
            await user.messages[0].edit_text(
                f"You are {user.real_name} from {user.group}. Correct?", reply_markup=reply_markup)
        except telegram.error.BadRequest:
            user.messages.append(await service.app.bot.send_message(
                user.id, f"You are {user.real_name} from {user.group}. Correct?", reply_markup=reply_markup))

    @staticmethod
    async def unregistered_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        buttons = [
            [InlineKeyboardButton("Schedule", callback_data="confirmation:send")],
            [InlineKeyboardButton("Register", callback_data="confirmation:restart")],
            [InlineKeyboardButton("Options", callback_data="confirmation:not_a_student")],
        ]
        reply_markup = telegram.InlineKeyboardMarkup(buttons)
        service.users[update.message.from_user.id].messages[0].edit_text("You are not registered", reply_markup=reply_markup)


class Button:
    @staticmethod
    async def group_31(service: StudentBotService, update: telegram.Update, context: CallbackContext):
        query = update.callback_query
        service.users[query.from_user.id].group = "km-31"
        await query.answer()
        await Menu.enter_name_menu(service, update, context)

    @staticmethod
    async def group_32(service: StudentBotService, update: telegram.Update, context: CallbackContext):
        query = update.callback_query
        service.users[query.from_user.id].group = "km-32"
        await query.answer()
        await Menu.enter_name_menu(service, update, context)

    @staticmethod
    async def group_33(service: StudentBotService, update: telegram.Update, context: CallbackContext):
        query = update.callback_query
        service.users[query.from_user.id].group = "km-33"
        await query.answer()
        await Menu.enter_name_menu(service, update, context)

    @staticmethod
    async def group_none(service: StudentBotService, update: telegram.Update, context: CallbackContext):
        query = update.callback_query
        await query.answer()
        await Menu.unregistered_menu()

    @staticmethod
    async def restart(service: StudentBotService, update: telegram.Update, context: CallbackContext):
        query = update.callback_query
        await query.answer()
        await StudentBotService.start(service, update, context)

    @staticmethod
    async def not_a_student(service: StudentBotService, update: telegram.Update, context: CallbackContext):
        query = update.callback_query
        await query.answer()
        await Menu.unregistered_menu(service, update, context)
