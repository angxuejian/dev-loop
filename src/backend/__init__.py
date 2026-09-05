def greet(name: str) -> str:
    return f"Hello, {name}!"


def main() -> None:
    # Ruff F541: `ruff check . --fix` removes the unnecessary f prefix.
    print("Ruff autofix demo")

    # Pyright: an int cannot be assigned to a str. Change 123 to "Alice".
    name: str = "Alice"

    # Ruff format: fixes spacing and quote style.
    settings = {"retries": 3, "enabled": True}

    print(greet(name))
    print(settings)
