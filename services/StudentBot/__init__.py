from copy import copy
import datetime
from typing import Any
from service_setup import SetupServiceData, get_token, load_student_db_config, load_schedule_db_config, load_material_db_config, load_debts_db_config, GroupsDB
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
    _is_inputting: bool = False
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
    def is_inputting(self) -> bool:
        return self._is_inputting
    
    @is_inputting.setter
    def is_inputting(self, is_inputting: bool) -> None:
        query = """
        UPDATE students
        SET is_inputting_name = %s
        WHERE id = %s;
        """

        self.student_db.cursor.execute(query, (is_inputting, self.id))
        self._is_inputting = is_inputting

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
        
    @is_admin.setter
    def is_admin(self, is_admin: bool) -> None:
        query = """
        UPDATE students
        SET is_admin = %s
        WHERE id = %s;
        """

        self.student_db.cursor.execute(query, (is_admin, self.id))
        self._is_admin = is_admin

        self.student_db.update_db()


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
            return []
        return output


class StudentDB:
    def __init__(self, service):
        self.connection = psycopg2.connect(**load_student_db_config())
        self.service = service
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
                         _is_inputting = student_info[4],
                         _main_message = student_info[5],
                         _main_message_first = student_info[6],
                         _is_admin=student_info[7],
                         student_db = self)
        
        return student
    
    def get_students_of_group(self, group: str) -> list[str]:
        query = """
        SELECT id, real_name FROM students
        WHERE "group" = %s
        """

        self.cursor.execute(query, (group, ))
        students = self.cursor.fetchall()

        if students is None:
            self.service.logger.warning("StudentBotService: No students found for group %s" % group)
            return []
        
        return students
    
    def parsed_students_list(self, group: str) -> str:
        students = self.get_students_of_group(group)
        output = ""
        for student in students:
            output += f"{student[1]}  [{student[0]}]\n\n"

        return output

    def student_exist(self, id: int) -> bool:
        return bool(self.get_student(id))

    def remove_student(self, id: int) -> None:
        query = """
        DELETE FROM students
        WHERE id = %s
        """

        self.cursor.execute(query, (id,))

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
        verification_text = f"Підтвердити нового користувача {name} [{client.id}] {client.real_name} to {client.group}?"
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Підтвердити", callback_data="verify_user")],
            [InlineKeyboardButton("Відхилити", callback_data="discard_user")],
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
        await self.service.send_raw(
            client.id,
            "Вас було підтверджено!")

        await Menu.main_menu(self.service, None, None, user_id=client.id)

    async def _send_client_verified_to_admins(self, client: Client, verifier: Client) -> None:
        telegram_username = await self.service.get_name_by_id(client.id)
        verified_admin_text = f"{verifier.real_name} підтвердив користувача {telegram_username} "\
                            f"[{client.id}] {client.real_name} до {client.group}."
        
        await self._admins_edit_message(client, verified_admin_text)

    async def discard(self, client: Client, verifier: Client) -> None:
        self.logger.info(f"StudentBotService: Discarded user {client.real_name} [{client.id}] from joining {client.group}")

        await self._client_send_discarded_message(client)
        await self._send_client_discarded_to_admins(client, verifier)

    async def _client_send_discarded_message(self, client: Client) -> None:
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Назад до реєстрації", callback_data="restart")],
        ])
        await self.service.send(
            client.id,
            "Ваш запит на перевірку відхилено.",
            reply_markup=reply_markup
        )

    async def _send_client_discarded_to_admins(self, client: Client, verifier: Client) -> None:
        telegram_username = await self.service.get_name_by_id(client.id)
        discarded_admin_text = f"{verifier.real_name} відхилив запит користувача {telegram_username} "\
                            f"[{client.id}] {client.real_name} до {client.group}."

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
    def __init__(self, service):
        self.connection = psycopg2.connect(**load_student_db_config())
        self.cursor = self.connection.cursor()
        self.service = service
        self.student_db = self.service.student_db

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
            self.service.logger.exception(f"StudentBotService: Schedule db error | {e}")
            rows = []
        finally:
            cur.close()
            conn.close()

        return rows

    async def user_send_schedule(self, user_id: int, day: str) -> None:
        client = self.student_db.get_student(user_id)
        week = self.get_week()

        schedule = self.get_schedule(client.group, day, week)

        if not schedule:
            await self.service.send(user_id, f"Не знайдено розкладу на {day}.")
            return
        
        schedule_info = ""
        for row in schedule:
            start_time = str(row[0])[:-3]
            subject = row[1]
            class_type = row[2]
            link = row[3]
            schedule_info += f"{start_time} {subject} - [{class_type}]({link})\n\n"

        try:
            await self.service.send(user_id, f"Розклад на {day.lower()}:\n\n{schedule_info}", parse_mode='MARKDOWN')
        except Exception as e:
            print(f"Error sending schedule: {e}")

    async def send_group_schedule(self, update: telegram.Update, context: CallbackContext, day: str) -> None:
        user = update.effective_user
        client = self.student_db.get_student(user.id)
        week = self.get_week()

        schedule = self.get_schedule(client.group, day, week)
        chat_type = update.effective_chat.type

        if chat_type == telegram.constants.ChatType.PRIVATE:
            send_command = self.service.send
        else:
            send_command = self.service.send_group

        if not schedule:
            await send_command(update.effective_chat.id, f"Не знайдено розкладу на {day}.")
            return

        schedule_info = ""
        for row in schedule:
            start_time = str(row[0])[:-3]
            subject = row[1]
            class_type = row[2]
            link = row[3]
            schedule_info += f"{start_time} {subject} - [{class_type}]({link})\n\n"

        try:
            await send_command(update.effective_chat.id, f"Розклад на {day.lower()}:\n\n{schedule_info}", parse_mode='MARKDOWN')
        except Exception as e:
            print(f"Error sending schedule: {e}")

    def get_week(self):
        return datetime.date.today().isocalendar()[1] % 2 + 1

    def get_current_day(self):
        days_of_week = {

            0: 'Понеділок',
            1: 'Вівторок',
            2: 'Середа',
            3: 'Четвер',
            4: "П'ятниця",
        }

        current_day = datetime.datetime.now().weekday()
        return days_of_week[current_day]


@dataclass
class Debt:
    subject: str
    text: str
    due_to_date: str
    user: int | None = None
    done: bool = False


class DebtsDB:
    def __init__(self, service) -> None:
        self.connection = psycopg2.connect(**load_debts_db_config())
        self.cursor = self.connection.cursor()
        self.service = service

    def add_debt(self, debt: Debt, group: str):
        students = self.service.student_db.get_students_of_group(group)

        for student_id in students:
            new_debt = copy(debt)
            new_debt.user = student_id

            self._add_debt(new_debt)

        self.connection.commit()

    def _add_debt(self, debt: Debt):
        self.cursor.execute("""
            INSERT INTO debts (due_to_date, subject, text, "user", done)
            VALUES (%s, %s, %s, %s, false)
        """, (debt.due_to_date, debt.subject, debt.text, debt.user))
        
    def get_debts(self, user_id: int) -> list[Debt]:
        self.cursor.execute("""
            SELECT subject, text, due_to_date, done
            FROM debts
            WHERE "user" = %s
            ORDER BY due_to_date ASC
        """, (user_id,))

        debts = self.cursor.fetchall()
        return [Debt(debt[0], debt[1], debt[2], user_id, debt[3]) for debt in debts]

    def build_debts_message_text(self, debts: list[Debt]) -> str:
        debts_str = ""

        if not debts:
            return "Clear"

        for i, debt in enumerate(debts):
            new_line = f"{i+1}. {debt.due_to_date}: {debt.subject}, {debt.text}"
            new_line = new_line.replace("~", "\\~").replace("-", "\\-").replace(".", "\\.")
            if debt.done:
                new_line = f"~{new_line}~"

            debts_str += new_line + "\n"

        return debts_str
    
    def mark_as_done(self, debt: Debt) -> None:
        self.cursor.execute("""
            UPDATE debts
            SET done = true
            WHERE subject = %s AND text = %s AND due_to_date = %s AND "user" = %s
        """, (debt.subject, debt.text, debt.due_to_date, debt.user))
        self.connection.commit()


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
    
    async def send_material(self, user_id: int) -> None:
        client = self.student_db.get_student(user_id)
        material = self.get_material(client.group)

        if not material:
            self.stud_bot.send(user_id, f"Немає матеріалів для {client.group}.")
            return

        material_info = ""
        for row in material:
            material_name = row[0]
            url = row[1]

            material_info += f"[{material_name}]({url})\n{'='*50}\n"

        try:
            await self.stud_bot.send(user_id, f"Матеріали для **{client.group}**:\n{material_info}", parse_mode="MARKDOWN")

        except Exception as e:
            print(f"Error sending material: {e}")



class StudentBotService:
    def __init__(self, setup_data: SetupServiceData) -> None:
        self.logger = setup_data.logger

        self.groups = "km31", "km32", "km33"
        self.admins = Admins(self)
        self.student_db = StudentDB(self)
        self.schedule_db = ScheduleDB(self)
        self.debts_db = DebtsDB(self)
        self.material_db = MaterialDB(self)
        self.groups_db = GroupsDB(self.logger)
        self.verification = Verification(self, self.student_db)
        self.app = ApplicationBuilder().token(get_token("StudentsBot")).build()

        setup_data.shared["bot_service"] = self
    
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
            telegram.BotCommand(command="/schedule", description="Send schedule for current day")
        ])

    def set_handlers(self) -> None:
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("menu", self.menu))
        self.app.add_handler(CommandHandler("admin", self.self_promote))
        self.app.add_handler(CommandHandler("forgetme", self.forget_me))
        self.app.add_handler(CommandHandler("schedule", self.send_schedule_for_today))
        self.app.add_handler(CallbackQueryHandler(self.button_controller))
        self.app.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, self.text_controller))
        self.app.add_handler(MessageHandler(filters.ALL, self.user_input_deleter))

    async def forget_me(self, update: telegram.Update, _context: CallbackContext) -> None:
        user = update.effective_user
        self.student_db.cursor.execute("""
            DELETE FROM students
            WHERE id = %s
        """, (user.id,))
        
        await delete_user_request_if_text(update)
        self.student_db.update_db()

    async def send_schedule_for_today(self, update: telegram.Update, context: CallbackContext) -> None:
        await self.user_input_deleter(update, context)
        await self.schedule_db.send_group_schedule(update, context, self.schedule_db.get_current_day())

    async def user_input_deleter(self, update: telegram.Update, context: CallbackContext) -> None:
        await delete_user_request_if_text(update)
        return telegram.ext.ConversationHandler.END

    async def self_promote(self, update: telegram.Update, _context: CallbackContext) -> None:
        await delete_user_request_if_text(update)
        self.student_db.get_student(update.effective_user.id).is_admin = True

    async def button_controller(self, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query

        if not self.student_db.student_exist(query.from_user.id):
            await query.answer(text="/start to start the bot")
            return

        name, args = self.parse_button_query(query.data)
        if hasattr(Button, name):
            await getattr(Button, name)(self, update, context, *args)
        else:
            self.logger.error(f"StudentBotService: Button: {name} not found. User: {query.from_user.name} | {query.message.to_json()}")
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
        if "run_input_on" not in context.chat_data:
            self.logger.error(f"StudentBotService: Error in text_controller. No effective functions have been specified | {update.effective_user.name} | {update.message.to_json()}")
            return telegram.ext.ConversationHandler.END

        effective_function = eval(context.chat_data["run_input_on"]) 

        user = update.effective_user
        client = self.student_db.get_student(user.id)

        if client is None or not client.is_inputting:
            await update.message.delete()
            return telegram.ext.ConversationHandler.END

        user_input = update.message.text
        client.is_inputting = False
        await update.message.delete()


        #if delete self, my tool will working
        await effective_function(self, update, context, user_input)

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
    
    async def send_group(self, usr_id: int, text: str, **kwargs) -> int:
        message = await self.app.bot.send_message(usr_id, text, **kwargs)
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
        if update.effective_chat.type == telegram.constants.ChatType.PRIVATE:
            await self.start_in_private_chat(update, context)
        elif update.effective_chat.type == telegram.constants.ChatType.GROUP:
            await self.start_in_group(update, context)
        else:
           await self.send_group(update.effective_chat.id, "Цей вид чату не підтримується")

    async def start_in_private_chat(self, update: telegram.Update, context: CallbackContext) -> None:
        user = update.effective_user
        
        if (self.student_db.student_exist(user.id) and
            self.student_db.get_student(user.id).is_verified):

            await self.menu(update, context)
            return

        self.logger.info(f"StudentBotService: Started with {user.name}")

        await delete_user_request_if_text(update)
        await self.init_user(user.id)

        await Menu.group_choice_menu(self, update, context)

    async def start_in_group(self, update: telegram.Update, context: CallbackContext) -> None:
        client = self.student_db.get_student(update.effective_user.id)
        group_id = update.effective_chat.id
        if client is None:
            await self.send_group(group_id, "Ви маєте бути зареєстрованими для активації бота в групі")
            return

        if not client.is_admin:
            await self.send_group(group_id, "Ви маєте бути адміністратором для активації бота в групі")
            return
        
        if self.groups_db.group_exists(group_id):
            await self.send_group(group_id, "Групу вже встановлено")
            return
        
        self.groups_db.add_group(group_id, client.group)
        await self.send_group(group_id, f"Групу встановлено для {client.group}")

    async def init_user(self, usr_id: int) -> None:
        if self.student_db.student_exist(usr_id):
            return
        
        self.student_db.add_student(usr_id)

    async def get_name_by_id(self, usr_id: int) -> str:
        user = await self.app.bot.get_chat_member(usr_id, usr_id)
        return user.user.name

    async def send_for_all_students(self, usr_id: int, group: str, text: str, **kwargs) -> None:
        students = self.student_db.get_students_of_group(group)
        for student in students:
            if student[0] == usr_id:
                await self.send(usr_id, 'Повідомлення було відправленно', **kwargs)
                continue
            await self.send_raw(student[0], text, **kwargs)

    async def store_message(self, update: telegram.Update, context: CallbackContext, user_input: str) -> None:
        context.chat_data["stored_message"] = user_input
        client = self.student_db.get_student(update.effective_user.id)

        await self.send_for_all_students(client.id, client.group, user_input)
        await self.send(update.effective_user.id, "Повідомлення збережено!")

        return user_input

    async def get_chat_name_by_id(self, group_id: int) -> str:
        chat = await self.app.bot.get_chat(group_id)
        return chat.title


class Menu:
    @staticmethod
    async def group_choice_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("KM-31", callback_data="choose_group(km31)")],
            [InlineKeyboardButton("KM-32", callback_data="choose_group(km32)")],
            [InlineKeyboardButton("KM-33", callback_data="choose_group(km33)")],
        ])
        await service.send(update.effective_user.id, "Виберіть свою групу:", reply_markup=reply_markup)

    @staticmethod
    async def enter_name_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await service.send(update.effective_user.id, "Введіть ваше повне ім'я:")
        client = service.student_db.get_student(query.from_user.id)
        client.is_inputting = True
        context.chat_data["run_input_on"] = "Menu.confirmation_menu"
        
    @staticmethod
    async def confirmation_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext, usr_name: str) -> None:
        client = service.student_db.get_student(update.effective_user.id)
        client.real_name = usr_name

        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Надіслати на перевірку", callback_data="confirm")],
            [InlineKeyboardButton("Змінити дані", callback_data="restart")]])
        await service.send(client.id, f"Ви {client.real_name} з {client.group}. Правильно?", reply_markup=reply_markup)

    @staticmethod
    async def schedule_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Понеділок", callback_data="schedule_day(Понеділок)")],
            [InlineKeyboardButton("Вівторок", callback_data="schedule_day(Вівторок)")],
            [InlineKeyboardButton("Середа", callback_data="schedule_day(Середа)")],
            [InlineKeyboardButton("Четвер", callback_data="schedule_day(Четвер)")],
            [InlineKeyboardButton("П'ятниця", callback_data="schedule_day(П'ятниця)")],
            [InlineKeyboardButton("Назад", callback_data="restart")],

        ])
        await service.send(update.effective_user.id, "Введіть день:", reply_markup=reply_markup)

    @staticmethod
    async def options_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        await service.send(update.effective_user.id, "<Options>")

    @staticmethod
    async def main_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext, user_id=None) -> None:
        if user_id is not None:
            client = service.student_db.get_student(user_id)
        else:
            client = service.student_db.get_student(update.effective_user.id)

        keyboard = [
            [InlineKeyboardButton("Розклад", callback_data="schedule")],
            [InlineKeyboardButton("Матеріали", callback_data="materials")],
            [InlineKeyboardButton("Борги", callback_data="debts")],
        ]

        if client.is_admin:
            keyboard.append([InlineKeyboardButton("Адмін-панель", callback_data="admin_panel")])

        reply_markup = telegram.InlineKeyboardMarkup(keyboard)
        await service.send(client.id, "Вітаю у меню", reply_markup=reply_markup)

    @staticmethod
    async def admin_panel(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        keyboard = [
            [InlineKeyboardButton("Повідомлення студентам", callback_data="request_message_input")],
            [InlineKeyboardButton("Видалити студента", callback_data="delete_student_button")],
            [InlineKeyboardButton("Список студентів", callback_data="send_lst_of_students_button")],
            [InlineKeyboardButton("Посилання", callback_data="links_menu")],
            [InlineKeyboardButton("Чати", callback_data="chats_admin_view")],
            [InlineKeyboardButton("Назад", callback_data="restart")],
        ]

        reply_markup = telegram.InlineKeyboardMarkup(keyboard)
        await service.send(update.effective_user.id, "Вітаю у меню для старост", reply_markup=reply_markup)

    @staticmethod
    async def send_students_message_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        client = service.student_db.get_student(update.effective_user.id)
        client.is_inputting = True
        context.chat_data["run_input_on"] = 'StudentBotService.store_message'

        await service.send(update.effective_user.id, "Введіть повідомлення для відправки студентам:")

    @staticmethod
    async def delete_student_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        client = service.student_db.get_student(update.effective_user.id)
        students = service.student_db.get_students_of_group(client.group)

        keyboard = [
        [InlineKeyboardButton(student_name, callback_data=f"delete_students('{student_id}')")]
            for student_id, student_name in students
        ]

        keyboard.append([InlineKeyboardButton("Назад", callback_data="admin_panel")])

        reply_markup = telegram.InlineKeyboardMarkup(keyboard)
        await service.send(update.effective_user.id, "Оберіть людину для видалення", reply_markup=reply_markup)

    @staticmethod
    async def debts_admin_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Мої борги", callback_data="debts_list")],
            [InlineKeyboardButton("Додати борг", callback_data="add_debt")],
            [InlineKeyboardButton("Назад", callback_data="menu")],
        ])

        await service.send(update.effective_user.id, "Борги", reply_markup=reply_markup)

    @staticmethod
    async def debts_list_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        debts = service.debts_db.get_debts(update.effective_user.id)
        context.chat_data["debts"] = debts
        text = service.debts_db.build_debts_message_text(debts)

        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Позначити готовим", callback_data="debts_mark_as_done")],
            [InlineKeyboardButton("Повернутися в меню", callback_data="menu")],
        ])

        await service.send(update.effective_user.id, text, reply_markup=reply_markup, parse_mode='MarkdownV2')

    @staticmethod
    async def confirm_new_debt_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext, usr_input: str) -> None:
        subject, text, date = Menu._parse_debt_input(usr_input)
        context.chat_data["debt_subject"] = subject
        context.chat_data["debt_text"] = text
        context.chat_data["debt_date"] = date

        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Так", callback_data="confirm_new_debt")],
            [InlineKeyboardButton("Ні", callback_data="back_to_menu_with_message(Adding debt aborted)")],
        ])

        await service.send(update.effective_user.id,
                           f"Тема: {subject}\nТекст: {text}\nДата: {date}\nПравильно?",
                           reply_markup=reply_markup)

    @staticmethod
    def _parse_debt_input(usr_input: str) -> tuple[str, str, str]:
        subject, other = usr_input.split(":")
        text, date = other.split("|")
        return subject.strip(), text.strip(), date.strip()

    @staticmethod
    async def mark_as_done_confirm_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext, usr_input: str) -> None:
        debts = context.chat_data["debts"]
        try:
            index = int(usr_input)
            if index < 1:
                raise IndexError("Too low")
            
            debt = debts[index - 1]
        except (ValueError, IndexError):
            return await Menu._incorrect_debt_index_menu(service, update.effective_user.id)

        service.debts_db.mark_as_done(debt)
        await Menu.debts_list_menu(service, update, context)

    @staticmethod
    async def _incorrect_debt_index_menu(service: StudentBotService, client_id: int) -> None:
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Повернутися в меню", callback_data="menu")]
        ])
        await service.send(client_id, "Некоректний номер", reply_markup=reply_markup)

    @staticmethod
    async def admin_material_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Посилання на google sheets", url="https://docs.google.com/spreadsheets/d/1bfFIgVgv-dDK0HOcMw1qr861vWI8IXJyTEzcDGYMDDc/edit?gid=47762859#gid=47762859")],
            [InlineKeyboardButton("Подивитися матеріали", callback_data="view_material")],
            [InlineKeyboardButton("Назад", callback_data="restart")],
        ])
        await service.send(update.effective_user.id, "Оберіть опцію:", reply_markup=reply_markup)

    @staticmethod
    async def chats_admin_view_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        client = service.student_db.get_student(update.effective_user.id)
        groups = list(service.groups_db.get_groups(client.group))

        if len(groups) == 0:
            back_reply_markup = telegram.InlineKeyboardMarkup([
                [InlineKeyboardButton("Назад", callback_data="admin_panel")],
            ])
            await service.send(
                client.id,
                "Чатів не знайдено. Напишіть /start у чаті щоб прив'язати",
                reply_markup=back_reply_markup)
            return

        reply_markup = telegram.InlineKeyboardMarkup(
            [[InlineKeyboardButton(
                await service.get_chat_name_by_id(group.id),
                callback_data=f"choose_chat({group.id})")
            ] for group in groups] +
            [[InlineKeyboardButton("Назад", callback_data="admin_panel")]]
        )

        await service.send(client.id, "Оберіть чат:", reply_markup=reply_markup)

    @staticmethod
    async def chat_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext, chat_id: str) -> None:
        client = service.student_db.get_student(update.effective_user.id)
        group = service.groups_db.get_group(chat_id)
        chat_name = await service.get_chat_name_by_id(chat_id)

        morning_day_schedule_text = ("🗹" if group.morning_day_schedule else "☐") + " Надсилати розклад зранку"
        morning_day_schedule_checkbox = InlineKeyboardButton(
            morning_day_schedule_text,
            callback_data=f"toggle_chat_option(morning_day_schedule,{group.id})")

        a_few_days_reminder_text = ("🗹" if group.a_few_days_reminder else "☐") + " Нагадування про дедлайн"
        a_few_days_reminder_checkbox = InlineKeyboardButton(
            a_few_days_reminder_text,
            callback_data=f"toggle_chat_option(a_few_days_reminder,{group.id})")

        reply_markup = telegram.InlineKeyboardMarkup([
            [morning_day_schedule_checkbox],
            [a_few_days_reminder_checkbox],
            [InlineKeyboardButton("Відв'язати чат", callback_data=f"forget_chat({chat_id})")],
            [InlineKeyboardButton("Назад", callback_data="chats_admin_view")],
        ])
        
        await service.send(client.id, f"{chat_name}", reply_markup=reply_markup)


class Button:
    @staticmethod
    async def choose_group(service: StudentBotService, update: telegram.Update, context: CallbackContext, group: str) -> None:
        query = update.callback_query
        client = service.student_db.get_student(query.from_user.id)
        client.group = group
        await query.answer()
        await Menu.enter_name_menu(service, update, context)

    @staticmethod 
    async def delete_student_button(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        await Menu.delete_student_menu(service, update, context)

    # TODO confirm menu
    @staticmethod
    async def delete_students(service: StudentBotService, update: telegram.Update, context: CallbackContext, id_: str) -> None:
        query = update.callback_query
        await query.answer()
        id_ = id_.replace('"', '').replace("'", '')
        await service.send_raw(id_, "Вас було видаленно з бази даних.")
        service.student_db.remove_student(id_)
        await service.send(update.effective_user.id, "Студента видалено з бази даних.")

    @staticmethod
    async def send_lst_of_students_button(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        client = service.student_db.get_student(query.from_user.id)
        await query.answer()
        students = service.student_db.parsed_students_list(client.group)

        await service.send(update.effective_user.id, students)

    @staticmethod
    async def restart(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        await StudentBotService.start(service, update, context)

    @staticmethod
    async def admin_panel(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        await Menu.admin_panel(service, update, context)

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
        await service.schedule_db.user_send_schedule(user_id, day)

    @staticmethod
    async def options(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        await Menu.options_menu(service, update, context)

    @staticmethod
    async def confirm(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        await service.send(update.effective_user.id, "Запит на перевірку надіслано. Чекайте підтвердження!")
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
    async def debts(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        client = service.student_db.get_student(query.from_user.id)
        
        if client.is_admin:
            return await Menu.debts_admin_menu(service, update, context)

        return await Menu.debts_list_menu(service, update, context)

    @staticmethod
    async def debts_list(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        await Menu.debts_list_menu(service, update, context)

    @staticmethod
    async def add_debt(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        client = service.student_db.get_student(query.from_user.id)
        client.is_inputting = True
        context.chat_data["run_input_on"] = "Menu.confirm_new_debt_menu.__(self)"

        await service.send(update.effective_user.id, "Введіть <тема>: <текст> | <день>/<місяць>/<рік>")

    @staticmethod
    async def confirm_new_debt(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        # DONT NEED query.answer since its done
        # in back_to_menu_with_message later

        client = service.student_db.get_student(query.from_user.id)

        subject = context.chat_data["debt_subject"]
        text = context.chat_data["debt_text"]
        due_to_date = context.chat_data["debt_date"]
        debt = Debt(subject, text, due_to_date)

        service.debts_db.add_debt(debt, client.group)
        await Button.back_to_menu_with_message(service, update, context, "Борг додан")

    @staticmethod
    async def back_to_menu_with_message(service: StudentBotService, update: telegram.Update, context: CallbackContext, message: str) -> None:
        query = update.callback_query
        await query.answer()
        
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Повернутися в меню", callback_data="menu")]
        ])

        await service.send(update.effective_user.id, message, reply_markup=reply_markup)

    @staticmethod
    async def debts_mark_as_done(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        client = service.student_db.get_student(query.from_user.id)
        client.is_inputting = True
        context.chat_data["run_input_on"] = "Menu.mark_as_done_confirm_menu.__(self)"

        await service.send(update.effective_user.id, "Введіть номер:")

    @staticmethod
    async def materials(service: StudentBotService, update: telegram.Update, context: CallbackContext):
        client = service.student_db.get_student(update.effective_user.id)
        query = update.callback_query
        user_id = query.from_user.id

        if client.is_admin:
            await Menu.admin_material_menu(service, update, context)
            return
        
        await service.material_db.send_material(user_id)

    @staticmethod
    async def view_material(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()
        await service.material_db.send_material(user_id)

    @staticmethod
    async def send_link_material(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()
        text = "[Таблиця з матеріалами](https://docs.google.com/spreadsheets/d/1bfFIgVgv-dDK0HOcMw1qr861vWI8IXJyTEzcDGYMDDc/edit?gid=47762859#gid=47762859)"
        await service.send(user_id, text, parse_mode="MARKDOWN")

    @staticmethod
    async def links_menu(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        reply_markup = telegram.InlineKeyboardMarkup([
            [InlineKeyboardButton("Матеріали (Посилання)", url="https://docs.google.com/spreadsheets/d/1bfFIgVgv-dDK0HOcMw1qr861vWI8IXJyTEzcDGYMDDc/edit?gid=0#gid=0")],
            [InlineKeyboardButton("Розклад (Посилання)", url="https://docs.google.com/spreadsheets/d/1gsxm1onrT76UYZxuT7b-qyO-haWiWk7igKwvSB0LLbg/edit?gid=0#gid=0")],
            [InlineKeyboardButton("Назад", callback_data="restart")],
        ])
        await service.send(update.effective_user.id, "Оберіть опцію:", reply_markup=reply_markup)

    @staticmethod
    async def request_message_input(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()

        await Menu.send_students_message_menu(service, update, context)

    @staticmethod
    async def chats_admin_view(service: StudentBotService, update: telegram.Update, context: CallbackContext) -> None:
        query = update.callback_query
        await query.answer()
        await Menu.chats_admin_view_menu(service, update, context)

    @staticmethod
    async def choose_chat(service: StudentBotService, update: telegram.Update, context: CallbackContext, group_id: int) -> None:
        query = update.callback_query
        await query.answer()
        await Menu.chat_menu(service, update, context, group_id)

    @staticmethod
    async def toggle_chat_option(service: StudentBotService, update: telegram.Update, context: CallbackContext, option: str, group_id: int) -> None:
        query = update.callback_query
        await query.answer()

        group = service.groups_db.get_group(group_id)
        
        if option == "morning_day_schedule":
            group.morning_day_schedule = not group.morning_day_schedule
        elif option == "a_few_days_reminder":
            group.a_few_days_reminder = not group.a_few_days_reminder
        else:
            service.logger.error(f"StudentBotService: unknown option {option} in toggle_chat_option")
        
        await Menu.chat_menu(service, update, context, group_id)

    @staticmethod
    async def forget_chat(service: StudentBotService, update: telegram.Update, context: CallbackContext, group_id: int) -> None:
        query = update.callback_query
        await query.answer()

        service.groups_db.delete_group(group_id)
        await Menu.chats_admin_view_menu(service, update, context)
