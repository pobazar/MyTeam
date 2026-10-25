from html import escape
from .models import Member
from .notifications import enqueue

def send_contacts(sender_id,chat_id,meeting_id,update_id):
    own=Member.objects.filter(person__telegram_id=sender_id,meeting_id=meeting_id,round__published_at__isnull=False).select_related('person','round').first()
    if not own:return False
    others=own.meeting.members.exclude(person=own.person)
    lines=['МАЙТИМ · участники твоей встречи:']
    for m in others:
        s=m.snapshot
        # Telegram supports inline ID mentions for people who previously contacted this bot.
        lines.append(f'<a href="tg://user?id={int(s["telegram_id"])}">{escape(s.get("full_name") or (s["first_name"]+" "+s["last_name"]))}</a> · '+escape(s['team']))
    lines.append('Нажми на имя, чтобы открыть профиль и написать в Telegram.')
    enqueue(f'contacts:{update_id}','contacts',chat_id,'\n'.join(lines),own.person,own.round)
    return True
