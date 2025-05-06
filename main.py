from typing import List
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
import subprocess
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

context_stack: List[str] = []
session: PromptSession = PromptSession()  # type: ignore
bindings: KeyBindings = KeyBindings()


@bindings.add("c-n")
def push_context(event: KeyPressEvent) -> None:
    new_context: str = session.prompt("New context: ")
    context_stack.append(new_context)
    print(f"[Context added]: {new_context}")


@bindings.add("c-b")
def pop_context(event: KeyPressEvent) -> None:
    if context_stack:
        popped: str = context_stack.pop()
        print(f"[Context removed]: {popped}")
    else:
        print("[Stack is empty]")


def build_prompt() -> str:
    return f"[{' > '.join(context_stack)}] > " if context_stack else "> "


def get_command_from_gpt(prompt: str) -> str:
    full_prompt: str = " ".join(context_stack + [prompt])
    print(f"[Sending to GPT]: {full_prompt}")

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "You are a CLI assistant that converts instructions into shell commands.",
            },
            {"role": "user", "content": full_prompt},
        ],
    )
    return str(response.choices[0].message.content).strip()


def execute_command(command: str) -> None:
    print(f"Execute command?: {command} (y/n)")
    confirm: str = input("> ").strip().lower()
    if confirm == "y":
        try:
            result = subprocess.run(
                command, shell=True, check=True, text=True, capture_output=True
            )
            print(result.stdout)
        except subprocess.CalledProcessError as e:
            print(f"[Error]: {e.stderr}")
    else:
        print("[Cancelled]")


def main() -> None:
    print(
        "Promptix started. Use Ctrl+N to add context, Ctrl+B to remove it. Ctrl+C to exit."
    )
    while True:
        try:
            user_input: str = session.prompt(
                build_prompt(), key_bindings=bindings
            )
            if not user_input.strip():
                continue
            command: str = get_command_from_gpt(user_input)
            print(f"[Suggested command]: {command}")
            execute_command(command)
        except KeyboardInterrupt:
            print("\n[Interrupted by user]")
        except EOFError:
            print("\n[Exiting...]")
            break


if __name__ == "__main__":
    main()
