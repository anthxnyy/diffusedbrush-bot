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
        self.new_submissions = self.gather_submissions()
        if len(self.new_submissions) > 0:
            self.store_submissions()
            self.notify_submitters()
        self.verify_submissions()
        # self.gather_deleted_submissions()
        # self.remove_deleted_submissions()

    def gather_submissions(self) -> list[Submission]:
        logging.info("Gathering submissions...")
        valid_submissions = []
        submission_source = self.REDDIT_API.submission("1167iaj")
        for comment in submission_source.comments:
            valid_comment = True
            if "SUBJECT: " in comment.body:
                for reply in comment.replies:
                    if ("⏰" in reply.body) or ("✅" in reply.body):
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
        if len(valid_submissions) != 0:
            logging.info(f"New submissions found: {len(valid_submissions)}")
            for i in range(len(valid_submissions)):
                logging.info(
                    f"Submission {i + 1} of {len(valid_submissions)}: {valid_submissions[i].subject}"  # noqa: E501
                )
        else:
            logging.info("No new submissions found")
        return valid_submissions

    def store_submissions(self) -> None:
        logging.info("Storing new submissions...")
        with open("submissions.json", "r") as old_file:
            updated_file = json.load(old_file)
        for new_submission in self.new_submissions:
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
        with open("submissions.json", "w") as old_file:
            json.dump(updated_file, old_file, indent=2)
        logging.info("New submissions stored")

    def notify_submitters(self) -> None:
        logging.info("Replying to submitters of new submissions...")
        submission_links = [
            self.new_submissions[i].link
            for i in range(len(self.new_submissions))
        ]
        for i in submission_links:
            submission = self.REDDIT_API.comment(url=i)
            submission.reply("⏰")
        logging.info("Replied to submitters of new submissions")

    def gather_deleted_submissions(self) -> None:
        logging.info("Gathering deleted submissions...")
        with open("posts.json", "r") as file:
            posts = json.load(file)
        deleted_posts = []
        for post in posts:
            current_post = self.REDDIT_API.submission(id=post["id"])
            if (current_post.author is None) and (
                current_post.is_robot_indexable is False
            ):
                deleted_posts.append(current_post)

    @staticmethod
    def remove_submission() -> None:
        logging.info("Removing selected submission from submissions.json...")
        with open("submissions.json", "r") as old_file:
            updated_file = json.load(old_file)
        del updated_file[0]
        with open("submissions.json", "w") as old_file:
            json.dump(updated_file, old_file, indent=2)
        logging.info("Removed selected submission from submissions.json")

    @staticmethod
    def verify_submissions() -> None:
        with open("submissions.json", "r") as file:
            if len(json.load(file)) == 0:
                logging.info("List of submissions is empty")
                logging.info("Shutting down...")
                exit()


class Prompt:
    def __init__(self) -> None:
        self.author, self.subject, self.link = self.prompt_info()
        self.keywords = self.generate_keywords()
        self.body = self.generate_prompt()

    def prompt_info(self) -> tuple[str, str, str]:
        logging.info("Getting oldest subject from submissions file...")
        with open("submissions.json", "r") as file:
            submissions = json.load(file)
        author = submissions[0]["author"]
        subject = submissions[0]["subject"]
        subject_link = submissions[0]["link"]
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

    def generate_prompt(self) -> str:
        logging.info("Generating prompt...")
        text = f"{self.subject}, {self.keywords}"
        logging.info(f"Prompt generated: {text}")
        return text


class Art:
    def __init__(
        self,
        STABILITY_API: client.StabilityInference,
        IMGUR_API: object,
        prompt: str,
    ) -> None:
        self.STABILITY_API = STABILITY_API
        self.IMGUR_API = IMGUR_API
        self.prompt = prompt
        self.file = self.generate_art()
        self.imgur_link = self.create_imgur()
        logging.info(f"Imgur link created: {self.imgur_link}")

    def generate_art(self) -> None:
        logging.info("Creating art...")
        try:
            result = self.STABILITY_API.generate(
                prompt=self.prompt,
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
        logging.info("Art created, creating Imgur link...")
        try:
            PATH = "sd_img.png"
            image = self.IMGUR_API.upload_image(PATH, title=self.prompt)
            return image.link
        except Exception as e:
            logging.error(e)
            logging.error("Error creating Imgur link, shutting down...")
            quit()


@dataclass
class Post:
    author: str
    subject: str
    prompt_link: str
    post_link: str
    imgur_link: str
    created_utc: str


class RedditPost:
    def __init__(
        self, REDDIT_API: praw.Reddit, prompt: Prompt, art: Art
    ) -> None:
        self.REDDIT_API = REDDIT_API
        self.prompt = prompt
        self.art = art
        self.current_post = None
        self.target = str

    def send_post(self) -> None:
        logging.info("Posting to Reddit...")
        try:
            self.REDDIT_API.subreddit("diffusedgallery").submit(
                title=self.prompt.subject,
                flair_id=os.environ["REDDIT_FLAIR_ID"],
                url=self.art.imgur_link,
            )
            for post in self.REDDIT_API.redditor("diffusedbrush").new(limit=1):
                self.current_post = Post(
                    author=post.author,
                    subject=self.prompt.subject,
                    prompt_link=self.prompt.link,
                    post_link=post.id,
                    imgur_link=self.art.imgur_link,
                    created_utc=post.created_utc,
                )
            self.target = self.REDDIT_API.submission(
                id=self.current_post.post_link
            )
            logging.info(
                f"Posted: http://redd.it/{self.current_post.post_link}/"
            )
            self.approve()
            self.comment_post_info()
            # self.delete_from_data()
            self.notify_author()
        except Exception as e:
            logging.error(e)
            logging.error("Error posting to Reddit, shutting down...")
            quit()

    def comment_post_info(self) -> None:
        logging.info("Commenting information on post...")
        text = [
            f"**Subject Idea By:** u/{self.current_post.author}\n\n",
            f"**Keywords Used:** {self.prompt.keywords}\n\n",
            f"**Original Submission:** {self.current_post.prompt_link}\n\n",
            "**Stable Diffusion Engine Settings:** \n\n",
            "* Engine: stable-diffusion-512-v2-1\n",
            "* Steps: 35\n",
            "* CFG Scale: 10\n",
            "* Width: 512\n",
            "* Height: 512\n",
            "* CLIP Guidance: Enabled\n",
        ]
        text = "".join(text)
        self.target.reply(text)
        logging.info("Commented information on post")

    def approve(self) -> None:
        logging.info("Approving post...")
        time.sleep(random.randint(10, 15))
        print(self.current_post.post_link)
        self.target.mod.approve()
        logging.info("Post approved")

    def delete_from_data(self) -> None:
        ManageSubmissions.remove_submission()

    def notify_author(self) -> str:
        logging.info("Notifying author of subject use...")
        submission = self.REDDIT_API.comment(url=self.current_post.prompt_link)
        submission.reply(f"✅ http://redd.it/{self.current_post.post_link}/")
        logging.info("Notified author of subject use")

    def store_post(self) -> None:
        logging.info("Storing post information...")
        with open("posts.json", "r") as file:
            posts = json.load(file)
        posts.append(
            {
                "author": self.current_post.author,
                "subject": self.current_post.subject,
                "prompt_link": self.current_post.prompt_link,
                "post_link": self.current_post.post_link,
                "imgur_link": self.current_post.imgur_link,
                "created_utc": self.current_post.created_utc,
            }
        )
        with open("posts.json", "w") as file:
            json.dump(posts, file, indent=2)
        logging.info("Post information stored")


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
    generated_art = Art(STABILITY_API, IMGUR_API, selected_prompt.body)
    new_post = RedditPost(REDDIT_API, selected_prompt, generated_art)
    new_post.send_post()
    """
    new_post.store_post()
    """
    logging.info("BOT COMPLETED TASKS SUCCESSFULLY")


# MAIN


if __name__ == "__main__":
    main()
