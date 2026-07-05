"""Tests for the pure daemon state machine in whispr.state."""

import pytest

from whispr.state import Effect, Event, State, transition


@pytest.mark.parametrize(
    "state, event, expected",
    [
        (State.IDLE, Event.TOGGLE, (State.RECORDING, Effect.START_RECORDING)),
        (State.RECORDING, Event.TOGGLE, (State.TRANSCRIBING, Effect.STOP_AND_DISPATCH)),
        (State.RECORDING, Event.CANCEL, (State.IDLE, Effect.DISCARD)),
        (State.TRANSCRIBING, Event.TOGGLE, (State.TRANSCRIBING, Effect.REJECT_BUSY)),
        (State.TRANSCRIBING, Event.COMPLETE, (State.IDLE, Effect.INJECT_OR_NOSPEECH)),
    ],
)
def test_defined_transitions(state, event, expected):
    assert transition(state, event) == expected


def test_reject_while_busy():
    assert transition(State.TRANSCRIBING, Event.TOGGLE) == (
        State.TRANSCRIBING,
        Effect.REJECT_BUSY,
    )


def test_cancel_from_recording():
    assert transition(State.RECORDING, Event.CANCEL) == (State.IDLE, Effect.DISCARD)


@pytest.mark.parametrize(
    "state, event",
    [
        (State.IDLE, Event.CANCEL),
        (State.IDLE, Event.COMPLETE),
        (State.RECORDING, Event.COMPLETE),
        (State.TRANSCRIBING, Event.CANCEL),
    ],
)
def test_stray_events_are_noop_and_do_not_raise(state, event):
    assert transition(state, event) == (state, Effect.NOOP)
