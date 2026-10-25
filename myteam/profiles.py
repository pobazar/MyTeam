import re
import unicodedata
from django import forms
from .models import Person, TeamGroup

CYR = dict(zip('абвгдеёзийклмнопрстуфхцыэ', ['a','b','v','g','d','e','e','z','i','i','k','l','m','n','o','p','r','s','t','u','f','h','c','y','e']))
CYR.update({'ж':'zh','ч':'ch','ш':'sh','щ':'sch','ю':'yu','я':'ya','ь':'','ъ':''})
def normalized(value):
    value = unicodedata.normalize('NFKC', value).casefold()
    return ' '.join(re.findall(r'[a-z0-9]+', ''.join(CYR.get(c,c) for c in value)))

def team_identity(raw):
    # Generic word translation, never a directory of team names. Unknown words remain separate.
    vocabulary={'komanda':'team','podderzhka':'support','razrabotka':'development','razrabotki':'development','prodazh':'sales','prodazhi':'sales','analitika':'analytics','analitiki':'analytics','klientskaya':'customer','klientskoi':'customer','rosta':'growth','rost':'growth'}
    key = ' '.join(vocabulary.get(word,word) for word in normalized(raw).split())
    tokens = key.split()
    compact = ''.join(tokens)
    # Exact transliteration and punctuation; conservative abbreviation against existing names.
    if not compact:return None,'uncertain'
    all_groups = list(TeamGroup.objects.all())
    for group in all_groups:
        if group.canonical.replace(' ','') == compact or sorted(group.canonical.split())==sorted(tokens) or ''.join(sorted(group.canonical.split()))==compact:
            return group, 'exact'
    matches = [g for g in all_groups if len(compact) >= 3 and len(g.canonical.split()) >= 3 and ''.join(w[0] for w in g.canonical.split()) == compact]
    if len(matches) == 1:
        return matches[0], 'abbreviation'
    if len(matches) > 1:
        return None, 'uncertain'
    if len(tokens) >= 3:
        acronym = ''.join(w[0] for w in tokens)
        short = [g for g in all_groups if g.canonical == acronym and len(acronym)>=3]
        if len(short)==1:
            group = short[0]
            group.canonical = key
            group.save(update_fields=['canonical'])
            return group,'abbreviation'
    return TeamGroup.objects.get_or_create(canonical=key)[0], 'separate'

CITY_ALIASES = {'moscow':('Москва','moskva'),'moskva':('Москва','moskva'),'saint petersburg':('Санкт-Петербург','sankt peterburg'),'sankt peterburg':('Санкт-Петербург','sankt peterburg'),'spb':('Санкт-Петербург','sankt peterburg'),'london':('Лондон','london'),'london gorod':('Лондон','london')}
def normalize_city(raw):
    key = normalized(raw)
    if key in ('', 'springfield', 'novgorod'):
        raise forms.ValidationError('Уточните город: укажите полное название и регион или страну.')
    return CITY_ALIASES.get(key, (raw.strip(),key))

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Person
        fields = ['full_name','team','city']
        labels = {'full_name':'Как вас зовут','team':'Команда','city':'Город, где вы сейчас'}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if self.instance.pk:self.initial['full_name']=self.instance.display_name
        self.fields['full_name'].widget.attrs['autocomplete']='name'
        for field in self.fields.values():field.required=True
    def clean_city(self):
        value=self.cleaned_data['city'].strip()
        self.city_normalized=normalize_city(value)
        return value
    def save(self,commit=True):
        p=super().save(commit=False)
        p.team_group,p.team_confidence=team_identity(p.team)
        p.city,p.city_key=self.city_normalized
        if commit:p.save()
        return p
