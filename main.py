import io
import json
import logging
import os
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import praw
import pyimgur
import stability_sdk.interfaces.gooseai.generation.generation_pb2 as generation
from PIL import Image
from stability_sdk import client

import keywords as k


# CLASSES


class Prompt:
    def __init__(self):
        logging.info("Creating prompt...")
        self.prompt = self.create_subject()
        logging.info("Prompt created")
        logging.info(f"Prompt: {self.prompt}")

    @staticmethod
    def create_subject():
        with open("prompts.txt", "r") as file:
            first_line = file.readline()
        selected_keywords = random.choices(k.KEYWORDS, k=random.randint(2, 4))
        selected_keywords = ", ".join(selected_keywords)
        prompt = f"{first_line}, {selected_keywords}"
        return prompt

    @staticmethod
    def remove_subject():
        with open("prompts.txt", "r") as file:
            lines = file.readlines()
        with open("prompts.txt", "w") as file:
            file.writelines(lines[1:])


class Art:
    def __init__(self, STABILITY_API, IMGUR_API, prompt):
        logging.info("Creating art...")
        self.STABILITY_API = STABILITY_API
        self.IMGUR_API = IMGUR_API
        self.prompt = prompt
        while True:
            try:
                self.file = self.create()
                self.imgur_link = self.create_imgur_link()
                logging.info(f"Art created: {self.imgur_link}")
                if self.confirm():
                    logging.info("IMAGE CONFIRMED")
                    break
                else:
                    logging.info("IMAGE REJECTED")
                    logging.info("Creating new art...")
                    continue
            except Exception as e:
                logging.error(e)
                logging.error("Error creating art, shutting down...")
                quit()

    def create(self):
        result = self.STABILITY_API.generate(
            prompt=self.prompt,
            steps=35,
            cfg_scale=10,
            width=512,
            height=512,
            samples=1,
            guidance_models="stable-diffusion-512-v2-1",
        )
        for resp in result:
            for artifact in resp.artifacts:
                if artifact.type == generation.ARTIFACT_IMAGE:
                    sd_img = Image.open(io.BytesIO(artifact.binary))
                    sd_img.save("sd_img.png")

    def create_imgur_link(self):
        PATH = "sd_img.png"
        image = self.IMGUR_API.upload_image(PATH, title=self.prompt)
        return image.link

    @staticmethod
    def confirm():
        while True:
            confirmation = input("CONFIRM IMAGE? [Y/n]: ")
            if confirmation in ["Y", "n"]:
                if confirmation == "Y":
                    return True
                else:
                    return False


class Post(ABC):
    @abstractmethod
    def send(self):
        pass


class RedditPost(Post):
    def __init__(self, REDDIT_API, title, imgur_link):
        self.REDDIT_API = REDDIT_API
        self.title = title
        self.imgur_link = imgur_link

    def send(self):
        logging.info("Posting to Reddit...")
        while True:
            try:
                self.REDDIT_API.subreddit("diffusedgallery").submit(
                    title=self.title,
                    flair_id=os.environ["REDDIT_FLAIR_ID"],
                    url=self.imgur_link,
                )
                for post in self.REDDIT_API.redditor("diffusedbrush").new(
                    limit=1
                ):
                    logging.info(f"Posted to Reddit: http://redd.it/{post}/")
                    self.approve(post)
                    Prompt.remove_subject()
                break
            except Exception as e:
                logging.error(e)
                logging.error("Error posting to Reddit, shutting down...")
                quit()

    @staticmethod
    def approve(post):
        logging.info("Sleeping for 10 seconds to approve post...")
        time.sleep(10)
        post.mod.approve()
        logging.info("Post approved")


class InstaPost(Post):
    def __init__(self, prompt):
        self.prompt = prompt

    def send(self):
        pass


@dataclass
class Submission:
    prompt: str
    comment_link: str
    comment_link = str
    time_created = str
    permalink = str


class StoreSubmissions:
    def __init__(self, REDDIT_API):
        self.REDDIT_API = REDDIT_API
        self.submissions = self.gather_submissions()

    def gather_submissions(self):
        logging.info("Storing submissions...")
        source = self.REDDIT_API.submission("1167iaj")
        valid_submissions = {}
        for comment in source.comments:
            if "PROMPT: " not in comment.body:
                continue
            valid_prompt = True
            for reply in comment.replies:
                if (reply.is_submitter) and ("IMAGE POSTED" == reply.body):
                    valid_prompt = False
            if valid_prompt:
                valid_submissions.append(
                    Submission(
                        prompt=comment.body.replace("PROMPT: ", ""),
                        author=comment.author.name,
                        comment_link=f"http://redd.it/{comment.id}",
                        time_created=comment.created_utc,
                        permalink=comment.permalink,
                    )
                )
        logging.info("Submissions stored")

    @staticmethod
    def store():
        with open("prompts.txt", "a") as f:
            f.write(comment.body.replace("PROMPT: ", "") + "\n")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,
    )
    logging.info("STARTING BOT")
    STABILITY_API = client.StabilityInference(
        key=os.environ["STABILITY_KEY"],
        engine="stable-diffusion-v1-5",
    )
    logging.info("Stability API connected")
    REDDIT_API = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        password=os.environ["REDDIT_PASSWORD"],
        user_agent="bot by u/diffusedbrush",
        username="diffusedbrush",
    )
    logging.info("Reddit API connected")
    IMGUR_API = pyimgur.Imgur(os.environ["IMGUR_CLIENT_ID"])
    logging.info("Imgur API connected")

    StoreSubmissions(REDDIT_API)
    # prompt = Prompt().prompt
    # art = Art(STABILITY_API, IMGUR_API, prompt)
    # imgur_link = art.imgur_link
    # RedditPost(REDDIT_API, prompt, imgur_link).send()
    # logging.info("ENDING BOT")


# MAIN


if __name__ == "__main__":
    main()
