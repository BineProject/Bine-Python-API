from distutils.core import setup

setup(
    name="bine",
    packages=["bine"],
    version="0.2",
    license="MIT",
    description="Python API for creating serverside backend for Bine dApps",
    author="LeaveMyYard",
    url="https://github.com/BineProject/Bine-Python-API",
    install_requires=["mysql-connector-python", "web3",],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.8",
    ],
)
