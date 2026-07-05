from whispr.config import Config
from whispr.rewriter import Rewriter, build_instructions, clean_reply


# -- build_instructions (pure) -----------------------------------------------

def test_instructions_contain_core_rules():
    instr = build_instructions()
    assert "rewritten transcript only" in instr.lower()
    assert "remove filler" in instr.lower()


def test_instructions_omit_vocabulary_section_when_empty():
    assert "exact terms" not in build_instructions()


def test_instructions_include_vocabulary_terms():
    instr = build_instructions(vocabulary=["CellStrat", "DepoIQ"])
    assert "CellStrat, DepoIQ" in instr


def test_instructions_list_canonical_spelling_not_the_pronunciation_hint():
    # "Sasi (pronounced Shashi)" must offer "Sasi" as the spelling, not the whole entry.
    instr = build_instructions(vocabulary=["Sasi (pronounced Shashi)", "git"])
    assert "source of truth for spelling: Sasi, git" in instr
    # and the spoken form is mapped explicitly so Whisper's "Shashi" resolves to "Sasi"
    assert 'transcribed "Shashi" means "Sasi"' in instr


def test_instructions_have_no_pronunciation_line_without_hints():
    assert "Pronunciation —" not in build_instructions(vocabulary=["git", "CellStrat"])


def test_instructions_add_vision_guidance_only_with_screenshot():
    assert "screenshot" not in build_instructions().lower()
    instr = build_instructions(with_screenshot=True).lower()
    assert "screenshot" in instr
    # framed as a spelling dictionary (correction source), not content to copy
    assert "dictionary" in instr
    # guarded against over-reach (completing from screen) AND injection
    assert "never add" in instr
    assert "instructions" in instr


# -- clean_reply (pure) ------------------------------------------------------

def test_clean_reply_strips_whitespace_and_quotes():
    assert clean_reply('  "Fixed text."  ', "fixed text") == "Fixed text."


def test_clean_reply_rejects_empty():
    assert clean_reply("   ", "anything") is None


def test_clean_reply_rejects_rambling():
    # A "rewrite" many times longer than the input is model rambling, not cleanup.
    assert clean_reply("blah " * 200, "short input sentence here") is None


# -- Rewriter (falls back to the raw transcript on every failure) ------------

def test_rewrite_returns_cleaned_completion():
    rewriter = Rewriter(complete=lambda instr, text, img=None: " Fixed. ")
    assert rewriter.rewrite("fixed") == "Fixed."


def test_rewrite_passes_vocabulary_into_instructions():
    seen = {}

    def complete(instructions, transcript, image=None):
        seen["instructions"] = instructions
        return "ok"

    Rewriter(complete=complete, vocabulary=["git", "CellStrat"]).rewrite("git")
    assert "git, CellStrat" in seen["instructions"]


def test_rewrite_falls_back_when_api_raises():
    def complete(instr, text, img=None):
        raise RuntimeError("api down")

    assert Rewriter(complete=complete).rewrite("raw text") == "raw text"


def test_rewrite_falls_back_on_unusable_completion():
    rewriter = Rewriter(complete=lambda instr, text, img=None: "   ")
    assert rewriter.rewrite("raw text") == "raw text"


def test_rewrite_passes_through_empty_transcript_without_calling_api():
    calls = []
    rewriter = Rewriter(complete=lambda *a: calls.append(1) or "x")
    assert rewriter.rewrite("") == ""
    assert calls == []


# -- screen context: capture seam feeds the completer, never blocks -----------

def test_rewrite_without_capture_sends_no_image():
    seen = {}

    def complete(instr, text, image=None):
        seen["image"] = image
        return "ok"

    Rewriter(complete=complete).rewrite("hi")
    assert seen["image"] is None


def test_rewrite_with_capture_passes_screenshot_to_completer():
    seen = {}

    def complete(instr, text, image=None):
        seen["image"] = image
        assert "screenshot" in instr.lower()  # vision guidance added
        return "ok"

    Rewriter(complete=complete, capture=lambda: b"JPEGDATA").rewrite("hi")
    assert seen["image"] == b"JPEGDATA"


def test_rewrite_survives_capture_failure_and_goes_text_only():
    seen = {}

    def capture():
        raise RuntimeError("portal denied")

    def complete(instr, text, image=None):
        seen["image"] = image
        return "Cleaned."

    out = Rewriter(complete=complete, capture=capture).rewrite("raw")
    assert out == "Cleaned."       # still rewrote, didn't fall back
    assert seen["image"] is None   # sent text-only after capture failed


# -- observability: every outcome is logged so a silent fallback is visible ---

def test_rewrite_logs_success():
    logs = []
    Rewriter(complete=lambda i, t, img=None: "Fixed.", log=logs.append).rewrite("fixed")
    assert any("OK in" in m for m in logs)


def test_rewrite_logs_api_failure_reason():
    logs = []

    def complete(i, t, img=None):
        raise RuntimeError("connection refused")

    Rewriter(complete=complete, log=logs.append).rewrite("raw")
    assert any("FAILED" in m and "connection refused" in m for m in logs)


def test_rewrite_logs_unusable_reply():
    logs = []
    Rewriter(complete=lambda i, t, img=None: "   ", log=logs.append).rewrite("raw")
    assert any("unusable reply" in m for m in logs)


# -- Config plumbing ----------------------------------------------------------

def test_config_rewrite_defaults_off():
    config = Config(device="CPU")
    assert config.rewrite is False
    assert config.vocabulary == []
    assert config.screen_context is False
    assert config.rewriter_model == "gpt-5.4-nano"
    assert config.rewrite_effort == "none"


def test_config_loads_rewrite_fields_from_toml(tmp_path):
    from whispr.config import load

    config_file = tmp_path / "config.toml"
    config_file.write_text(
        'device = "CPU"\n'
        "rewrite = true\n"
        'vocabulary = ["git", "DepoIQ", "Bhavesh"]\n'
        'rewriter_model = "gpt-5.4-mini"\n'
        'rewrite_effort = "low"\n'
        "rewrite_timeout = 5.0\n"
    )
    config = load(config_file)
    assert config.rewrite is True
    assert config.vocabulary == ["git", "DepoIQ", "Bhavesh"]
    assert config.rewriter_model == "gpt-5.4-mini"
    assert config.rewrite_effort == "low"
    assert config.rewrite_timeout == 5.0
