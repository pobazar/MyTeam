from typing import Protocol
class Activity(Protocol):
    key: str
    version: int
    title: str
    minimum_participants: int
    achievement_key: str
    card_template: str
    def build_groups(self, people, history, rng=None): ...
    def valid_distribution(self, count, sizes, unmatched) -> bool: ...
    def feedback_form(self, *args, **kwargs): ...
    def final_feedback(self, answer) -> bool: ...
    def achievement_earned(self, person_id) -> bool: ...
    def instructions(self, same_city: bool) -> str: ...
from .coffee import RandomCoffee
from .codenames import CodeNames
ACTIVITIES: dict[str, Activity] = {'random_coffee': RandomCoffee(),'code_names':CodeNames()}
VERSIONS = {(activity.key,activity.version):activity for activity in ACTIVITIES.values()}
def get_activity(key,version=None):
    current=ACTIVITIES.get(key)
    if current is not None and (version is None or current.version==version):
        return current
    return VERSIONS[key,version]
