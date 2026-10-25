"""Direct participant profile links; this module never sends bot messages."""
import re

def participant_url(snapshot):
    username=snapshot.get('username','')
    if isinstance(username,str) and re.fullmatch(r'[A-Za-z0-9_]{5,32}',username):
        return 'https://t.me/'+username
    telegram_id=snapshot.get('telegram_id')
    if type(telegram_id) is int and telegram_id>0:
        return f'tg://user?id={telegram_id}'
    return None
