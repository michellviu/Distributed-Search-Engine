"""
Setup script for Distributed Search Engine
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text() if readme_file.exists() else ""

setup(
    name="distributed-search-engine",
    version="0.1.0",
    author="Distributed Systems Course",
    description="A centralized document search engine system",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/michellviu/Distributed-Search-Engine",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    py_modules=["main_server", "main_client"],  # incluir módulos sueltos
    entry_points={
        "console_scripts": [
            "search-server=main_server:main",
            "search-client=main_client:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Education",
        "Topic :: System :: Distributed Computing",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        # No external dependencies required
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "search-server=main_server:main",
            "search-client=main_client:main",
        ],
    },
)
