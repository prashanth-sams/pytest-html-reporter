from pytest import approx


def test_aprox():
    assert 0.1 + 0.2 == approx(0.3)
    assert (0.1 + 0.2, 0.2 + 0.4) == approx((0.3, 0.6))
    assert {'a': 0.1 + 0.2, 'b': 0.2 + 0.4} == approx({'a': 0.3, 'b': 0.6})
