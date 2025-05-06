import os
import subprocess
import sys
from base64 import urlsafe_b64encode
from getpass import getpass
from pathlib import Path
from typing import List, Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from openai import OpenAI
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.input.defaults import create_input
from prompt_toolkit.input.vt100 import raw_mode
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from rich import print
from rich.console import Console

SHOW_CONTEXT_MESSAGES = False

# === Secure Token Storage ===
SECURE_DIR = Path.home() / ".promptix"
SECURE_FILE = SECURE_DIR / "token.enc"
SESSION_CACHE = SECURE_DIR / "password_cache"


def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
        backend=default_backend(),
    )
    return urlsafe_b64encode(kdf.derive(password.encode()))


def encrypt_token(token: str, password: str) -> bytes:
    salt = os.urandom(16)
    key = derive_key(password, salt)
    fernet = Fernet(key)
    token_enc = fernet.encrypt(token.encode())
    return salt + token_enc  # type: ignore


def decrypt_token(enc_data: bytes, password: str) -> str:
    salt = enc_data[:16]
    token_enc = enc_data[16:]
    key = derive_key(password, salt)
    fernet = Fernet(key)
    return fernet.decrypt(token_enc).decode()  # type: ignore


def load_cached_password() -> Optional[str]:
    if SESSION_CACHE.exists():
        return SESSION_CACHE.read_text().strip()
    return None


def cache_password(password: str) -> None:
    SESSION_CACHE.write_text(password)


def clear_cached_password() -> None:
    if SESSION_CACHE.exists():
        SESSION_CACHE.unlink()


REMEMBER_PASSWORD = SESSION_CACHE.exists()


def load_or_create_token() -> str:
    SECURE_DIR.mkdir(exist_ok=True)
    password = load_cached_password() if REMEMBER_PASSWORD else None

    if SECURE_FILE.exists():
        if not password:
            password = getpass("[Promptix] Enter your master password: ")
            if REMEMBER_PASSWORD:
                cache_password(password)
        try:
            with open(SECURE_FILE, "rb") as f:
                return decrypt_token(f.read(), password)
        except Exception:
            print(
                "[bold red][!] Invalid password or corrupted token file[/bold red]"
            )
            sys.exit(1)
    else:
        password = getpass("[Promptix] Set a master password: ")
        token = getpass("[Promptix] Enter your OpenAI token: ")
        enc_data = encrypt_token(token, password)
        with open(SECURE_FILE, "wb") as f:
            f.write(enc_data)
        if REMEMBER_PASSWORD:
            cache_password(password)
        print("[bold green][✓] Token stored securely[/bold green]")
        return token


# === Promptix Core ===


def build_prompt() -> HTML:
    if context_stack:
        return HTML(
            f'<cyan>[{" > ".join(context_stack)}]</cyan> <green>></green> '
        )
    return HTML("<green>></green> ")


token = load_or_create_token()
client = OpenAI(api_key=token)
context_stack: List[str] = []
bindings: KeyBindings = KeyBindings()
console = Console()

session: PromptSession = PromptSession(build_prompt, key_bindings=bindings)  # type: ignore
pending_context: dict = {"add": None, "remove": None, "options": False}  # type: ignore


def configure_promptix() -> None:
    global REMEMBER_PASSWORD
    inp = create_input()

    while True:
        print("\n[bold cyan]Promptix Configuration[/bold cyan]")
        print("[1] Change password")
        print("[2] Change token")
        print("[3] Delete all data")
        print(
            "[4] Remember password:",
            (
                "[green]Enabled[/green]"
                if REMEMBER_PASSWORD
                else "[red]Disabled[/red]"
            ),
        )
        print("[5] Exit configuration")
        print("\nPress [1-5] to select an option...")

        key = None
        with raw_mode(inp.fileno()):
            while not key:
                keys = inp.read_keys()
                if keys:
                    key = keys[0].key

        if key == "1":
            if not SECURE_FILE.exists():
                print("[bold red]No token stored yet[/bold red]")
                continue
            password = getpass("Enter current password: ")
            try:
                with open(SECURE_FILE, "rb") as f:
                    token = decrypt_token(f.read(), password)
                new_password = getpass("Enter new password: ")
                enc_data = encrypt_token(token, new_password)
                with open(SECURE_FILE, "wb") as f:
                    f.write(enc_data)
                print("[bold green]Password changed successfully[/bold green]")
                if REMEMBER_PASSWORD:
                    cache_password(new_password)
            except Exception:
                print("[bold red]Incorrect password[/bold red]")

        elif key == "2":
            password = getpass("Enter your password: ")
            token = getpass("Enter new OpenAI token: ")
            enc_data = encrypt_token(token, password)
            with open(SECURE_FILE, "wb") as f:
                f.write(enc_data)
            print("[bold green]Token updated successfully[/bold green]")

        elif key == "3":
            confirm = (
                input("Are you sure you want to delete all data? (y/N): ")
                .strip()
                .lower()
            )
            if confirm == "y":
                if SECURE_FILE.exists():
                    SECURE_FILE.unlink()
                clear_cached_password()
                print("[bold red]All data deleted[/bold red]")
                sys.exit(0)

        elif key == "4":
            REMEMBER_PASSWORD = not REMEMBER_PASSWORD
            if not REMEMBER_PASSWORD:
                clear_cached_password()
            print("[bold green]Preference updated[/bold green]")

        elif key == "5":
            break
        else:
            print("[bold yellow]Invalid choice[/bold yellow]")


@bindings.add("c-n")  # type: ignore
def push_context(event: KeyPressEvent) -> None:
    text = event.app.current_buffer.text.strip()
    if text:
        context_stack.append(text)
        pending_context["add"] = text
    event.app.current_buffer.reset()
    event.app.exit("")  # type: ignore


@bindings.add("c-b")  # type: ignore
def pop_context(event: KeyPressEvent) -> None:
    if context_stack:
        removed = context_stack.pop()
        pending_context["remove"] = removed
    else:
        pending_context["remove"] = "__empty__"
    event.app.exit("")  # type: ignore


@bindings.add("c-o")  # type: ignore
def open_options(event: KeyPressEvent) -> None:
    pending_context["options"] = True
    event.app.exit("")  # type: ignore


def get_command_from_gpt(prompt: str) -> str:
    full_prompt: str = " ".join(context_stack + [prompt])

    system_prompt = (
        "You are a CLI assistant that converts instructions into shell commands.\n"
        "You will receive a list of instructions and you need to convert them into a single shell command.\n"
        "You should only return the command without any explanation or additional text."
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_prompt},
        ],
    )
    return str(response.choices[0].message.content).strip()


def execute_command(command: str) -> None:
    print(
        f"[bold magenta][?] Execute:[/bold magenta] [green]{command}[/green] (Y/n)"
    )
    confirm: str = input("> ").strip().lower() or "y"
    if confirm == "y":
        try:
            result = subprocess.run(
                command, shell=True, check=True, text=True, capture_output=True
            )
            console.print(result.stdout, style="white")
        except subprocess.CalledProcessError as e:
            print(f"[bold red][!] Error:[/bold red] {e.stderr}")
    else:
        print("[bold yellow][x] Cancelled[/bold yellow]")


def overwrite_previous_prompt_line() -> None:
    sys.stdout.write("\033[F\033[K")
    sys.stdout.flush()


def main() -> None:
    print(
        "\n[bold cyan]Promptix started.[/bold cyan] Use [bold]Ctrl+N[/bold] to add context, [bold]Ctrl+B[/bold] to remove it, [bold]Ctrl+O[/bold] to open settings. [bold]Ctrl+C[/bold] to exit.\n"
    )
    while True:
        try:
            user_input: str = session.prompt()
            stripped = user_input.strip()

            if pending_context["options"]:
                overwrite_previous_prompt_line()
                pending_context["options"] = False
                configure_promptix()
                continue

            if pending_context["add"]:
                if SHOW_CONTEXT_MESSAGES:
                    print(
                        f"[bold green][+] Context added:[/bold green] [cyan]{pending_context['add']}[/cyan]\n"
                    )
                else:
                    overwrite_previous_prompt_line()
                pending_context["add"] = None
                continue

            if pending_context["remove"]:
                if SHOW_CONTEXT_MESSAGES:
                    if pending_context["remove"] == "__empty__":
                        print("[bold red][!] Stack is empty[/bold red]\n")
                    else:
                        print(
                            f"[bold yellow][-] Context removed:[/bold yellow] [cyan]{pending_context['remove']}[/cyan]\n"
                        )
                else:
                    overwrite_previous_prompt_line()
                pending_context["remove"] = None
                continue

            if not stripped:
                continue

            command: str = get_command_from_gpt(stripped)
            execute_command(command)

        except KeyboardInterrupt:
            print("\n[bold red][Exiting on Ctrl+C][/bold red]")
            break
        except EOFError:
            print("\n[bold red][Exiting...][/bold red]")
            break


if __name__ == "__main__":
    main()
