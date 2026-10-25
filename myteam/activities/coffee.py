from itertools import combinations
import random
import networkx as nx

class RandomCoffee:
    key = 'random_coffee'
    version = 1
    title = 'Random Coffee'
    minimum_participants = 2
    achievement_key = 'first_coffee'
    card_template = 'myteam/activity_details.html'
    def build_groups(self,people,history,rng=None):
        return select_groups(people,history,rng)
    def valid_distribution(self,count,sizes,unmatched):
        if count<2:return not sizes and unmatched==count
        return unmatched==0 and all(s in (2,3) for s in sizes) and sum(sizes)==count and sizes.count(3)==count%2
    def final_feedback(self,answer):
        return answer.outcome=='no' or (answer.outcome=='yes' and bool(answer.rating or (answer.impression and answer.again)))
    def achievement_earned(self,person_id):
        from myteam.models import Feedback
        return Feedback.objects.filter(member__person_id=person_id,member__round__activity=self.key,outcome='yes').exists()
    def feedback_form(self,*args,**kwargs):
        from myteam.feedback import FeedbackForm
        return FeedbackForm(*args,**kwargs)
    def instructions(self, same_city):
        where = 'Вы в одном городе — встретьтесь офлайн за кофе. Организатор предложит удобное место и время. Если встретиться лично не получится, можно созвониться.' if same_city else 'Вы в разных городах — встретьтесь онлайн. Организатор предложит время и удобный сервис звонка.'
        return where + ' Напишите друг другу в Telegram и выберите время. Рекомендуем 20–30 минут. О чём поговорить: чем занимается ваша команда? Что недавно вдохновило? В какое место стоит попутешествовать?'


def select_groups(people, history, rng=None):
    """Minimum-weight perfect matching; one triple for odd attendance."""
    rng=rng or random.SystemRandom()
    count=len(people)
    if count<2:return []
    people=list(people)
    rng.shuffle(people)
    # Integer scales guarantee total lower-priority costs never overtake one higher priority.
    edges=count*(count-1)//2
    max_recency=max(history.values(),default=0)
    random_scale=edges*1001+1
    team_scale=random_scale
    recency_scale=(edges+1)*team_scale
    repeat_scale=(edges*(max_recency+1)+1)*recency_scale
    costs={}
    for a,b in combinations(range(count),2):
        key=frozenset((people[a].id,people[b].id))
        repeated=key in history
        same=people[a].team_group_id is not None and people[a].team_group_id==people[b].team_group_id
        costs[a,b]=int(repeated)*repeat_scale+history.get(key,0)*recency_scale+int(same)*team_scale+rng.randrange(1000)
    def edge(a,b):return costs[tuple(sorted((a,b)))]
    def pairs(indices):
        graph=nx.Graph()
        graph.add_nodes_from(indices)
        for a,b in combinations(indices,2):graph.add_edge(a,b,weight=edge(a,b))
        return [list(pair) for pair in nx.min_weight_matching(graph)]
    if count%2==0:
        groups=pairs(list(range(count)))
    else:
        if count<=21:
            triples=list(combinations(range(count),3))
        else:
            candidates=set()
            while len(candidates)<128:candidates.add(tuple(sorted(rng.sample(range(count),3))))
            triples=list(candidates)
        best=None
        for triple in triples:
            rest=pairs([i for i in range(count) if i not in triple])
            groups=[list(triple),*rest]
            cost=sum(edge(a,b) for group in groups for a,b in combinations(group,2))
            if best is None or cost<best[0]:best=(cost,groups)
        groups=best[1]
    return [[people[i] for i in group] for group in groups]

