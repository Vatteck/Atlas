
import os

from setuptools import setup, find_packages

DESCRIPTION = (
    "Arch-focused graphical package manager (Arch/AUR, Flatpak, AppImage)"
)

AUTHOR = "Vatteck"
AUTHOR_EMAIL = "vatteck@github.com"
NAME = 'atlas'
URL = "https://github.com/Vatteck/" + NAME

file_dir = os.path.dirname(os.path.abspath(__file__))

if os.getenv('ATLAS_SETUP_NO_REQS'):
    requirements = []
else:
    with open(f'{file_dir}/requirements.txt', 'r') as f:
        requirements = [line.strip() for line in f.readlines() if line]


with open(file_dir + '/{}/__init__.py'.format(NAME), 'r') as f:
    exec(f.readlines()[0])


setup(
    name=NAME,
    version=eval('__version__'),
    description=DESCRIPTION,
    long_description=DESCRIPTION,
    author=AUTHOR,
    author_email=AUTHOR_EMAIL,
    python_requires=">=3.10",
    url=URL,
    packages=find_packages(exclude=["tests.*", "tests"]),
    package_data={NAME: ["view/resources/locale/*", "view/resources/img/*", "view/resources/style/*", 'view/resources/style/*/img/*', "gems/*/resources/img/*", "gems/*/resources/locale/*", "desktop/*", "view/webview/*"]},
    install_requires=requirements,
    test_suite="tests",
    entry_points={
        "console_scripts": [
            "{name}={name}.app:main".format(name=NAME),
            "{name}-cli={name}.cli.app:main".format(name=NAME)
        ]
    },
    include_package_data=True,
    license="zlib/libpng",
    classifiers=[
        'Topic :: Utilities',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3.14'
    ],
    zip_safe=False
)
