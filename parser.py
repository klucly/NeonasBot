import re
import psycopg2
from google.oauth2 import service_account
from googleapiclient.discovery import build


SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
SERVICE_ACCOUNT_FILE = './data/credentials_google_service.json'

credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
service = build('drive', 'v3', credentials=credentials)
document_id = '1saaxjnbaTq-SiPu-wy_zUqth1wu-irq0GGV5mCinYA8'

response = service.files().export(fileId=document_id,mimeType='text/plain').execute()


content = response.decode('utf-8')
cleaned_content = re.sub(r'[\n\r]', ' ', content)

schedule_monday =re.findall(r"\bПонеділок.*?(?=\bВівторок\:|#)",cleaned_content)
schedule_tuesday = re.findall(r"\bВівторок.*?(?=\bСереда\:|#)",cleaned_content)
schedule_wednesday = re.findall(r"\bСереда.*?(?=\bЧетвер\:|#)",cleaned_content)
schedule_thursday = re.findall(r"\bЧетвер.*?(?=\bП.ятниця\:|#)",cleaned_content)
schedule_friday = re.findall(r"\bП.ятниця.*?(?=\bСубота\:|#)",cleaned_content)
schedule_saturday = re.findall(r"\bСубота.*?(?=\bНеділя|#)",cleaned_content)
schedule_sunday = re.findall(r"\bНеділя.*?(?=#)",cleaned_content)

schdedule_pattern = re.compile(r"(?P<class>[0-9]\.)\s+?(?P<time>\([1-2]?[0-9]\:[0-5][0-9]\))(?P<subj>((?!\()\s+\b\w+\b(?!\))){1,}?)\s+?(?P<type>\(\w+\))\s+?(?P<link>\(https://\w+\S+\))")

schedule_parsed = []

if len(schedule_monday) != 0:
    schedule_monday_parsed = schdedule_pattern.findall(schedule_monday[0])
    schedule_monday_parsed.insert(0,"Понеділок")
    schedule_parsed.append(schedule_monday_parsed)
if len(schedule_tuesday) != 0:
    schedule_tuesday_parsed = schdedule_pattern.findall(schedule_tuesday[0])
    schedule_tuesday_parsed.insert(0,"Вівторок")
    schedule_parsed.append(schedule_tuesday_parsed)
if len(schedule_wednesday) != 0:
    schedule_wednesday_parsed = schdedule_pattern.findall(schedule_wednesday[0])
    schedule_wednesday_parsed.insert(0,"Середа")
    schedule_parsed.append(schedule_wednesday_parsed)
if len(schedule_thursday) != 0:
    schedule_thursday_parsed = schdedule_pattern.findall(schedule_thursday[0])
    schedule_thursday_parsed.insert(0,"Четвер")
    schedule_parsed.append(schedule_thursday_parsed)
if len(schedule_friday) != 0:
    schedule_friday_parsed = schdedule_pattern.findall(schedule_friday[0])
    schedule_friday_parsed.insert(0,"П'ятниця")
    schedule_parsed.append(schedule_friday_parsed)
if len(schedule_saturday) != 0:
    schedule_saturday_parsed = schdedule_pattern.findall(schedule_saturday[0])
    schedule_saturday_parsed.insert(0,"Субота")
    schedule_parsed.append(schedule_saturday_parsed)
if len(schedule_sunday) != 0:
    schedule_sunday_parsed = schdedule_pattern.findall(schedule_sunday[0])
    schedule_sunday_parsed.insert(0,"Неділя")
    schedule_parsed.append(schedule_sunday_parsed)


# print(cleaned_content)
# print(schedule_monday)
# print(schedule_monday_parsed)
# print(schedule_wednesday_parsed)
                                  

db_name = "postgres"
user_db = "postgres"
password_db = "matan1mbA" 


db_connnection = psycopg2.connect(f"dbname={db_name} user={user_db} password={password_db}")

db_cursor = db_connnection.cursor()

db_cursor.execute("CREATE TABLE schedule2 (Day varchar, Class integer, Time varchar, Subject varchar, Type varchar);")
db_cursor.execute("CREATE TABLE lessonlinks (Subject varchar, Type varchar, Link varchar);")


for i in range(len(schedule_parsed)):
    day_content = schedule_parsed[i]
    for j in range(1,len(day_content)):
        lesson_values = day_content[j]
        db_cursor.execute("INSERT INTO schedule2 (Day,Class,Time,Subject,Type) VALUES (%s,%s,%s,%s,%s)",(day_content[0].strip(), 
                                                                               re.sub(r"[. ]",'',lesson_values[0]).strip(),
                                                                               re.sub(r"[() ]",'',lesson_values[1].strip()),
                                                                               lesson_values[2].strip(),
                                                                               re.sub(r"[() ]",'',lesson_values[4].strip())))
for i in range(len(schedule_parsed)):
    day_content = schedule_parsed[i]
    for j in range(1,len(day_content)):
        lesson_values = day_content[j]
        db_cursor.execute("INSERT INTO lessonlinks (Subject,Type,Link) VALUES (%s,%s,%s)",(
                                                                               re.sub(r"[.]",'',lesson_values[2].strip()),
                                                                               re.sub(r"[()]",'',lesson_values[4].strip()),
                                                                               re.sub(r"[()]",'',lesson_values[5].strip())))



# db_connnection.commit()

db_cursor.execute("SELECT * FROM schedule2;")
print(db_cursor.fetchall())

print()

db_cursor.execute("SELECT * FROM lessonlinks;")
print(db_cursor.fetchall())




db_cursor.close()
db_connnection.close()












