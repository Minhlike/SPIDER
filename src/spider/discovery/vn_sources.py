"""Bounded sources that are broadly used or relevant in Vietnam.

DIRECT_MAIGRET_SITES are present in the bundled Maigret 0.6.5 catalog and can
be checked directly. SEARCH_ONLY_SITES require a separate, explicit browser
search and must never be reported as directly checked by Maigret.
"""

DIRECT_MAIGRET_SITES = (
    "Facebook",
    "Instagram",
    "Threads",
    "TikTok",
    "YouTube",
    "LinkedIn",
    "GitHub",
    "Reddit",
    "Pinterest",
    "Telegram",
)

SEARCH_ONLY_SITES = ("X/Twitter", "Zalo", "Tinhte", "VOZ")
