#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""The setup script."""

from setuptools import setup, find_packages

with open("README.md") as readme_file:
    readme = readme_file.read()

with open("requirements.txt") as f:
    requirements = f.read().split("\n")

setup_requirements = ["pytest-runner"]
test_requirements = ["pytest"]

setup(
    name="slack_cleaner2",
    description="Slack Cleaner2 is an improved slack cleaner version using a python first approach",
    version="3.0.3",
    license="MIT license",
    long_description=readme,
    long_description_content_type="text/markdown",
    keywords="slack_cleaner2 slack slack-cleaner",
    author="Samuel Gratzl",
    author_email="sam@sgratzl.com",
    url="https://github.com/sgratzl/slack_cleaner2",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
    ],
    install_requires=requirements,
    include_package_data=True,
    packages=find_packages(include=["slack_cleaner2"]),
    setup_requires=setup_requirements,
    test_suite="tests",
    tests_require=test_requirements,
    zip_safe=False,
        entry_points={
        'console_scripts': [
            'slack-cleaner2 = slack_cleaner2.cli:main'
        ]
    }
)
