"""User notification templates shared by scheduling and Telegram callbacks."""
from html import escape
from .activities import get_activity
from .contacts import participant_url
from .pages import web_url

def link_button(text,path):
    return {'reply_markup':{'inline_keyboard':[[{'text':text,'url':web_url(path)}]]}}

def assignment(r,meeting,members,organizer,recipient):
    activity=get_activity(r.activity,r.rules_version)
    names=[]
    for member in members:
        s=member.snapshot
        name=escape(s.get('full_name') or (s.get('first_name','')+' '+s.get('last_name','')).strip())
        url=participant_url(s)
        if url:name=f'<a href="{escape(url,quote=True)}">{name}</a>'
        names.append(name+' · '+escape(s['team'])+(' · организатор' if str(member.person_id)==organizer else ''))
    own_instructions=getattr(activity,'organizer_instructions',lambda:'')() if str(recipient.person_id)==organizer else ''
    instructions=activity.instructions(len({m.snapshot['city_key'] for m in members})==1)
    text=escape(r.activity_title)+'\nТвоя активность на эту неделю!\n\nУчастники:\n'+'\n'.join(names)+'\n\n'+escape(own_instructions+instructions)
    payload=link_button('Открыть активность',f'/meetings/{meeting.id}/')
    game_url=getattr(activity,'game_url',None)
    if game_url:payload['reply_markup']['inline_keyboard'].append([{'text':'Открыть '+activity.title,'url':game_url}])
    return text,payload

def unmatched(r):
    return (escape(r.activity_title)+'\n\nНа этой неделе не собралось достаточно участников для активности. Попробуем в следующий раз!\n\nНа следующую неделю нужно записаться отдельно.',link_button('Открыть МАЙТИМ','/'))

def feedback_request(r,member):
    return (escape(r.activity_title)+'\n\nКак прошла активность? Поделись результатом — это поможет сделать следующие активности интереснее.',link_button('Оставить оценку',f'/meetings/{member.meeting_id}/feedback/'))

def invitation(r,active=None,closed=False):
    text=escape(r.activity_title)+'\n\nПрисоединишься к активности на следующей неделе?'
    if active is not None:text+='\n\n'+('Ты записан.' if active else 'Ты не участвуешь.')
    if closed:text+='\nЗапись закрыта.'
    buttons=[] if closed else [[{'text':'Записаться','callback_data':f'enroll:{r.id}:yes'},{'text':'Отказаться','callback_data':f'enroll:{r.id}:no'}]]
    return text,{'reply_markup':{'inline_keyboard':buttons}}
