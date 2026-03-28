# RUN THIS N AMOUNT OF TIMES
import sys

from status import *
from cache import get_accounts
from config import get_llm_provider
from config import get_verbose
from config import ensure_config_file
from config import get_cardnews_config
from classes.Tts import TTS
from classes.Twitter import Twitter
from classes.YouTube import YouTube
from classes.CardNews import CardNews
from llm_provider import select_provider_model
from post_bridge_integration import maybe_crosspost_youtube_short

def main():
    """Main function to post content to Twitter or upload videos to YouTube.

    This function determines its operation based on command-line arguments:
    - If the purpose is "twitter", it initializes a Twitter account and posts a message.
    - If the purpose is "youtube", it initializes a YouTube account, generates a video with TTS, and uploads it.

    Command-line arguments:
        sys.argv[1]: A string indicating the purpose, either "twitter" or "youtube".
        sys.argv[2]: A string representing the account UUID.

    The function also handles verbose output based on user settings and reports success or errors as appropriate.

    Args:
        None. The function uses command-line arguments accessed via sys.argv.

    Returns:
        None. The function performs operations based on the purpose and account UUID and does not return any value."""
    purpose = str(sys.argv[1])
    account_id = str(sys.argv[2])
    model = str(sys.argv[3]) if len(sys.argv) > 3 else None

    ensure_config_file()

    if model:
        select_provider_model(get_llm_provider(), model)
    else:
        error("No model specified. Pass model name as third argument.")
        sys.exit(1)

    verbose = get_verbose()

    if purpose == "twitter":
        accounts = get_accounts("twitter")

        if not account_id:
            error("Account UUID cannot be empty.")

        for acc in accounts:
            if acc["id"] == account_id:
                if verbose:
                    info("Initializing Twitter...")
                twitter = Twitter(
                    acc["id"],
                    acc["nickname"],
                    acc["firefox_profile"],
                    acc["topic"]
                )
                twitter.post()
                if verbose:
                    success("Done posting.")
                break
    elif purpose == "youtube":
        tts = TTS()

        accounts = get_accounts("youtube")

        if not account_id:
            error("Account UUID cannot be empty.")

        for acc in accounts:
            if acc["id"] == account_id:
                if verbose:
                    info("Initializing YouTube...")
                youtube = YouTube(
                    acc["id"],
                    acc["nickname"],
                    acc["firefox_profile"],
                    acc["niche"],
                    acc["language"]
                )
                youtube.generate_video(tts)
                upload_success = youtube.upload_video()
                if upload_success:
                    if verbose:
                        success("Uploaded Short.")
                    maybe_crosspost_youtube_short(
                        video_path=youtube.video_path,
                        title=youtube.metadata.get("title", ""),
                        interactive=False,
                    )
                else:
                    warning("YouTube upload failed. Skipping Post Bridge cross-post.")
                break
    elif purpose == "cardnews":
        profiles = get_accounts("cardnews")
        review_required = get_cardnews_config()["review_required"]

        if not account_id:
            error("CardNews profile UUID cannot be empty.")

        for profile in profiles:
            if profile["id"] == account_id:
                if verbose:
                    info("Initializing CardNews...")
                studio = CardNews(profile)
                draft = studio.prepare_draft()

                if review_required:
                    warning(
                        "CardNews review_required is enabled. Draft generated and rendered, but not auto-published."
                    )
                    break

                studio.approve_draft(draft["id"])
                studio.publish_draft(draft["id"], interactive=False)
                if verbose:
                    success("Published CardNews draft.")
                break
    else:
        error("Invalid Purpose, exiting...")
        sys.exit(1)

if __name__ == "__main__":
    main()
