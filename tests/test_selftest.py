"""Selftest entry pointu: `floorforge_app --selftest` przez lokalny serwis HTTP.

Testy z podmienionym solverem (szybkie: kontrakt wyjścia, kody powrotu, awarie
startu serwisu) + jeden z prawdziwym CP-SAT — bramka, że mózg działa w tym
środowisku. Plus `--version`, które musi być czystym odczytem (bez efektów ubocznych).
"""
import os


def test_selftest_returns_zero_with_mocked_solver(monkeypatch, capsys):
    import service.app as app
    monkeypatch.setattr(app, "solve_request",
                        lambda req, progress=None: {"mode": "apartment",
                                                    "variants": [{"rooms": [{"name": "salon"}, {"name": "hub"}], "score": 0.9}]})
    import floorforge_app
    rc = floorforge_app.main(["--selftest"])
    out = capsys.readouterr().out
    assert rc == 0 and "SELFTEST OK" in out and "2 rooms" in out


def test_selftest_returns_one_on_error(monkeypatch, capsys):
    import service.app as app
    monkeypatch.setattr(app, "solve_request",
                        lambda req, progress=None: (_ for _ in ()).throw(RuntimeError("INFEASIBLE")))
    import floorforge_app
    rc = floorforge_app.main(["--selftest"])
    assert rc == 1 and "SELFTEST FAIL" in capsys.readouterr().out


def test_selftest_returns_one_when_no_variants(monkeypatch, capsys):
    """Solver skończył bez wyjątku, ale nic nie zwrócił — to też FAIL."""
    import service.app as app
    monkeypatch.setattr(app, "solve_request",
                        lambda req, progress=None: {"mode": "apartment", "variants": []})
    import floorforge_app
    rc = floorforge_app.main(["--selftest"])
    assert rc == 1 and "SELFTEST FAIL: the solver returned no variants" in capsys.readouterr().out


def test_selftest_returns_one_when_service_fails_to_start(monkeypatch, capsys):
    """Najbardziej prawdopodobna awaria w paczce (brak hidden importu / zajęty port)
    musi wyjść jako SELFTEST FAIL + rc 1, a nie traceback."""
    import service.app as app
    monkeypatch.setattr(app, "start_server",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bind")))
    import floorforge_app
    rc = floorforge_app.main(["--selftest"])
    out = capsys.readouterr().out
    assert rc == 1 and "SELFTEST FAIL" in out and "bind" in out


def test_version_is_side_effect_free(monkeypatch, capsys, tmp_path):
    """`--version` to czysty odczyt: bez pliku logu i bez włączania trybu beta."""
    monkeypatch.delenv("FLOORFORGE_BETA", raising=False)
    monkeypatch.setenv("FLOORFORGE_VERSION", "beta-7")
    import floorforge_app
    rc = floorforge_app.main(["--version"])
    assert rc == 0 and capsys.readouterr().out.strip() == "beta-7"
    # tmp_path == FLOORFORGE_LOG_DIR (autouse fixture _isolated_log_dir w conftest)
    assert not (tmp_path / "floorforge.log").exists()
    assert "FLOORFORGE_BETA" not in os.environ


def test_selftest_real_solver_m2_8x6():
    """Prawdziwy solver, ~3 s. Bramka: mózg działa w tym środowisku."""
    import floorforge_app
    assert floorforge_app.main(["--selftest"]) == 0
