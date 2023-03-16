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
        self.notify_submitters()

    def gather_submissions(self):
        logging.info("Gathering Reddit submissions...")
        valid_submissions = []
        valid_comment = True
        submission_source = self.REDDIT_API.submission("1167iaj")
        for comment in submission_source.comments:
            if "SUBJECT: " in comment.body:
                for reply in comment.replies:
                    if (("IMAGE POSTED: ") in reply.body) or (
                        ("SUBJECT ACCEPTED") in reply.body
                    ):
                        valid_comment = False
                if valid_comment:
                    valid_submissions.append(
                        Submission(
                            author=comment.author.name,
                            subject=comment.body.replace(
                                "SUBJECT: ", ""
                            ).strip(),
                            link=f"https://reddit.com{comment.permalink}",
                            created_utc=comment.created_utc,
                        )
                    )
        logging.info(f"New submissions found: {len(valid_submissions)}")
        for i in range(len(valid_submissions)):
            logging.info(
                f"Submission {i + 1} of {len(valid_submissions)}: {valid_submissions[i].subject}"  # noqa: E501
            )
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
                        "subject": new_submission.subject.strip(),
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
        logging.info("Replying to submitters of new Reddit submissions...")
        submission_links = [
            self.submissions[i].link for i in range(len(self.submissions))
        ]
        for i in submission_links:
            submission = self.REDDIT_API.comment(url=i)
            submission.reply("SUBJECT ACCEPTED")
        logging.info("Replied to submitters of new Reddit submissions")

    @staticmethod
    def remove_submission():
        logging.info("Removing selected submission from Reddit submissions...")
        with open("reddit_submissions.json", "r") as old_file:
            updated_file = json.load(old_file)
        with open("reddit_submissions.json", "w") as old_file:
            del updated_file[0]
            json.dump(updated_file, old_file, indent=2)
        logging.info("Removed selected submission from Reddit submissions")


class Prompt:
    def __init__(self):
        self.source, self.file_source = self.get_source()
        self.author, self.subject, self.link = self.prompt_info()
        self.keywords = self.generate_keywords()
        self.text = f"{self.subject}, {self.keywords}"
        logging.info(f"Prompt generated: {self.text}")

    def get_source(self):
        logging.info("Getting source of subject...")
        source = "Reddit"
        file = "reddit_submissions.json"
        logging.info(f"Source selected: {source}")
        return source, file

    def prompt_info(self):
        if self.source == "Reddit":
            logging.info(f"Getting subject from {self.file_source} ...")
            with open(self.file_source, "r") as old_file:
                submissions = json.load(old_file)
            author = submissions[0]["author"]
            subject = submissions[0]["subject"]
            subject_link = submissions[0]["link"]
            with open(self.file_source, "w") as old_file:
                json.dump(submissions, old_file, indent=2)
        logging.info(f"Subject selected: {subject}")
        return author, subject, subject_link

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
        try:
            self.file = self.generate_art()
            self.imgur_link = self.create_imgur()
            logging.info(f"Art created: {self.imgur_link}")
        except Exception as e:
            logging.error(e)
            logging.error("Error creating art, shutting down...")
            quit()

    def generate_art(self):
        result = self.STABILITY_API.generate(
            prompt=self.prompt.text,
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

    def create_imgur(self):
        PATH = "sd_img.png"
        image = self.IMGUR_API.upload_image(PATH, title=self.prompt.text)
        return image.link


class ManagePost(ABC):
    @abstractmethod
    def send(self):
        pass


class RedditPost(ManagePost):
    def __init__(self, REDDIT_API, prompt, art):
        self.REDDIT_API = REDDIT_API
        self.prompt = prompt
        self.imgur_link = art.imgur_link
        self.post_link = str

    def send(self):
        logging.info("Posting to Reddit...")
        try:
            self.REDDIT_API.subreddit("diffusedgallery").submit(
                title=self.prompt.text,
                flair_id=os.environ["REDDIT_FLAIR_ID"],
                url=self.imgur_link,
            )
            for post in self.REDDIT_API.redditor("diffusedbrush").new(limit=1):
                self.post_link = post
            logging.info(f"Posted to Reddit: http://redd.it/{self.post_link}/")
            self.comment()
            self.approve()
            self.delete_subject()
            self.notify_author()
        except Exception as e:
            logging.error(e)
            logging.error("Error posting to Reddit, shutting down...")
            quit()

    def comment(self):
        logging.info("Commenting information on post...")
        text = [
            f"**Author:** u/{self.prompt.author}\n\n",
            f"**Original Submission:** {self.prompt.link}\n\n",
            "**Stable Diffusion Engine Settings:** \n\n",
            "* Engine: stable-diffusion-512-v2-1\n",
            "* Steps: 35\n",
            "* CFG Scale: 10\n",
            "* Width: 512\n",
            "* Height: 512\n",
        ]
        text = "".join(text)
        self.post_link.reply(text)
        logging.info("Commented information on post")

    def approve(self):
        logging.info("Approving post, sleeping for 10 seconds...")
        time.sleep(10)
        self.post_link.mod.approve()
        logging.info("Post approved")

    def notify_author(self):
        logging.info("Notifying author of subject use...")
        submission = self.REDDIT_API.comment(url=self.prompt.link)
        submission.reply(f"IMAGE POSTED: http://redd.it/{self.post_link}/")
        logging.info(f"Original author submission: {self.prompt.link}")
        logging.info("Notified author of subject use")

    def delete_subject(self):
        RedditSubmissions.remove_submission()


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
            engine="stable-diffusion-512-v2-1",
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
    selected_prompt = Prompt()
    generated_art = Art(STABILITY_API, IMGUR_API, selected_prompt)
    new_post = RedditPost(REDDIT_API, selected_prompt, generated_art)
    new_post.send()
    """
    """
    logging.info("BOT COMPLETED TASKS SUCCESSFULLY")


# MAIN


if __name__ == "__main__":
    main()
