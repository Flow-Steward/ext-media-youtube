"""One label for each input name, and one description for inputs that mean the same in
every step.

A step's form shows the label and the description. An input with the same name has the
same label in every step (``LABELS``, otherwise the name in words); an input that means
the same in every step also has the same description (``SAME``). An input whose meaning
depends on the method (``part``, ``id``, ``mine``) keeps the description the source gives
for that method; where the source gives none, ``FALLBACK`` says it.
"""

from __future__ import annotations

_WORDS = {"id": "ID", "ids": "IDs", "url": "URL", "html": "HTML"}

LABELS: dict[str, str] = {
    "q": "Search query",
    "hl": "Language",
    "tfmt": "Caption format",
    "tlang": "Translate to",
    "part": "Parts",
    "parts": "Parts",
    "id": "IDs",
    "mine": "Mine",
    "page_token": "Page token",
    "max_results": "Results per page",
    "max_items": "Most records",
    "all_pages": "All pages",
    "skip": "Skip",
    "body": "Request body",
    "file": "File",
    "content_type": "File type",
    "privacy_status": "Privacy",
    "on_behalf_of": "On behalf of page",
    "on_behalf_of_content_owner": "On behalf of content owner",
    "on_behalf_of_content_owner_channel": "Content owner's channel",
    "region_code": "Region",
    "relevance_language": "Relevance language",
    "published_after": "Published after",
    "published_before": "Published before",
    "parent_id": "Parent comment ID",
    "search_terms": "Search terms",
    "text_format": "Text format",
    "notify_subscribers": "Notify subscribers",
    "category_id": "Category ID",
    "output": "Output",
}

SAME: dict[str, str] = {
    "page_token": (
        "The page to start from: next_page_token of an earlier run that stopped early, or a "
        "nextPageToken YouTube returned."
    ),
    "skip": (
        "With page_token: how many records of that page an earlier run already returned "
        "(its next_skip)."
    ),
    "on_behalf_of_content_owner": (
        "For YouTube content partners only: the content owner the request is made for. The "
        "connection must be authorized by a CMS account linked to that content owner."
    ),
    "on_behalf_of_content_owner_channel": (
        "For YouTube content partners only, with on_behalf_of_content_owner: the channel the "
        "content owner acts for."
    ),
    "on_behalf_of": "The ID of the page of the channel the request is made for.",
    "hl": "The language of localized texts in the answer, such as en or de.",
    "region_code": (
        "A country, as an ISO 3166-1 alpha-2 code such as US: the results are those for "
        "viewers in this country."
    ),
    "published_after": "Only resources published at or after this date and time (RFC 3339).",
    "published_before": "Only resources published before this date and time (RFC 3339).",
    "notify_subscribers": (
        "Whether YouTube notifies the channel's subscribers (YouTube's default: true)."
    ),
    "text_format": "html (YouTube's default) or plainText.",
}

FALLBACK: dict[str, str] = {
    "channel_id": "The channel's ID.",
    "id": "The ID, or IDs separated by commas, the step works on.",
    "mine": "True: the connected channel's own resources.",
    "order": "The order of the results.",
    "rating": "like, dislike or none.",
    "max_height": "The largest height of the embedded player, in pixels.",
    "my_recent_subscribers": "True: the connected channel's most recent subscribers.",
    "video_paid_product_placement": (
        "Only videos with (true) or without (false) paid product placement."
    ),
}


def label_of(name: str) -> str:
    """The label of an input: LABELS, or its name in words."""
    if name in LABELS:
        return LABELS[name]
    words = [_WORDS.get(w, w) for w in name.split("_")]
    text = " ".join(words)
    return text[:1].upper() + text[1:]


def text_of(name: str, description: str | None) -> tuple[str, str]:
    """(label, description) of one input."""
    label = label_of(name)
    if name in SAME:
        return label, SAME[name]
    given = (description or "").strip()
    raw = name.replace("_", "")
    if not given or given.lower().replace(" ", "") in {raw, name.lower()}:
        given = FALLBACK.get(name, "")
    if not given:
        raise ValueError(f"No description for input {name}")
    return label, given
