"""Pure daemon state machine for whispr.

Daemon State is always exactly one of IDLE / RECORDING / TRANSCRIBING.
A Toggle is one hotkey press. A Toggle received while TRANSCRIBING is
REJECTED, not queued.

This module is intentionally pure: no I/O, no imports from `whispr`.
"""

from __future__ import annotations

import enum


class State(enum.Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"


class Event(enum.Enum):
    TOGGLE = "toggle"
    CANCEL = "cancel"
    COMPLETE = "complete"


class Effect(enum.Enum):
    START_RECORDING = "start_recording"
    STOP_AND_DISPATCH = "stop_and_dispatch"
    DISCARD = "discard"
    REJECT_BUSY = "reject_busy"
    INJECT_OR_NOSPEECH = "inject_or_nospeech"
    NOOP = "noop"


_TRANSITIONS: dict[tuple[State, Event], tuple[State, Effect]] = {
    (State.IDLE, Event.TOGGLE): (State.RECORDING, Effect.START_RECORDING),
    (State.RECORDING, Event.TOGGLE): (State.TRANSCRIBING, Effect.STOP_AND_DISPATCH),
    (State.RECORDING, Event.CANCEL): (State.IDLE, Effect.DISCARD),
    (State.TRANSCRIBING, Event.TOGGLE): (State.TRANSCRIBING, Effect.REJECT_BUSY),
    (State.TRANSCRIBING, Event.COMPLETE): (State.IDLE, Effect.INJECT_OR_NOSPEECH),
}


def transition(state: State, event: Event) -> tuple[State, Effect]:
    """Compute the next (State, Effect) for a given (state, event) pair.

    Any (state, event) pair not explicitly listed above is a stray event
    and returns (state, Effect.NOOP) — it never raises.
    """
    return _TRANSITIONS.get((state, event), (state, Effect.NOOP))
