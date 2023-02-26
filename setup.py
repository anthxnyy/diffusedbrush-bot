from setuptools import setup

setup(
    name="diffusedbrush-bot",
    version="0.1.2",
    description="AI art based on trending topics and user generated prompts with randomized descriptors. Art automatically posted on Reddit.",
    license="MIT",
    author="Anthony Toyco",
    url="https://github.com/anthonytoyco/diffusedbrush-bot",
    python_requires="==3.10.10",
    packages=["diffusedbrush-bot"],
    install_requires=[
        "Pillow",
        "praw",
        "pyimgur",
        "stability_sdk",
    ],
)
