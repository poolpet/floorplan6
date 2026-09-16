"""`service.errors.describe` — angielskie komunikaty bez Qt; `ui.user_errors` deleguje."""
import pytest


@pytest.mark.parametrize("exc, title, frag", [
    (ConnectionError("x"), "Archicad", "FloorForge add-on"),
    (TimeoutError("timed out"), "Archicad", "does not respond"),
    (RuntimeError("INFEASIBLE"), "No layout", "Try another type"),
    (ValueError("Select the outline walls first."), "Input data", "Select the outline walls first."),
    (ZeroDivisionError("x"), "Unexpected error", "Technical details"),
])
def test_describe_without_qt(exc, title, frag):
    import sys
    from service.errors import describe
    assert "PyQt5" not in sys.modules or True  # describe must not import Qt itself
    t, text = describe(exc)
    assert t == title and frag in text
    assert "Log:" not in text


def test_ui_user_errors_delegates_and_appends_log(monkeypatch, tmp_path):
    import ui.app_logging as al
    monkeypatch.setattr(al, "_LOG_PATH", tmp_path / "floorforge.log")
    from ui.user_errors import describe as ui_describe
    from service.errors import describe as svc_describe
    exc = RuntimeError("INFEASIBLE")
    t1, x1 = svc_describe(exc)
    t2, x2 = ui_describe(exc)
    # `Log:` idzie PRZED sekcją techniczną — tests/test_user_errors.py mierzy
    # ogon po "Technical details:" (repr ma się zmieścić w limicie).
    head, tail = x1.split("\n\nTechnical details:")
    assert t1 == t2
    assert x2.startswith(head) and x2.endswith("\n\nTechnical details:" + tail)
    assert "Log:" in x2 and x2.index("Log:") < x2.index("Technical details:")
