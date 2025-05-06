from typing import List
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
import subprocess
from openai import OpenAI
import os
from dotenv import load_dotenv
from rich import print
from rich.console import Console

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

context_stack: List[str] = []
session: PromptSession = PromptSession()  # type: ignore
bindings: KeyBindings = KeyBindings()
console = Console()


@bindings.add("c-n")
def push_context(event: KeyPressEvent) -> None:
    text = event.app.current_buffer.text.strip()
    if text:
        context_stack.append(text)
        event.app.current_buffer.reset()
        print(
            f"\n[bold green][+] Context added:[/bold green] [cyan]{text}[/cyan]\n"
        )


@bindings.add("c-b")
def pop_context(event: KeyPressEvent) -> None:
    if context_stack:
        popped: str = context_stack.pop()
        print(
            f"\n[bold yellow][-] Context removed:[/bold yellow] [cyan]{popped}[/cyan]\n"
        )
    else:
        print("\n[bold red][!] Stack is empty[/bold red]\n")


def build_prompt() -> str:
    return f"[{' > '.join(context_stack)}] > " if context_stack else "> "


def get_command_from_gpt(prompt: str) -> str:
    full_prompt: str = " ".join(context_stack + [prompt])
    print(
        f"\n[bold blue][>] Sending to GPT:[/bold blue] [white]{full_prompt}[/white]\n"
    )

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
            user_input: str = session.prompt(
                build_prompt(), key_bindings=bindings
            )
            if not user_input.strip():
                continue
            command: str = get_command_from_gpt(user_input)
            execute_command(command)
        except KeyboardInterrupt:
            print("\n[bold red][Interrupted by user][/bold red]")
            break
        except EOFError:
            print("\n[bold red][Exiting...][/bold red]")
            break


if __name__ == "__main__":
    main()
