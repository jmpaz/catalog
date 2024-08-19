from setuptools import setup, find_packages
import re


def get_requirements():
    with open("requirements.txt") as f:
        required = f.read().splitlines()
    return [req for req in required if re.match(r"^(?!git\+)[\w-]+", req)]


with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()


setup(
    name="catalog",
    version="0.0.2",
    packages=find_packages(),
    install_requires=get_requirements(),
    entry_points={"console_scripts": ["catalog = catalog.cli:cli"]},
    author="jmpaz",
    description="Library and CLI for managing and processing media",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/jmpaz/catalog",
    python_requires=">=3.6",
)
