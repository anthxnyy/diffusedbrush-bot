import io
import os
import random

import praw
import pyimgur
import stability_sdk.interfaces.gooseai.generation.generation_pb2 as generation
from PIL import Image
from stability_sdk import client

import keywords as k


def get_prompt():
    # Get a list of randomized keywords to be used for the prompt
    selected_keywords = random.choices(k.KEYWORDS, k=random.randint(2, 4))
    selected_keywords = ", ".join(selected_keywords)
    # Ask user for the subject
    subject = input("Subject: ")
    print(f"Keywords Selected: {selected_keywords}")
    # Create prompt
    prompt = f"{subject}, {selected_keywords}"
    return prompt, selected_keywords


def sd_image(stability_api, prompt):
    print("\nGenerating image...")
    # Settings for image generation
    answer = stability_api.generate(
        prompt=prompt,
        steps=35,
        cfg_scale=9.5,
        width=512,
        height=512,
        samples=1,
        guidance_models="stable-diffusion-512-v2-1",
    )
    # Save image
    for resp in answer:
        for artifact in resp.artifacts:
            if artifact.type == generation.ARTIFACT_IMAGE:
                sd_img = Image.open(io.BytesIO(artifact.binary))
                sd_img.save("sd_img.png")
                print("Image generated!")


def imgur_link(prompt):
    PATH = "sd_img.png"
    img = pyimgur.Imgur(os.environ["IMGUR_CLIENT_ID"])
    imgur_img = img.upload_image(PATH, title=prompt)
    print(f"\nLink to image: {imgur_img.link}")
    return imgur_img


def post(reddit_api, prompt, sd_image_url):
    while True:
        # Ask the user if they want to post the image
        confirmation = input("\nWould you like to post the image? [Y/n]: ")
        if confirmation in ["Y", "n"]:
            if confirmation == "Y":
                print("\nPosting...")
                # Post generated image to r/diffusedgallery
                reddit_api.subreddit("diffusedgallery").submit(
                    title=prompt,
                    flair_id="89263ac6-b0ff-11ed-a9d7-a2ed7812b990",
                    url=sd_image_url.link,
                )
                for submission in reddit_api.redditor("diffusedbrush").new(
                    limit=1
                ):
                    print("Posted!")
                    print(
                        f"View it here: https://www.reddit.com/r/diffusedgallery/comments/{submission}/"
                    )
            break
        else:
            print("ERROR: Please enter a valid input!")


def store_submissions(post):
    suggestions = post
    for comment in suggestions.comments:
        for reply in comment.replies:
            if (reply.is_submitter) and ("IMAGE POSTED" == reply.body):
                print("test")
    for comment in suggestions.comments:
        for reply in comment.replies:
            if (reply.is_submitter) and ("PROMPT SELECTED" == reply.body):
                print("test")


def main():
    # Connect to Stability.ai
    stability_api = client.StabilityInference(
        key=os.environ["STABILITY_KEY"],
        verbose=True,
        engine="stable-diffusion-v1-5",
    )
    # Connect to Reddit diffusedbrush app
    reddit_api = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        password=os.environ["REDDIT_PASSWORD"],
        user_agent="bot by u/diffusedbrush",
        username="diffusedbrush",
    )

    # store_submissions(reddit_api.submission("1167iaj"))
    exit(1)

    # Ask user for prompts and keywords
    prompt, used_keywords = get_prompt()

    # Generate image using prompt
    sd_image(stability_api, prompt)

    # Upload generated image to Imgur
    sd_image_url = imgur_link(prompt)

    # Post to r/diffusedgallery
    post(reddit_api, prompt, sd_image_url)
    """
    TODO:

    migrate to oop and classes
        image
        prompt
        comment
        post

    approve posts after set time

    store prompts in a file
        reply to comment when prompt is used with link to post
        delete prompt from file

    use prompts from file to generate images
        leave comment on post to creator of prompt and their username

    github actions
        automatic and through discussions/comments

    mirgrate to numpy randomness, no duplicate keywords

    improve randomness of keywords for better looking images

    also post the image to instagram diffusedbrush

    use ai to generate improved prompts

    github docs
    """


if __name__ == "__main__":
    main()
