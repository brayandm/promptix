# Promptix v0.1.0

1 - Install pyenv & pipenv on your system

-   [pyenv](https://github.com/pyenv/pyenv#installation)
-   [pipenv](https://pypi.org/project/pipenv/)

2 - Install python 3.12

```bash
pyenv install
```

3 - Setup python 3.12 as the local version

```bash
pyenv local
```

4 - Setup environment & dependencies

```bash
PIPENV_VENV_IN_PROJECT=1 pipenv install --dev
```

4 - Copy the `.env.example` file to `.env`:

```bash
cp .env.example .env
```

5 - Run the application

```bash
pipenv run python main.py
```

## Development

1 - Install pre-commit hooks

```bash
pipenv run pre-commit install
```
