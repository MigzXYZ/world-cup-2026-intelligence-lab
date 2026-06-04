from src.travel import haversine_km


def test_haversine_positive():
    assert haversine_km(30.0444, 31.2357, 40.7128, -74.0060) > 8000
