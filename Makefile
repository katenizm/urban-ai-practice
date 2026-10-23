SOURCE_DIR = my_package
TEST_DIR = tests

.PHONY: lint format venv install install-dev install-docs install-tests build clean tests tests-cov

# code formatting and linting

lint:
	pylint ${SOURCE_DIR}

format:
	isort ${SOURCE_DIR}
	black ${SOURCE_DIR}

# installing

venv: # затем необходимо активировать: source .venv/bin/activate
	python3 -m venv .venv

install: # простая установка зависимостей без editable режима
	pip install .

install-dev: # установка зависимостей для разработки
	pip install -e '.[dev]'

install-docs: # установка зависимостей для сборки документации
	pip install -e '.[docs]'

install-tests: # установка зависимостей для тестирования
	pip install -e '.[tests]'

# building the package

build:
	python3 -m build .

clean:
	rm -rf ./build ./dist ./${SOURCE_DIR}.egg-info

# testing

tests: # тестирование
	python3 -m pytest ${TEST_DIR}

tests-cov: # тестирование с выводом процента покрытия кода тестами
	python3 -m pytest ${TEST_DIR} --cov=${SOURCE_DIR} --cov-report=term-missing