from app.core.nats_broker import set_app


def test_set_app():
    # Test setting the global app for nats broker
    mock_app = object()
    set_app(mock_app)

    from app.core.nats_broker import _app

    assert _app is mock_app
    set_app(None)  # cleanup
