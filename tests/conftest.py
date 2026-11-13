import pytest

from main import app
from routes.auth import require_api_key


@pytest.fixture(autouse=True)
def _api_key_check_disabled(request):
    """Most tests are about signals and backtests, not authentication, so the
    API key check is switched off for them. Tests marked `real_auth` run with
    the check exactly as deployed."""
    if "real_auth" in request.keywords:
        yield
        return

    app.dependency_overrides[require_api_key] = lambda: None
    yield
    app.dependency_overrides.pop(require_api_key, None)
