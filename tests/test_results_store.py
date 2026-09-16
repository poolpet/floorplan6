"""`service.results.ResultStore` — obiekty planów w pamięci, LRU z limitem."""


def test_put_get_and_lru_eviction():
    from service.results import ResultStore
    s = ResultStore(limit=3)
    for i in range(4):
        s.put(f"j{i}", {"mode": "apartment", "plans": [i]})
    assert s.get("j0") is None
    assert s.get("j3") == {"mode": "apartment", "plans": [3]}
    assert s.get("nope") is None


def test_get_refreshes_recency():
    from service.results import ResultStore
    s = ResultStore(limit=2)
    s.put("a", {}); s.put("b", {})
    s.get("a")
    s.put("c", {})
    assert s.get("b") is None and s.get("a") is not None
