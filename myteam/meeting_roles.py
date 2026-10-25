"""Stable organizer selection, including published meetings created before this feature."""
import hashlib

def organizer_id(meeting,members):
    ids={str(member.person_id) for member in members}
    saved=(meeting.activity_data or {}).get('organizer_person_id')
    if saved in ids:return saved
    # Per-meeting deterministic choice: stable for all viewers and across retries.
    return min(ids,key=lambda person:hashlib.sha256(f'{meeting.id}:{person}'.encode()).digest()) if ids else None

def persist_organizer(meeting,members):
    selected=organizer_id(meeting,members)
    if selected and (meeting.activity_data or {}).get('organizer_person_id')!=selected:
        meeting.activity_data={**(meeting.activity_data or {}),'organizer_person_id':selected}
        meeting.save(update_fields=['activity_data'])
    return selected
