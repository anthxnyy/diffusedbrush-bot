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
            self.notify_saved_submitters()

    def gather_submissions(self) -> list[Submission]:
        logging.info("Gathering submissions...")
        valid_submissions = []
        submission_source = self.REDDIT_API.submission("1167iaj")
        for comment in submission_source.comments:
            valid_comment = True
            if "SUBJECT: " in comment.body:
                for reply in comment.replies:
                    if ("☑️" in reply.body) or ("✅" in reply.body):
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

    def notify_saved_submitters(self) -> None:
        logging.info("Replying to submitters of new submissions...")
        submission_links = [
            self.new_submissions[i].link
            for i in range(len(self.new_submissions))
        ]
        for i in submission_links:
            submission = self.REDDIT_API.comment(url=i)
            submission.reply("☑️")
        logging.info("Replied to submitters of new submissions")

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

    @staticmethod
    def notify_deleted_submitters(
        REDDIT_API, deleted_posts: list[dict]
    ) -> None:
        logging.info("Replying to submitter(s) of deleted post(s)...")
        for deleted_post in deleted_posts:
            comment = REDDIT_API.comment(url=deleted_post["prompt_link"])
            if comment.author is not None:
                comment.reply("❌")
        logging.info("Replied to submitter(s) of deleted post(s)")


class Prompt:
    def __init__(self) -> None:
        self.author, self.subject, self.link = self.prompt_info()
        self.keywords = self.generate_keywords()
        self.body = self.generate_prompt()

    def prompt_info(self) -> tuple[str]:
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
        with open("promptings.json", "r") as file:
            promptings = json.load(file)
            keywords_list = promptings["keywords"]
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
        with open("promptings.json", "r") as file:
            promptings = json.load(file)
            negative_prompts = promptings["negative_prompts"]
        for attempt in range(3):
            try:
                result = self.STABILITY_API.generate(
                    prompt=f"{self.prompt}, {negative_prompts}",
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
                    if artifact.finish_reason == generation.FILTER:
                        logging.critical(
                            f"Art activated safety filter, retrying ({attempt}/3)..."  # noqa: E501
                        )
                        continue
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
        try:
            self.send_post()
            self.approve()
            self.comment_post_info()
            self.delete_from_data()
            self.notify_author()
            ManagePosts.store_post(self.current_post)
        except Exception as e:
            logging.error(e)
            logging.error("Error posting to Reddit, shutting down...")
            quit()

    def send_post(self) -> None:
        logging.info("Posting to Reddit...")
        self.REDDIT_API.subreddit("diffusedgallery").submit(
            title=self.prompt.subject,
            flair_id=os.environ["REDDIT_FLAIR_ID"],
            url=self.art.imgur_link,
        )
        for post in self.REDDIT_API.redditor("diffusedbrush").new(limit=1):
            self.current_post = Post(
                author=str(self.prompt.author),
                subject=self.prompt.subject,
                prompt_link=self.prompt.link,
                post_link=post.id,
                imgur_link=self.art.imgur_link,
                created_utc=post.created_utc,
            )
        self.target = self.REDDIT_API.submission(id=self.current_post.post_link)
        logging.info(f"Posted: http://redd.it/{self.current_post.post_link}/")

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
        self.target.mod.approve()
        logging.info("Post approved")

    def delete_from_data(self) -> None:
        ManageSubmissions.remove_submission()

    def notify_author(self) -> str:
        logging.info("Notifying author of subject use...")
        submission = self.REDDIT_API.comment(url=self.current_post.prompt_link)
        submission.reply(f"✅ http://redd.it/{self.current_post.post_link}/")
        logging.info("Notified author of subject use")


class ManagePosts:
    def __init__(self, REDDIT_API: praw.Reddit) -> None:
        self.REDDIT_API = REDDIT_API
        self.deleted_posts = self.gather_deleted_posts()
        if self.deleted_posts:
            self.remove_deleted_posts()
            ManageSubmissions.notify_deleted_submitters(
                self.REDDIT_API, self.deleted_posts
            )

    @staticmethod
    def store_post(post_to_save: Post) -> None:
        logging.info("Storing post information...")
        with open("live_posts.json", "r") as file:
            posts = json.load(file)
        posts.append(
            {
                "author": post_to_save.author,
                "subject": post_to_save.subject,
                "prompt_link": post_to_save.prompt_link,
                "post_link": f"http://redd.it/{post_to_save.post_link}/",
                "imgur_link": post_to_save.imgur_link,
                "created_utc": post_to_save.created_utc,
            }
        )
        posts = sorted(
            posts,
            key=lambda post: post["created_utc"],
        )
        with open("live_posts.json", "w") as file:
            json.dump(posts, file, indent=2)
        logging.info("Post information stored")

    def gather_deleted_posts(self) -> list[dict]:
        logging.info("Gathering deleted posts...")
        deleted_posts = []
        with open("live_posts.json", "r") as file:
            posts = json.load(file)
        for post in posts:
            post_id = post["post_link"].split("/")[3]
            test_post = self.REDDIT_API.submission(post_id)
            if test_post.author is None:
                deleted_posts.append(post)
        if len(deleted_posts) != 0:
            logging.info("Deleted post(s) gathered")
            for i in range(len(deleted_posts)):
                logging.info(
                    f"Deleted post {i + 1} of {len(deleted_posts)}: {deleted_posts[i]['subject']}"  # noqa: E501
                )
            return deleted_posts
        else:
            logging.info("No deleted posts found")
            return None

    def remove_deleted_posts(self) -> None:
        logging.info("Removing deleted posts...")
        with open("live_posts.json", "r") as file:
            posts = json.load(file)
        for deleted_post in self.deleted_posts:
            for post in posts:
                if post["post_link"] == deleted_post["post_link"]:
                    posts.remove(post)
        with open("live_posts.json", "w") as file:
            json.dump(posts, file, indent=2)
        logging.info("Deleted post(s) removed")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,
    )
    logging.critical("STARTING BOT")

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
    ManagePosts(REDDIT_API)
    ManageSubmissions.verify_submissions()
    selected_prompt = Prompt()
    generated_art = Art(STABILITY_API, IMGUR_API, selected_prompt.body)
    RedditPost(REDDIT_API, selected_prompt, generated_art)
    logging.critical("BOT COMPLETED TASKS SUCCESSFULLY")


# MAIN


if __name__ == "__main__":
    main()
