.PHONY: all venv install format format-check lint security check train_model train_hex_model train_iris_model test ansible-ui clean

PYTHON_FILES := $(wildcard *.py)

# 1. Create virtual environment
venv:
	python3 -m venv venv

# 2. Install dependencies
install: venv
	. venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt

# 3. Code formatting
format:
	. venv/bin/activate && black $(PYTHON_FILES)

# Verify formatting without changing files
format-check:
	. venv/bin/activate && black --check $(PYTHON_FILES)

# 4. Linting
lint:
	. venv/bin/activate && flake8 --max-line-length=88 --per-file-ignores=ansible_ui.py:E501 $(PYTHON_FILES)

# 5. Security check
security:
	. venv/bin/activate && bandit $(PYTHON_FILES)

# 6. Run all code checks
check: format-check lint security

# 7. Train model
train_model:
	. venv/bin/activate && python3 -c "from main import train_model; train_model()"

# Train and evaluate the UCI 531-feature malware models
train_hex_model:
	. venv/bin/activate && python3 hex_malware_detection.py

# Train the ElasticNet regression example and log RMSE/R² to MLflow
train_iris_model:
	. venv/bin/activate && python3 elasticnet_iris.py

# 9. Run tests
test:
	. venv/bin/activate && python -m pytest

ansible-ui:
	. venv/bin/activate && python -m uvicorn ansible_ui:app --host 192.168.100.77 --port 8080

# 10. Clean up
clean:
	rm -rf venv __pycache__ .pytest_cache .mypy_cache

app:
	python3 main.py	

up:
	docker compose up -d

build:
	docker compose up --build -d

down:
	docker compose down

elastic:
	sudo sysctl -w vm.max_map_count=262144	

logstash:
	docker compose up -d --force-recreate logstash	

# 11. Run everything
all: install check up train_model train_hex_model test
