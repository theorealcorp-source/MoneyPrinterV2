import os
import json
import threading

from typing import List
from config import ROOT_DIR

PROVIDER_CACHE_FILES = {
    "twitter": "twitter.json",
    "youtube": "youtube.json",
    "cardnews": "cardnews_accounts.json",
}
_CARDNEWS_JOB_LOCK = threading.Lock()

def get_cache_path() -> str:
    """
    Gets the path to the cache file.

    Returns:
        path (str): The path to the cache folder
    """
    return os.path.join(ROOT_DIR, '.mp')

def get_afm_cache_path() -> str:
    """
    Gets the path to the Affiliate Marketing cache file.

    Returns:
        path (str): The path to the AFM cache folder
    """
    return os.path.join(get_cache_path(), 'afm.json')

def get_twitter_cache_path() -> str:
    """
    Gets the path to the Twitter cache file.

    Returns:
        path (str): The path to the Twitter cache folder
    """
    return os.path.join(get_cache_path(), 'twitter.json')

def get_youtube_cache_path() -> str:
    """
    Gets the path to the YouTube cache file.

    Returns:
        path (str): The path to the YouTube cache folder
    """
    return os.path.join(get_cache_path(), 'youtube.json')

def get_provider_cache_path(provider: str) -> str:
    """
    Gets the cache path for a supported account provider.

    Args:
        provider (str): The provider name ("twitter" or "youtube")

    Returns:
        path (str): The provider-specific cache path

    Raises:
        ValueError: If the provider is unsupported
    """
    if provider in PROVIDER_CACHE_FILES:
        return os.path.join(get_cache_path(), PROVIDER_CACHE_FILES[provider])

    raise ValueError(
        f"Unsupported provider '{provider}'. Expected one of {sorted(PROVIDER_CACHE_FILES)}."
    )

def get_accounts(provider: str) -> List[dict]:
    """
    Gets the accounts from the cache.

    Args:
        provider (str): The provider to get the accounts for

    Returns:
        account (List[dict]): The accounts
    """
    cache_path = get_provider_cache_path(provider)

    if not os.path.exists(cache_path):
        # Create the cache file
        with open(cache_path, 'w') as file:
            json.dump({
                "accounts": []
            }, file, indent=4)

    with open(cache_path, 'r') as file:
        parsed = json.load(file)

        if parsed is None:
            return []
        
        if 'accounts' not in parsed:
            return []

        # Get accounts dictionary
        return parsed['accounts']

def add_account(provider: str, account: dict) -> None:
    """
    Adds an account to the cache.

    Args:
        provider (str): The provider to add the account to ("twitter" or "youtube")
        account (dict): The account to add

    Returns:
        None
    """
    cache_path = get_provider_cache_path(provider)

    # Get the current accounts
    accounts = get_accounts(provider)

    # Add the new account
    accounts.append(account)

    # Write the new accounts to the cache
    with open(cache_path, 'w') as file:
        json.dump({
            "accounts": accounts
        }, file, indent=4)


def update_account(provider: str, account_id: str, updates: dict) -> dict | None:
    """
    Updates an existing account payload by id.

    Args:
        provider (str): Provider bucket
        account_id (str): Account identifier
        updates (dict): Partial update payload

    Returns:
        account (dict | None): Updated account or None when not found
    """
    accounts = get_accounts(provider)
    updated_account = None

    for account in accounts:
        if account.get("id") == account_id:
            account.update(updates or {})
            updated_account = account
            break

    cache_path = get_provider_cache_path(provider)
    with open(cache_path, "w", encoding="utf-8") as file:
        json.dump({"accounts": accounts}, file, indent=4)

    return updated_account

def remove_account(provider: str, account_id: str) -> None:
    """
    Removes an account from the cache.

    Args:
        provider (str): The provider to remove the account from ("twitter" or "youtube")
        account_id (str): The ID of the account to remove

    Returns:
        None
    """
    # Get the current accounts
    accounts = get_accounts(provider)

    # Remove the account
    accounts = [account for account in accounts if account['id'] != account_id]

    # Write the new accounts to the cache
    cache_path = get_provider_cache_path(provider)

    with open(cache_path, 'w') as file:
        json.dump({
            "accounts": accounts
        }, file, indent=4)

def get_products() -> List[dict]:
    """
    Gets the products from the cache.

    Returns:
        products (List[dict]): The products
    """
    if not os.path.exists(get_afm_cache_path()):
        # Create the cache file
        with open(get_afm_cache_path(), 'w') as file:
            json.dump({
                "products": []
            }, file, indent=4)

    with open(get_afm_cache_path(), 'r') as file:
        parsed = json.load(file)

        # Get the products
        return parsed["products"]
    
def add_product(product: dict) -> None:
    """
    Adds a product to the cache.

    Args:
        product (dict): The product to add

    Returns:
        None
    """
    # Get the current products
    products = get_products()

    # Add the new product
    products.append(product)

    # Write the new products to the cache
    with open(get_afm_cache_path(), 'w') as file:
        json.dump({
            "products": products
        }, file, indent=4)
    
def get_results_cache_path() -> str:
    """
    Gets the path to the results cache file.

    Returns:
        path (str): The path to the results cache folder
    """
    return os.path.join(get_cache_path(), 'scraper_results.csv')


def get_cardnews_cache_path() -> str:
    """
    Gets the path to the CardNews draft cache file.

    Returns:
        path (str): CardNews cache path
    """
    return os.path.join(get_cache_path(), "cardnews.json")


def get_cardnews_jobs_cache_path() -> str:
    """
    Gets the path to the CardNews job cache file.

    Returns:
        path (str): CardNews jobs cache path
    """
    return os.path.join(get_cache_path(), "cardnews_jobs.json")


def _read_cardnews_jobs_unlocked() -> List[dict]:
    cache_path = get_cardnews_jobs_cache_path()
    if not os.path.exists(cache_path):
        with open(cache_path, "w", encoding="utf-8") as file:
            json.dump({"jobs": []}, file, indent=4)

    with open(cache_path, "r", encoding="utf-8") as file:
        parsed = json.load(file)

    jobs = parsed.get("jobs", [])
    return jobs if isinstance(jobs, list) else []


def get_cardnews_jobs() -> List[dict]:
    """
    Gets all CardNews background jobs.

    Returns:
        jobs (List[dict]): Stored jobs
    """
    with _CARDNEWS_JOB_LOCK:
        return _read_cardnews_jobs_unlocked()


def get_cardnews_job(job_id: str) -> dict | None:
    """
    Gets a CardNews job by id.

    Args:
        job_id (str): Job identifier

    Returns:
        job (dict | None): Matching job if found
    """
    for job in get_cardnews_jobs():
        if job.get("id") == job_id:
            return job

    return None


def add_cardnews_job(job: dict) -> None:
    """
    Adds a CardNews background job to cache.
    """
    with _CARDNEWS_JOB_LOCK:
        jobs = _read_cardnews_jobs_unlocked()
        jobs.append(job)
        jobs = sorted(jobs, key=lambda item: str(item.get("created_at", "")), reverse=True)[:20]

        with open(get_cardnews_jobs_cache_path(), "w", encoding="utf-8") as file:
            json.dump({"jobs": jobs}, file, indent=4)


def update_cardnews_job(job_id: str, updates: dict) -> dict | None:
    """
    Updates a CardNews job by id.
    """
    with _CARDNEWS_JOB_LOCK:
        jobs = _read_cardnews_jobs_unlocked()
        updated_job = None

        for job in jobs:
            if job.get("id") == job_id:
                job.update(updates or {})
                updated_job = job
                break

        with open(get_cardnews_jobs_cache_path(), "w", encoding="utf-8") as file:
            json.dump({"jobs": jobs}, file, indent=4)

    return updated_job


def get_cardnews_drafts() -> List[dict]:
    """
    Gets all CardNews drafts.

    Returns:
        drafts (List[dict]): Stored drafts
    """
    cache_path = get_cardnews_cache_path()

    if not os.path.exists(cache_path):
        with open(cache_path, "w", encoding="utf-8") as file:
            json.dump({"drafts": []}, file, indent=4)

    with open(cache_path, "r", encoding="utf-8") as file:
        parsed = json.load(file)

    drafts = parsed.get("drafts", [])
    return drafts if isinstance(drafts, list) else []


def get_cardnews_drafts_for_profile(profile_id: str) -> List[dict]:
    """
    Gets drafts belonging to a single CardNews profile.

    Args:
        profile_id (str): CardNews profile id

    Returns:
        drafts (List[dict]): Matching drafts newest first
    """
    drafts = [draft for draft in get_cardnews_drafts() if draft.get("profile_id") == profile_id]
    return sorted(drafts, key=lambda draft: str(draft.get("created_at", "")), reverse=True)


def get_cardnews_draft(draft_id: str) -> dict | None:
    """
    Gets a CardNews draft by id.

    Args:
        draft_id (str): Draft identifier

    Returns:
        draft (dict | None): Matching draft if found
    """
    for draft in get_cardnews_drafts():
        if draft.get("id") == draft_id:
            return draft

    return None


def add_cardnews_draft(draft: dict) -> None:
    """
    Adds a CardNews draft to cache.

    Args:
        draft (dict): Draft payload

    Returns:
        None
    """
    drafts = get_cardnews_drafts()
    drafts.append(draft)

    with open(get_cardnews_cache_path(), "w", encoding="utf-8") as file:
        json.dump({"drafts": drafts}, file, indent=4)


def update_cardnews_draft(draft_id: str, updates: dict) -> dict | None:
    """
    Updates a CardNews draft by id.

    Args:
        draft_id (str): Draft identifier
        updates (dict): Partial draft update

    Returns:
        draft (dict | None): Updated draft if found
    """
    drafts = get_cardnews_drafts()
    updated_draft = None

    for draft in drafts:
        if draft.get("id") == draft_id:
            draft.update(updates or {})
            updated_draft = draft
            break

    with open(get_cardnews_cache_path(), "w", encoding="utf-8") as file:
        json.dump({"drafts": drafts}, file, indent=4)

    return updated_draft
