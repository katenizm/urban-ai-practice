import my_package


def test_version_is_available():
    assert isinstance(my_package.__version__, str)
    assert my_package.__version__


def test_metadata():
    assert my_package.__author__ == "Ekaterina Kumanina"
    assert my_package.__email__ == "katenizm@gmail.com"
    assert my_package.__license__ == "BSD-3"
