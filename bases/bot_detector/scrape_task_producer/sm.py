from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Generic, Iterable, TypeVar

S = TypeVar("S", bound=Enum)
E = TypeVar("E", bound=Enum)
C = TypeVar("C")

Action = Callable[[C], None]


class InvalidTransition(Exception):
    pass


@dataclass
class StateMachine(Generic[S, E, C]):
    transitions: dict[tuple[S, E], tuple[S, Action]] = field(default_factory=dict)

    def add_transition(
        self, from_state: S, event: E, to_state: S, func: Action
    ) -> None:
        self.transitions[(from_state, event)] = (to_state, func)

    def next_transition(self, state: S, event: E) -> tuple[S, Action]:
        try:
            return self.transitions[(state, event)]
        except KeyError as e:
            raise InvalidTransition(f"Cannot {event.name} when {state.name}") from e

    def handle(self, ctx: C, state: S, event: E) -> S:
        next_state, action = self.next_transition(state, event)
        action(ctx)
        return next_state

    def transition(self, from_state: S | Iterable[S], event: E, to_state: S):
        if not isinstance(from_state, Iterable):
            states = (from_state,)
        else:
            states = from_state

        def decorator(func: Action) -> Action:
            for s in states:
                self.add_transition(s, event, to_state, func)
            return func

        return decorator
