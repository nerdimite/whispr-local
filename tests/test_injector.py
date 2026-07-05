from whispr.injector import PASTE_KEYCODES, Injector


class FakeRun:
    def __init__(self):
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        return None


def test_inject_copies_then_pastes():
    fake = FakeRun()
    injector = Injector(run=fake, settle=0.0)

    injector.inject("héllo, world")

    assert len(fake.calls) == 2

    argv1, kwargs1 = fake.calls[0]
    assert argv1 == ["wl-copy"]
    assert kwargs1["input"] == "héllo, world"

    # ydotool needs raw keycodes for Ctrl+V, not the symbolic "ctrl+v".
    argv2, _ = fake.calls[1]
    assert argv2 == ["ydotool", "key", *PASTE_KEYCODES]
    assert argv2[2:] == ["29:1", "47:1", "47:0", "29:0"]


def test_empty_text_no_calls():
    fake = FakeRun()
    injector = Injector(run=fake)

    injector.inject("")
    injector.inject(None)

    assert fake.calls == []
