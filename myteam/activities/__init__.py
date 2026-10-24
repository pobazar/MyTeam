from typing import Protocol
class Activity(Protocol):
    key: str
    version: int
    title: str
    def instructions(self, same_city: bool) -> str: ...
from .coffee import RandomCoffee
ACTIVITIES: dict[str, Activity] = {'random_coffee': RandomCoffee()}
def get_activity(key):
    return ACTIVITIES[key]
