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


@dataclass
class Submission:
    author: str
    subject: str
    link: str
    created_utc: str


class ManageSubmissions(ABC):
    @abstractmethod
    def gather_submissions(self):
        pass

    @abstractmethod
    def store_submissions(self):
        pass

    @abstractmethod
    def notify_submitters(self):
        pass

    @abstractmethod
    def remove_submission(self):
        pass


class RedditSubmissions(ManageSubmissions):
    def __init__(self, REDDIT_API):
        self.REDDIT_API = REDDIT_API
        self.submissions = self.gather_submissions()
        self.store_submissions()
        # self.notify_submitters()

    def gather_submissions(self):
        logging.info("Gathering Reddit submissions...")
        valid_submissions = []
        submission_source = self.REDDIT_API.submission("1167iaj")
        for comment in submission_source.comments:
            if "SUBJECT: " in comment.body:
                for reply in comment.replies:
                    if (reply.is_submitter) and (
                        ("IMAGE POSTED" == reply.body)
                        or ("SUBJECT ACCEPTED" == reply.body)
                    ):
                        continue
                valid_submissions.append(
                    Submission(
                        author=comment.author.name,
                        subject=comment.body.replace("SUBJECT: ", "").strip(),
                        link=f"https://reddit.com{comment.permalink}",
                        created_utc=comment.created_utc,
                    )
                )
        logging.info(f"New submissions found: {len(valid_submissions)}")
        return valid_submissions

    def store_submissions(self):
        logging.info("Storing new Reddit submissions...")
        with open("reddit_submissions.json", "r") as old_file:
            updated_file = json.load(old_file)
        with open("reddit_submissions.json", "w") as old_file:
            for new_submission in self.submissions:
                if new_submission.link in [
                    submission["link"] for submission in updated_file
                ]:
                    continue
                updated_file.append(
                    {
                        "author": new_submission.author,
                        "subject": new_submission.subject,
                        "link": new_submission.link,
                        "created_utc": new_submission.created_utc,
                    }
                )
            updated_file = sorted(
                updated_file,
                key=lambda submission: submission["created_utc"],
            )
            json.dump(updated_file, old_file, indent=2)
        logging.info("New submissions stored")

    def notify_submitters(self):
        logging.info("Replying to sources of new Reddit submissions...")
        submission_links = [
            self.submissions[i].link for i in range(len(self.submissions))
        ]
        for i in submission_links:
            submission = self.REDDIT_API.comment(url=i)
            submission.reply("SUBJECT ACCEPTED")
        logging.info("Replied to sources of new Reddit submissions")

    @staticmethod
    def remove_submission(selected_submission):
        logging.info("Removing selected submission from Reddit submissions...")
        with open("reddit_submissions.json", "r") as old_file:
            updated_file = json.load(old_file)
        with open("reddit_submissions.json", "w") as old_file:
            for i in range(len(updated_file)):
                if updated_file[i]["link"] == selected_submission:
                    del updated_file[i]
                    break
            json.dump(updated_file, old_file, indent=2)
        logging.info("Removed selected submission from Reddit submissions")


class Prompt:
    def __init__(self):
        self.source, self.file_source = self.get_source()
        self.subject = self.get_subject()
        self.keywords = self.generate_keywords()
        self.text = f"{self.subject}, {self.keywords}"
        logging.info(f"Prompt generated: {self.text}")

    def get_source(self):
        logging.info("Getting source of subject...")
        source = "Reddit"
        file = "reddit_submissions.json"
        logging.info(f"Source selected: {source}")
        return source, file

    def get_subject(self):
        subject = ""
        subject_link = ""
        if self.source == "Reddit":
            logging.info(f"Getting subject from {self.file_source} ...")
            with open(self.file_source, "r") as file:
                submissions = json.load(file)
            subject = submissions[0]["subject"]
            subject_link = submissions[0]["link"]
            del submissions[0]
            with open(self.file_source, "w") as file:
                json.dump(submissions, file, indent=2)
        logging.info(f"Subject selected: {subject}")
        self.remove_subject(subject_link)
        return subject

    def remove_subject(self, link):
        if self.source == "Reddit":
            RedditSubmissions.remove_submission(link)

    def generate_keywords(self):
        logging.info("Generating keywords...")
        selected_keywords = random.choices(k.KEYWORDS, k=random.randint(2, 4))
        selected_keywords = ", ".join(selected_keywords)
        logging.info("Keywords generated")
        return selected_keywords


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


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,
    )
    logging.info("STARTING BOT")

    try:
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
    except Exception as e:
        logging.error(e)
        logging.error("Error connecting to APIs, shutting down...")
        quit()

    RedditSubmissions(REDDIT_API)
    prompt = Prompt()
    # art = Art(STABILITY_API, IMGUR_API, prompt)
    # imgur_link = art.imgur_link
    # RedditPost(REDDIT_API, prompt, imgur_link).send()
    # logging.info("ENDING BOT")


# MAIN


if __name__ == "__main__":
    main()
