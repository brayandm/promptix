from setuptools import find_packages, setup  # type: ignore[import]

setup(
    name="promptix",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "prompt-toolkit",
        "keyboard",
        "openai",
        "rich",
        "python-dotenv",
        "cryptography",
    ],
    entry_points={
        "console_scripts": [
            "promptix=promptix.main:main",
        ],
    },
)
