"""Shared four-person grouping for external games; preferences never exclude attendees."""
from itertools import combinations
import random
from .base import WeeklyActivity

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

class FourPersonActivity(WeeklyActivity):
    minimum_participants=4
    signup_only=False
    card_template='myteam/activity_details.html'

    def build_groups(self,people,history,rng=None):return make_groups(people,history,rng)

    def valid_distribution(self,count,sizes,unmatched):
        return sorted(sizes)==sorted(group_sizes(count)) and unmatched==(count if count<4 else 0)
