"""Invitation buttons use the same enrollment rules as the web API."""
import uuid
from django.db import transaction
from .models import Notification,Enrollment
from .rounds import enroll,RuleError
from .user_messages import invitation
from .telegram import call,DeliveryError


def handle_callback(callback,clock):
    sender=callback.get('from',{})
    message=callback.get('message',{})
    chat=message.get('chat',{})
    notice=None
    error='Это приглашение недоступно.'
    try:
        prefix,round_id,action=callback.get('data','').split(':')
        round_id=uuid.UUID(round_id)
    except (ValueError,AttributeError):
        round_id=None;action=None;prefix=None
    if (prefix=='enroll' and action in ('yes','no') and round_id and
        chat.get('type')=='private' and sender.get('id')==chat.get('id') and not sender.get('is_bot')):
        notice=Notification.objects.filter(kind='signup_invite',round_id=round_id,
            person__telegram_id=sender.get('id'),chat_id=chat.get('id'),status='sent',
            telegram_message_id=message.get('message_id')).first()
        if notice:
            try:enroll(notice.person_id,round_id,action=='yes',clock)
            except RuleError as exc:error=str(exc)
            else:error=None
    notice_id=notice.id if notice else None
    callback_id=callback.get('id')
    transaction.on_commit(lambda: respond(callback_id,notice_id,error,clock))


def respond(callback_id,notice_id,error,clock):
    # Read the durable current state, rather than trusting callback text or the requested action.
    notice=Notification.objects.select_related('round').filter(pk=notice_id).first() if notice_id else None
    active=bool(notice and Enrollment.objects.filter(person_id=notice.person_id,round=notice.round,active=True).exists())
    if callback_id:
        try:call('answerCallbackQuery',{'callback_query_id':callback_id,'text':error or ('Ты записан.' if active else 'Ты не участвуешь.')})
        except DeliveryError:pass
    if not notice:return
    closed=notice.round.state!='open' or clock.now()>=notice.round.closes_at
    text,payload=invitation(notice.round,active=active,closed=closed)
    try:call('editMessageText',{'chat_id':notice.chat_id,'message_id':notice.telegram_message_id,
        'text':text,'parse_mode':'HTML','link_preview_options':{'is_disabled':True},**payload})
    except DeliveryError:pass  # Enrollment is durable; retrying a button is safe even if editing failed.
