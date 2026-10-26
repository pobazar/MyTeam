"""Code Names is played on an external site; MyTeam connects the group."""
from itertools import combinations
import random
from .base import WeeklyActivity

GAME_URL='https://codenames.game/'

def group_sizes(count):
    if count<4:return []
    sizes=[4]*(count//4)
    for i in range(count%4):sizes[i%len(sizes)]+=1
    return sizes

def make_groups(people,history,rng=None):
    rng=rng or random.SystemRandom()
    sizes=group_sizes(len(people))
    if not sizes:return []
    people=list(people)
    best=None
    # Bounded randomized search prefers new connections and different teams.
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

class CodeNames(WeeklyActivity):
    key='code_names'
    version=1
    title='Code Names'
    minimum_participants=4
    achievement_key='first_code_names'
    signup_only=False
    card_template='myteam/activity_details.html'
    game_url=GAME_URL
    def build_groups(self,people,history,rng=None):return make_groups(people,history,rng)
    def valid_distribution(self,count,sizes,unmatched):
        expected=group_sizes(count)
        return sorted(sizes)==sorted(expected) and unmatched==(count if count<4 else 0)
    def organizer_instructions(self):
        return 'Ты организуешь игру: предложи группе время, создай ссылку на звонок и комнату Code Names. Пришли обе ссылки участникам. '
    def instructions(self,same_city):
        return ('Пообщайтесь с коллегами за онлайн-игрой Code Names — попробуйте понять, как вы мыслите и находите общий язык.\n\n'
            'Договоритесь в Telegram о времени и созвонитесь с голосом. Заложите 45–60 минут. Организатор создаёт комнату на сайте игры, выбирает русский язык и отправляет ссылку группе. Правила можно посмотреть на сайте. Разделитесь на две команды; в каждой выберите капитана, который даёт подсказки. Если вас нечётное число, в одной команде будет на человека больше. Меняйтесь ролями между партиями.\n\n'
            'Не молчите: обсуждайте версии и рассуждайте вслух, когда ходит ваша команда. Слушайте друг друга и не перебивайте. Во время хода соперников не подсказывайте и не мешайте их обсуждению; капитаны не дают дополнительных намёков. Обращайте внимание на то, какие ассоциации возникают у коллег и как они объясняют свои решения.\n\n'
            'После игры уделите несколько минут разговору: что удивило в рассуждениях других? Какие разные пути привели к одному ответу? Здесь важна не только победа, но и возможность увидеть коллег в новой ситуации. Затем поделитесь результатом активности в МАЙТИМ.')
