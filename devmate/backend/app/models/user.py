"""
User Model - Day 1 phase B student challenge answer key
Answers business question #2
"""

from typing import ClassVar

class User:
    registry: ClassVar[list["User"]] = []

    def __init__(self, user_id: int, name: str, team: str):
        self.id = user_id
        self.name = name
        self.team = team
        User.registry.append(self)

    @classmethod
    def find_by_id(cls, user_id: int) -> "User | None":
        for user in cls.registry:
            if user.id == user_id:
                return user
        return None

    def __repr__(self) -> str:
        return f"User(id={self.id}, name={self.name!r}, team={self.team!r})"