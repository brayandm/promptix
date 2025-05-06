from typing import List
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.formatted_text import HTML
import subprocess
from openai import OpenAI
import os
from dotenv import load_dotenv
from rich import print
from rich.console import Console

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

context_stack: List[str] = []
bindings: KeyBindings = KeyBindings()
console = Console()


def build_prompt() -> HTML:
    if context_stack:
        return HTML(
            f'<cyan>[{" > ".join(context_stack)}]</cyan> <green>></green> '
        )
    return HTML("<green>></green> ")


session: PromptSession = PromptSession(build_prompt, key_bindings=bindings)  # type: ignore

pending_context: dict = {"add": None, "remove": None}  # type: ignore


@bindings.add("c-n")
def push_context(event: KeyPressEvent) -> None:
    text = event.app.current_buffer.text.strip()
    if text:
        context_stack.append(text)
        pending_context["add"] = text
    event.app.current_buffer.reset()
    event.app.exit("")  # type: ignore


@bindings.add("c-b")
def pop_context(event: KeyPressEvent) -> None:
    if context_stack:
        removed = context_stack.pop()
        pending_context["remove"] = removed
    else:
        pending_context["remove"] = "__empty__"
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


def main() -> None:
    print(
        "\n[bold cyan]Promptix started.[/bold cyan] Use [bold]Ctrl+N[/bold] to add context, [bold]Ctrl+B[/bold] to remove it. [bold]Ctrl+C[/bold] to exit.\n"
    )
    while True:
        try:
            user_input: str = session.prompt()
            stripped = user_input.strip()

            if pending_context["add"]:
                print(
                    f"[bold green][+] Context added:[/bold green] [cyan]{pending_context['add']}[/cyan]\n"
                )
                pending_context["add"] = None
                continue

            if pending_context["remove"]:
                if pending_context["remove"] == "__empty__":
                    print("[bold red][!] Stack is empty[/bold red]\n")
                else:
                    print(
                        f"[bold yellow][-] Context removed:[/bold yellow] [cyan]{pending_context['remove']}[/cyan]\n"
                    )
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
