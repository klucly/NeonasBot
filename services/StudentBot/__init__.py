import datetime
from typing import Any
from service_setup import SetupServiceData, get_token, load_student_db_config, load_schedule_db_config, load_material_db_config
from telegram.ext import ApplicationBuilder, CommandHandler
import telegram
import asyncio
from telegram.ext import CallbackQueryHandler, MessageHandler, CallbackContext, filters
from telegram import InlineKeyboardButton
import psycopg2

from dataclasses import dataclass
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
    _is_inputting_name: bool = False
    _main_message: int | None = None
    _main_message_first: bool = True
    _options: dict[str, Any] = None
    _is_admin: bool = True
    student_db: Any = None
    
    @property
    def id(self) -> int:
        return self._id

    @property
    def is_verified(self) -> bool:
        return self._verified
    
    @is_verified.setter
    def is_verified(self, verified: bool) -> None:
        query = """
        UPDATE students
        SET verified = %s
        WHERE id = %s
        """

        self.student_db.cursor.execute(query, (verified, self.id))
        self._verified = verified
        self.student_db.update_db()

    @property
    def real_name(self) -> str | None:
        return self._real_name
    
    @real_name.setter
    def real_name(self, real_name: str) -> None:
        query = """
        UPDATE students
        SET real_name = %s
        WHERE id = %s;  
        """

        self.student_db.cursor.execute(query, (real_name, self.id))
        self._real_name = real_name
        self.student_db.update_db()

    @property
    def group(self) -> str | None:
        return self._group
    
    @group.setter
    def group(self, group_name: str) -> None:
        query = """
        UPDATE students
        SET "group" = %s
        WHERE id = %s;
        """

        self.student_db.cursor.execute(query, (group_name, self.id))
        self._group = group_name
        self.student_db.update_db()

    @property
    def is_inputting_name(self) -> bool:
        return self._is_inputting_name
    
    @is_inputting_name.setter
    def is_inputting_name(self, is_inputting_name: bool) -> None:
        query = """
        UPDATE students
        SET is_inputting_name = %s
        WHERE id = %s;
        """

        self.student_db.cursor.execute(query, (is_inputting_name, self.id))
        self._is_inputting_name = is_inputting_name

        self.student_db.update_db()

    @property
    def main_message(self) -> int | None:
        return self._main_message
    
    @main_message.setter
    def main_message(self, main_message_: int) -> None:
        query = """
        UPDATE students
        SET main_message = %s
        WHERE id = %s;
        """

        self.student_db.cursor.execute(query, (main_message_, self.id))
        self._main_message = main_message_

        self.student_db.update_db()

    @property
    def is_main_message_first(self) -> bool:
        return self._main_message_first
    
    @is_main_message_first.setter
    def is_main_message_first(self, main_message_first: bool) -> None:
        query = """
        UPDATE students
        SET main_message_first = %s
        WHERE id = %s;
        """

        self.student_db.cursor.execute(query, (main_message_first, self.id))
        self._main_message_first = main_message_first

        self.student_db.update_db()

    @property
    def options(self) -> dict[str, Any] | None:
        return self._options
    
    @options.setter
    def options(self, options: dict[str, Any]) -> None:
        self._options = options

    @property
    def is_admin(self) -> bool:
        return self._is_admin


class Admins:
    def __init__(self, service) -> None:
        self.logger = service.logger
        self.groups = service.groups
        self.service = service

    def get_admins(self, group: str) -> list[int]:
        self.service.student_db.cursor.execute("""
            SELECT id FROM students WHERE
            "group" = %s AND
            is_admin = true;
        """, (group, ))

        output = self.service.student_db.cursor.fetchone()
        if output is None:
            return ()
        return output
    
    def add_admin(self, user_id: int) -> None:
        self.logger.info(f"StudentBotService: Added admin {user_id}")
        self.service.student_db.cursor.execute("""
            UPDATE students SET is_admin = true WHERE id = %s;
        """, (user_id,))
        self.service.student_db.update_db()


class StudentDB:
    def __init__(self):
        self.connection = psycopg2.connect(**load_student_db_config())
        self.cursor = self.connection.cursor()

    def add_student(self, id: int) -> Client:
        query = """
        INSERT INTO students (id, verified, real_name, "group", is_inputting_name, main_message, main_message_first, is_admin)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """

        self.cursor.execute(query, (id, False, None, None, False, None, True, False))
        self.connection.commit()

        student = Client(id, student_db=self)

        return student

    def update_student_verification(self, id: int, verified: bool) -> None:
        query = """
        UPDATE students 
        SET verified = %s
        WHERE id = %s
        """

        self.cursor.execute(query, (verified, id))
        self.connection.commit()

    def get_student(self, id: int) -> Client | None:
        query = """
        SELECT * FROM students
        WHERE id = %s
        """

        self.cursor.execute(query, (id,))
        student_info = self.cursor.fetchone()

        if student_info is None:
            return None

        student = Client(_id = student_info[0],
                         _verified = student_info[1],
                         _real_name = student_info[2],
                         _group = student_info[3],
                         _is_inputting_name = student_info[4],
                         _main_message = student_info[5],
                         _main_message_first = student_info[6],
                         _is_admin=student_info[7],
                         student_db = self)
        
        return student

    def student_exist(self, id: int) -> bool:
        return bool(self.get_student(id))

    def close(self):
        self.cursor.close()
        self.connection.close()

    def update_db(self) -> None:
        self.connection.commit()


class Verification:
    def __init__(self, service, student_db) -> None:
        self.logger = service.logger
        self.admins = service.admins
        self.groups = service.groups
        self.student_db = student_db
        self.service = service

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

    async def _send_request_to_admins(self, client: Client, text: str, **kwargs):
        for admin in self.admins.get_admins(client.group):
            await self._send_message(client.group, admin, client.id, text, **kwargs)

    async def _send_message(self, group: str, admin: int, user: int, text: str, **kwargs) -> None:
        message_id = await self.service.send_raw(admin, text, **kwargs)
        self.student_db.cursor.execute("""
            INSERT INTO verification_messages ("group", "admin", "user", "message")
            VALUES (%s, %s, %s, %s)
        """, (group, admin, user, message_id))
        self.student_db.update_db()

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
        for admin, user, message in self.get_admin_messages_from_group(client.group):
            try:
                await self.service.app.bot.edit_message_text(
                    chat_id=admin,
                    message_id=message,
                    text=text
                )
            except telegram.error.BadRequest:
                pass

    def get_admin_messages_from_group(self, group: str) -> list[tuple[int, int, int]]:
        self.student_db.cursor.execute("""
            SELECT "admin", "user", "message" FROM verification_messages
            WHERE "group" = %s
        """, (group,))

        return self.student_db.cursor.fetchall()
    
    def get_client_from_verification_message(self, message: telegram.Message):
        user_id = int(re.search(r"\[(\d+)\]", message.text).group(1))
        client = self.service.student_db.get_student(user_id)
        return client


class ScheduleDB:
    def __init__(self, stud_bot):
        self.connection = psycopg2.connect(**load_student_db_config())
        self.cursor = self.connection.cursor()
        self.stud_bot = stud_bot
        self.student_db = self.stud_bot.student_db

    def get_schedule(self, group_name: str, day: str, week: int) -> list:
        conn = psycopg2.connect(**load_schedule_db_config())
        cur = conn.cursor()

        query = f"""
            SELECT time, subject, class_type, url
            FROM {group_name}
            WHERE day_of_week = %s AND week = %s;
            """

        try:
            cur.execute(query, (day, week))
            rows = cur.fetchall()
        except Exception as e:
            print(f"Database error: {e}")
            rows = []
        finally:
            cur.close()
            conn.close()

        return rows

    async def send_schedule(self, update: telegram.Update, user_id: int, context: CallbackContext, day: str) -> None:
        user = update.effective_user
        client = self.student_db.get_student(user.id)
        week = self.get_week()

        schedule = self.get_schedule(client.group, day, week)

        if not schedule:
            await self.stud_bot.send(user.id, f"No schedule found for {day}.")
            return
        
        schedule_info = ""
        for row in schedule:
            start_time = row[0]
            subject = row[1]
            class_type = row[2]
            link = row[3]
            schedule_info += f"{start_time}: {subject}, ({class_type}) [{link}]\n"

        try:
            await self.stud_bot.send(user.id, f"Schedule for {day}:\n{schedule_info}")
        except Exception as e:
            print(f"Error sending schedule: {e}")

    @staticmethod
    def unverified_need_to_choose_group(context: CallbackContext) -> bool:
        if "unverified_choose_group_for_schedule" not in context.chat_data:
            return True
        
        return context.chat_data["unverified_choose_group_for_schedule"]

    def get_week(self):
        return datetime.date.today().isocalendar()[1] % 2 + 1


class MaterialDB:
    def __init__(self, stud_bot):
        self.connection = psycopg2.connect(**load_student_db_config())
        self.cursor = self.connection.cursor()
        self.stud_bot = stud_bot
        self.student_db = self.stud_bot.student_db

    def get_material(self, group_name: str) -> list:
        conn = psycopg2.connect(**load_material_db_config())
        cur = conn.cursor()

        query = f"""
            SELECT material_name, url
            FROM materials_km3x
            WHERE "group" = '{group_name}';
            """

        try:
            cur.execute(query,)
            rows = cur.fetchall()
        except Exception as e:
            print(f"Database error: {e}")
            rows = []
        finally:
            cur.close()
            conn.close()

        return rows
    
    async def send_material(self, update: telegram.Update, user_id: int, context: CallbackContext) -> None:
        user = update.effective_user
        client = self.student_db.get_student(user.id)

        material = self.get_material(client.group)

        if not material:
            self.stud_bot.send(user.id, f"Немає матеріалів для  {client.group}.")
            return

        material_info = ""
        for row in material:
            material_name = row[0]
            url = row[1]

            material_info += f"[{material_name}] ({url})\n\n"

        try:
            await self.stud_bot.send(user.id, f"Матеріали для **{client.group}**:\n{material_info}")
        except Exception as e:
            print(f"Error sending material: {e}")


class StudentBotService:
    def __init__(self, setup_data: SetupServiceData) -> None:
        self.logger = setup_data.logger

        self.groups = "km31", "km32", "km33"
        self.admins = Admins(self)
        self.student_db = StudentDB()
        self.schedule_db = ScheduleDB(self)
        self.material_db = MaterialDB(self)
        self.verification = Verification(self, self.student_db)
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
        self.app.add_handler(CommandHandler("forgetme", self.forget_me))
        self.app.add_handler(CallbackQueryHandler(self.button_controller))
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, self.text_controller))
        self.app.add_handler(MessageHandler(filters.ALL, self.user_input_deleter))

    async def forget_me(self, update: telegram.Update, context: CallbackContext) -> None:
        user = update.effective_user
        self.student_db.cursor.execute("""
            DELETE FROM students
            WHERE id = %s
        """, (user.id,))
        
        await delete_user_request_if_text(update)
        self.student_db.update_db()
    
    async def user_input_deleter(self, update: telegram.Update, context: CallbackContext) -> None:
        await delete_user_request_if_text(update)
        return telegram.ext.ConversationHandler.END

    async def self_promote(self, update: telegram.Update, context: CallbackContext) -> None:
        await delete_user_request_if_text(update)
        self.admins.add_admin(update.effective_user.id)

    async def button_controller(self, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query

        if not self.student_db.student_exist(query.from_user.id):
            await query.answer(text="/start to start the bot")
            return

        name, args = self.parse_button_query(query.data)
        if hasattr(Button, name):
            await getattr(Button, name)(self, update, context, *args)
        else:
            self.logger.error(f"Button: {name} not found. User: {query.from_user.name} | {query.message.to_json()}")
            await query.answer(text="Invalid option selected.")

    def parse_button_query(self, query: str) -> tuple[str, list[str]]:
        '''
        Parsing query for button controller.

        Valid syntax:
        * button_name
        * button_name(arg1)
        * button_name(arg1, arg2, ...)
        '''

        if "(" not in query:
            return query, []
        
        if query[-1] != ")":
            raise ValueError(f"{query} has invalid query format. Expected ending with `)`")
        
        name_end = query.index("(")
        name = query[:name_end]
        args = query[name_end + 1:-1].split(",")
        return name, args

    async def text_controller(self, update: telegram.Update, context: CallbackContext) -> int:
        user = update.effective_user
        client = self.student_db.get_student(user.id)

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
        
        client = self.student_db.get_student(usr_id)
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
        client = self.student_db.get_student(usr_id)
        client.is_main_message_first = False
        return message.id

    async def _reset_and_send(self, usr_id: int, text: str, **kwargs) -> int:
        new_message = await self.app.bot.send_message(usr_id, text, **kwargs)

        await self.clear_main_message(usr_id)
        client = self.student_db.get_student(usr_id)
        client.main_message = new_message.id

        return new_message.id

    async def clear_main_message(self, usr_id: int) -> None:
        message = self.student_db.get_student(usr_id).main_message
        try:
            await self.app.bot.delete_message(usr_id, message)
        except telegram.error.BadRequest:
            pass

    async def menu(self, update: telegram.Update, context: CallbackContext) -> None:
        await delete_user_request_if_text(update)

        usr = update.effective_user
        client = self.student_db.get_student(usr.id)

        if client is None:
            return
        
        if client.is_verified:
            await Menu.main_menu(self, update, context)
            return

        await Menu.unverified_menu(self, update, context)

    async def start(self, update: telegram.Update, context: CallbackContext) -> None:
        user = update.effective_user

        if self.student_db.student_exist(user.id) and self.student_db.get_student(user.id).is_verified:
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

    async def init_user(self, usr_id: int) -> None:
        if self.student_db.student_exist(usr_id):
            return
        
        self.student_db.add_student(usr_id)

    async def get_name_by_id(self, usr_id: int) -> str:
        user = await self.app.bot.get_chat_member(usr_id, usr_id)
        return user.user.name


class Menu:
    @staticmethod
    async def group_choice_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Km-31", callback_data="choose_group(km31)")],
            [InlineKeyboardButton("Km-32", callback_data="choose_group(km32)")],
            [InlineKeyboardButton("Km-33", callback_data="choose_group(km33)")],
            [InlineKeyboardButton("Not a student", callback_data="not_a_student")],
        ])
        await service.send(update.effective_user.id, "Choose your group:", reply_markup=reply_markup)

    @staticmethod
    async def schedule_group_choice_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Km-31", callback_data="schedule_choose_group(km31)")],
            [InlineKeyboardButton("Km-32", callback_data="schedule_choose_group(km32)")],
            [InlineKeyboardButton("Km-33", callback_data="schedule_choose_group(km33)")],
        ])
        await service.send(update.effective_user.id, "Choose the group:", reply_markup=reply_markup)

    @staticmethod
    async def enter_name_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await service.send(update.effective_user.id, "Enter your full name:")
        client = service.student_db.get_student(query.from_user.id)
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
        client = service.student_db.get_student(update.effective_user.id)
        
        if not client.is_verified and service.schedule_db.unverified_need_to_choose_group(context):
            return await Menu.schedule_group_choice_menu(service, update, context)
        context.chat_data["unverified_choose_group_for_schedule"] = True

        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Понеділок", callback_data="schedule_day(Monday)")],
            [InlineKeyboardButton("Вівторок", callback_data="schedule_day(Tuesday)")],
            [InlineKeyboardButton("Середа", callback_data="schedule_day(Wednesday)")],
            [InlineKeyboardButton("Четвер", callback_data="schedule_day(Thursday)")],
            [InlineKeyboardButton("П'ятниця", callback_data="schedule_day(Friday)")]
        ])
        await service.send(update.effective_user.id, "Enter the day:", reply_markup=reply_markup)

    @staticmethod
    async def options_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        await service.send(update.effective_user.id, "<Options>")

    @staticmethod
    async def main_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        user = service.student_db.get_student(update.effective_user.id)

        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Schedule", callback_data="schedule")],
            [InlineKeyboardButton("Materials", callback_data="materials")],
            [InlineKeyboardButton("Debts", callback_data="debts")],
            [InlineKeyboardButton("Options", callback_data="options")],
        ])
        await service.send(user.id, f"Hello, {user.real_name}", reply_markup=reply_markup)

    @staticmethod
    async def admin_material_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Google sheet link", url="https://docs.google.com/spreadsheets/d/1bfFIgVgv-dDK0HOcMw1qr861vWI8IXJyTEzcDGYMDDc/edit?gid=47762859#gid=47762859")],
            [InlineKeyboardButton("Подивитися матеріали", callback_data="view_material")],
            [InlineKeyboardButton("Назад", callback_data="restart")],
        ])
        await service.send(update.effective_user.id, "Оберіть опцію:", reply_markup=reply_markup)


class Button:
    @staticmethod
    async def choose_group(service: StudentBotService, update: telegram.Update, context: CallbackContext, group: str) -> None:
        query = update.callback_query
        client = service.student_db.get_student(query.from_user.id)
        client.group = group
        await query.answer()
        await Menu.enter_name_menu(service, update, context)

    @staticmethod
    async def schedule_choose_group(service: StudentBotService, update: telegram.Update, context: CallbackContext, group: str) -> None:
        context.chat_data["unverified_choose_group_for_schedule"] = False
        query = update.callback_query
        client = service.student_db.get_student(query.from_user.id)
        client.group = group
        await query.answer()
        await Menu.schedule_menu(service, update, context)

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
    async def schedule_day(service: StudentBotService, update: telegram.Update, context: CallbackContext, day: str) -> None:
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()
        await service.schedule_db.send_schedule(update, user_id, context, day)

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
        client = service.student_db.get_student(query.from_user.id)
        await service.verification.send(client)

        service.logger.info(f"StudentBotService: {query.from_user.name} sent verification request")

    @staticmethod
    async def verify_user(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()

        verifier = service.student_db.get_student(query.from_user.id)
        client = service.verification.get_client_from_verification_message(query.message)
        await service.verification.verify(client, verifier)

    @staticmethod
    async def discard_user(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()

        verifier = service.student_db.get_student(query.from_user.id)
        client = service.verification.get_client_from_verification_message(query.message)
        await service.verification.discard(client, verifier)

    @staticmethod
    async def menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        await Menu.main_menu(service, update, context)

    @staticmethod
    async def materials(service: StudentBotService, update: telegram.Update, context: CallbackContext):
        client = service.student_db.get_student(update.effective_user.id)
        query = update.callback_query
        user_id = query.from_user.id


        if client.is_admin:
            await Menu.admin_material_menu(service, update, context)
            return
        
        await service.material_db.send_material(update, user_id, context)

    @staticmethod
    async def view_material(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()
        await service.material_db.send_material(update, user_id, context)

    @staticmethod
    async def send_link_material(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()
        text = "[Таблиця з матеріалами](https://docs.google.com/spreadsheets/d/1bfFIgVgv-dDK0HOcMw1qr861vWI8IXJyTEzcDGYMDDc/edit?gid=47762859#gid=47762859)"
        await service.send(user_id, text, parse_mode="MARKDOWN")


    @staticmethod
    async def debts(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        await service.send(update.effective_user.id, "<Debts>")
