help:
	@echo 'Individual commands:'
	@echo ' build            - Build and start the API and Search containers'
	@echo ' up               - Start the API and Search containers'
	@echo ' base             - Start only the API container'
	@echo ' down             - Remove the networks'
	@echo ' lint             - Lint the code with pylint and flake8 and check imports'
	@echo '                    have been sorted correctly'
	@echo ' test             - Run tests'
	@echo ' speed            - Run a speed test against api.acmi.net.au'
	@echo ' load             - Run a load test against api.acmi.net.au'
	@echo ''
	@echo 'Grouped commands:'
	@echo ' linttest         - Run lint and test'
build:
	# Build and start the api and search containers
	cd development && docker compose up --build
up:
	# Start the api and search containers
	cd development && docker compose up
base:
	# Start only the api container
	cd development && docker compose -f docker-compose-base.yml up
down:
	# Remove the networks
	cd development && docker compose down
lint:
	# Lint the python code
	pylint *
	flake8
	isort -rc --check-only .
test:
	# Run python tests
	pytest -v -s tests/*tests.py
speed:
	# Run speed test
	python3 app/speed_test.py
load:
	# Run load test
	k6 run tests/load_test.js
linttest: lint test
