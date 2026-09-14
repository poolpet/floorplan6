"""Selftest entry pointu: `floorforge_app --selftest` przez lokalny serwis HTTP.

Dwa testy z podmienionym solverem (szybkie, sprawdzają kontrakt wyjścia i kod
powrotu) + jeden z prawdziwym CP-SAT — bramka, że mózg działa w tym środowisku.
"""


def test_selftest_returns_zero_with_mocked_solver(monkeypatch, capsys):
    import service.app as app
    monkeypatch.setattr(app, "solve_request",
                        lambda req, progress=None: {"mode": "apartment",
                                                    "variants": [{"rooms": [{"name": "salon"}, {"name": "hub"}], "score": 0.9}]})
    import floorforge_app
    rc = floorforge_app.main(["--selftest"])
    out = capsys.readouterr().out
    assert rc == 0 and "SELFTEST OK" in out and "2 pokoi" in out


def test_selftest_returns_one_on_error(monkeypatch, capsys):
    import service.app as app
    monkeypatch.setattr(app, "solve_request",
                        lambda req, progress=None: (_ for _ in ()).throw(RuntimeError("INFEASIBLE")))
    import floorforge_app
    rc = floorforge_app.main(["--selftest"])
    assert rc == 1 and "SELFTEST FAIL" in capsys.readouterr().out


def test_selftest_real_solver_m2_8x6():
    """Prawdziwy solver, ~3 s. Bramka: mózg działa w tym środowisku."""
    import floorforge_app
    assert floorforge_app.main(["--selftest"]) == 0
