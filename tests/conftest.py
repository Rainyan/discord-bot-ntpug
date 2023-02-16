import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--dbdrivers",
        action="store",
        default="all",
        help="which DB drivers to test",
    )


@pytest.fixture
def dbdrivers(request):
    return request.config.getoption("--dbdrivers")
