"""GeoGuesser is played together over screen sharing, outside MyTeam."""
from itertools import combinations
import random
from .base import WeeklyActivity

GAME_URL='https://geoguesser.io/'


def group_sizes(count):
    if count<3:return []
    sizes=[3]*(count//3)
    for i in range(count%3):sizes[i%len(sizes)]+=1
    return sizes


def make_groups(people,history,rng=None):
    rng=rng or random.SystemRandom()
    sizes=group_sizes(len(people))
    if not sizes:return []
    people=list(people)
    best=None
    # Soft preferences only: every candidate includes every signed-up person.
    # History includes meetings across all MyTeam activities.
    for _ in range(32):
        rng.shuffle(people);groups=[];offset=0
        for size in sizes:groups.append(people[offset:offset+size]);offset+=size
        repeat=recency=teams=0
        for group in groups:
            for a,b in combinations(group,2):
                pair=frozenset((a.id,b.id))
                repeat+=int(pair in history);recency+=history.get(pair,0)
                teams+=int(a.team_group_id is not None and a.team_group_id==b.team_group_id)
        score=(repeat,recency,teams)
        if best is None or score<best[0]:best=(score,groups)
    return best[1]


class GeoGuesser(WeeklyActivity):
    key='geoguesser'
    version=1
    title='GeoGuesser'
    minimum_participants=3
    achievement_key='first_geoguesser'
    signup_only=False
    card_template='myteam/activity_details.html'
    game_url=GAME_URL

    def build_groups(self,people,history,rng=None):return make_groups(people,history,rng)

    def valid_distribution(self,count,sizes,unmatched):
        return sorted(sizes)==sorted(group_sizes(count)) and unmatched==(count if count<3 else 0)

    def organizer_instructions(self):
        return ('Ты организуешь эту встречу: предложи время, создай звонок, открой игру и поделись экраном. '
            'Помогай всем включаться в обсуждение: приглашай тех, кто ещё не высказался, оставляй время на разные версии '
            'и мягко возвращай разговор к совместному поиску, если кто-то увлёкся. '
            'Тебе не нужно знать правильные ответы — вы исследуете мир вместе.\n\n')

    def instructions(self,same_city):
        return ('Попутешествуйте вместе в GeoGuesser — игре, где нужно угадать место по панорамам. '
            'Рассматривайте улицы, замечайте детали и обсуждайте, в какой точке мира вы оказались.\n\n'
            'Договоритесь в Telegram об удобном времени и созвонитесь. Организатор откроет geoguesser.io и поделится экраном. '
            'Вместе ищите подсказки: вывески, дорожные знаки, архитектуру и природу. Обсуждайте версии и выбирайте ответ сообща.\n\n'
            'Здесь интереснее искать вместе, чем угадывать в одиночку. Делитесь наблюдениями, спрашивайте мнение друг друга '
            'и давайте каждому высказаться — даже неожиданная версия может навести группу на ответ. '
            'Организатор поможет всем поучаствовать: слушайте друг друга, не перебивайте и оставляйте место для разных идей.\n\n'
            'После игры можно немного поболтать: какое место удивило больше всего и чья подсказка помогла его найти? '
            'Затем поделитесь результатом активности в МАЙТИМ.')
