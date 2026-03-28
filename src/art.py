from config import ROOT_DIR
try:
    from termcolor import colored
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal test envs
    def colored(message: str, *_args, **_kwargs) -> str:
        return str(message)

def print_banner() -> None:
    """
    Prints the introductory ASCII Art Banner.

    Returns:
        None
    """
    with open(f"{ROOT_DIR}/assets/banner.txt", "r") as file:
        print(colored(file.read(), "green"))
