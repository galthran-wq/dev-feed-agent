from src.agent.dependency_parser import (
    parse_dependencies,
    parse_package_json,
    parse_pyproject,
    parse_requirements,
)


def test_parse_pyproject_pep621_and_optional() -> None:
    content = """
[project]
name = "x"
dependencies = ["fastapi>=0.115", "SQLAlchemy[asyncio]>=2.0 ; python_version>'3.10'"]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff"]
"""
    names = parse_pyproject(content)
    assert "fastapi" in names
    assert "sqlalchemy" in names  # normalized: lowercased, extras stripped
    assert "pytest" in names
    assert "ruff" in names


def test_parse_pyproject_poetry_skips_python() -> None:
    content = """
[tool.poetry.dependencies]
python = "^3.12"
torch = "^2.0"
transformers = "*"
"""
    names = parse_pyproject(content)
    assert names == ["torch", "transformers"]


def test_parse_requirements_skips_noise() -> None:
    content = "# comment\nfastapi==0.115.0\n-r other.txt\n\nhttpx>=0.28  # inline\ngit+https://x/y\n"
    names = parse_requirements(content)
    assert names == ["fastapi", "httpx"]


def test_parse_package_json() -> None:
    content = '{"dependencies": {"vue": "^3.5"}, "devDependencies": {"vite": "^7"}}'
    names = parse_package_json(content)
    assert "vue" in names
    assert "vite" in names


def test_parse_dependencies_dispatch_and_unknown() -> None:
    assert parse_dependencies("pyproject.toml", '[project]\ndependencies=["a"]') == ["a"]
    assert parse_dependencies("requirements-dev.txt", "b==1") == ["b"]
    assert parse_dependencies("README.md", "whatever") == []
    # Malformed content never raises.
    assert parse_dependencies("package.json", "{not json") == []
