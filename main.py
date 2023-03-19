import io
import json
import logging
import os
import random
import time
from dataclasses import dataclass

import praw
import pyimgur
import stability_sdk.interfaces.gooseai.generation.generation_pb2 as generation
from PIL import Image
from stability_sdk import client

# CLASSES


@dataclass
class Submission:
    author: str
    subject: str
    link: str
    created_utc: str


class ManageSubmissions:
    def __init__(self, REDDIT_API: praw.Reddit) -> None:
        self.REDDIT_API = REDDIT_API
        self.handle_deleted_submissions()
        self.new_submissions = self.gather_submissions()
        if len(self.new_submissions) > 0:
            self.store_submissions()
            self.notify_submitters()
        self.verify_submissions()

    def handle_deleted_submissions(self) -> None:
        logging.info("Handling deleted submissions...")
        with open("reddit_submissions.json", "r") as file:
            updated_file = json.load(file)
        with open("reddit_submissions.json", "w") as old_file:
            for submission in updated_file:
                if (
                    self.REDDIT_API.comment(url=submission["link"]).author
                    is None
                ) and ():
                    continue
                else:
                    updated_file.append(submission)
            json.dump(updated_file, old_file, indent=2)
        logging.info("Handled deleted submissions")

    def gather_submissions(self) -> list[Submission]:
        logging.info("Gathering Reddit submissions...")
        valid_submissions = []
        valid_comment = True
        subject_confirmation = False
        submission_source = self.REDDIT_API.submission("1167iaj")
        for comment in submission_source.comments:
            if "SUBJECT: " in comment.body:
                for reply in comment.replies:
                    if "SUBJECT ACCEPTED" in reply.body:
                        save_confirmation = reply.permalink
                        subject_confirmation = True
                    if "IMAGE POSTED: " in reply.body:
                        valid_comment = False
                if valid_comment and subject_confirmation:
                    valid_submissions.append(
                        Submission(
                            author=comment.author.name,
                            subject=comment.body.replace(
                                "SUBJECT: ", ""
                            ).strip(),
                            origin=f"https://reddit.com{comment.permalink}",
                            confirmation=f"https://reddit.com{save_confirmation}",  # noqa: E501
                            created_utc=comment.created_utc,
                        )
                    )
        if len(valid_submissions) == 0:
            logging.info("No new submissions found")
        else:
            logging.info(f"New submissions found: {len(valid_submissions)}")
            for i in range(len(valid_submissions)):
                logging.info(
                    f"Submission {i + 1} of {len(valid_submissions)}: {valid_submissions[i].subject}"  # noqa: E501
                )
        return valid_submissions

    def store_submissions(self) -> None:
        logging.info("Storing new Reddit submissions...")
        with open("reddit_submissions.json", "r") as old_file:
            updated_file = json.load(old_file)
        with open("reddit_submissions.json", "w") as old_file:
            for new_submission in self.new_submissions:
                if new_submission.link in [
                    submission["link"] for submission in updated_file
                ]:
                    continue
                updated_file.append(
                    {
                        "author": new_submission.author,
                        "subject": new_submission.subject.strip(),
                        "origin": new_submission.origin,
                        "confirmation": new_submission.confirmation,
                        "created_utc": new_submission.created_utc,
                    }
                )
            updated_file = sorted(
                updated_file,
                key=lambda submission: submission["created_utc"],
            )
            json.dump(updated_file, old_file, indent=2)
        logging.info("New submissions stored")

    def notify_submitters(self) -> None:
        logging.info("Replying to submitters of new Reddit submissions...")
        submission_links = [
            self.new_submissions[i].link
            for i in range(len(self.new_submissions))
        ]
        for i in submission_links:
            submission = self.REDDIT_API.comment(url=i)
            submission.reply("SUBJECT ACCEPTED")
        logging.info("Replied to submitters of new Reddit submissions")

    @staticmethod
    def remove_submission() -> None:
        logging.info("Removing selected submission from Reddit submissions...")
        with open("reddit_submissions.json", "r") as old_file:
            updated_file = json.load(old_file)
        with open("reddit_submissions.json", "w") as old_file:
            del updated_file[0]
            json.dump(updated_file, old_file, indent=2)
        logging.info("Removed selected submission from Reddit submissions")

    @staticmethod
    def verify_submissions() -> None:
        with open("reddit_submissions.json", "r") as file:
            if json.load(file) == []:
                logging.info("List of Reddit submissions is empty")
                logging.info("Shutting down...")
                exit()


class Prompt:
    def __init__(self) -> None:
        self.source, self.file_source = self.get_source()
        self.author, self.subject, self.link = self.prompt_info()
        self.keywords = self.generate_keywords()
        self.text = f"{self.subject}, {self.keywords}"
        logging.info(f"Prompt generated: {self.text}")

    def get_source(self) -> tuple[str, str]:
        logging.info("Getting source of subject...")
        platform = "Reddit"
        file = "reddit_submissions.json"
        logging.info(f"Source selected: {platform}")
        return platform, file

    def prompt_info(self) -> tuple[str, str, str]:
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

    def generate_keywords(self) -> str:
        logging.info("Generating keywords...")
        with open("keywords.json", "r") as file:
            keywords_list = json.load(file)
        selected_keywords = random.choices(
            keywords_list, k=random.randint(2, 4)
        )
        selected_keywords = ", ".join(selected_keywords)
        selected_keywords += ", 4k, 8k"
        logging.info("Keywords generated")
        return selected_keywords


class Art:
    def __init__(
        self, STABILITY_API: object, IMGUR_API: object, prompt: Prompt
    ) -> None:
        self.STABILITY_API = STABILITY_API
        self.IMGUR_API = IMGUR_API
        self.prompt = prompt
        self.file = self.generate_art()
        logging.info("Art created, creating Imgur link...")
        self.imgur_link = self.create_imgur()
        logging.info(f"Imgur link created: {self.imgur_link}")

    def generate_art(self) -> None:
        logging.info("Creating art...")
        try:
            result = self.STABILITY_API.generate(
                prompt=self.prompt.text,
                steps=35,
                cfg_scale=10,
                width=512,
                height=512,
                samples=1,
                guidance_preset=generation.GUIDANCE_PRESET_FAST_GREEN,
            )
        except Exception as e:
            logging.error(e)
            logging.error("Error creating art, shutting down...")
            quit()
        for resp in result:
            for artifact in resp.artifacts:
                if artifact.type == generation.ARTIFACT_IMAGE:
                    sd_img = Image.open(io.BytesIO(artifact.binary))
                    sd_img.save("sd_img.png")

    def create_imgur(self) -> str:
        PATH = "sd_img.png"
        image = self.IMGUR_API.upload_image(PATH, title=self.prompt.text)
        return image.link


class RedditPost:
    def __init__(self, REDDIT_API: object, prompt: Prompt, art: Art) -> None:
        self.REDDIT_API = REDDIT_API
        self.prompt = prompt
        self.imgur_link = art.imgur_link
        self.post_link = str

    def send(self) -> None:
        logging.info("Posting to Reddit...")
        try:
            self.REDDIT_API.subreddit("diffusedgallery").submit(
                title=self.prompt.subject,
                flair_id=os.environ["REDDIT_FLAIR_ID"],
                url=self.imgur_link,
            )
            for post in self.REDDIT_API.redditor("diffusedbrush").new(limit=1):
                self.post_link = post
            logging.info(f"Posted to Reddit: http://redd.it/{self.post_link}/")
            self.comment_post_info()
            self.approve()
            self.delete_subject()
            self.notify_author()
        except Exception as e:
            logging.error(e)
            logging.error("Error posting to Reddit, shutting down...")
            quit()

    def comment_post_info(self) -> None:
        logging.info("Commenting information on post...")
        text = [
            f"**Subject Idea By:** u/{self.prompt.author}\n\n",
            f"**Keywords Used:** {self.prompt.keywords}\n\n",
            f"**Original Submission:** {self.prompt.link}\n\n",
            "**Stable Diffusion Engine Settings:** \n\n",
            "* Engine: stable-diffusion-512-v2-1\n",
            "* Steps: 35\n",
            "* CFG Scale: 10\n",
            "* Width: 512\n",
            "* Height: 512\n",
            "* CLIP Guidance: Enabled\n",
        ]
        text = "".join(text)
        self.post_link.reply(text)
        logging.info("Commented information on post")

    def approve(self) -> None:
        logging.info("Approving post, sleeping for 10 seconds...")
        time.sleep(10)
        self.post_link.mod.approve()
        logging.info("Post approved")

    def notify_author(self) -> None:
        logging.info("Notifying author of subject use...")
        submission = self.REDDIT_API.comment(url=self.prompt.link)
        submission.reply(f"IMAGE POSTED: http://redd.it/{self.post_link}/")
        logging.info(f"Original author submission: {self.prompt.link}")
        logging.info("Notified author of subject use")

    def delete_subject(self) -> None:
        ManageSubmissions.remove_submission()


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

    ManageSubmissions(REDDIT_API)
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
