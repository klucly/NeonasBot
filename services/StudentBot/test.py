import datetime

def get_current_day():
        days_of_week = {
        0: 'Понеділок',
        1: 'Вівторок',
        2: 'Середа',
        3: 'Четвер',
        4: 'П’ятниця',
        5: 'Субота',
        6: 'Неділя'
        }
        
        current_day = datetime.datetime.now().weekday()
        return days_of_week[current_day]


print(get_current_day())