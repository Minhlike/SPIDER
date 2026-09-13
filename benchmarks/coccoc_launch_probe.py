"""Visible, navigation-free Cốc Cốc compatibility probe with redacted output."""
import asyncio
import argparse
import json
import tempfile

from playwright.async_api import async_playwright

from spider.providers.browser.coccoc import (browser_start_reason, coccoc_installation,
                                             coccoc_profile)


async def run(use_real_profile=False):
    executable, profile = coccoc_installation()
    if not executable:
        return {"launch": "FAIL", "reason": "MISSING_RUNTIME"}
    async with async_playwright() as playwright:
        try:
            with tempfile.TemporaryDirectory(prefix="spider-coccoc-probe-") as temporary:
                directory = str(profile) if use_real_profile else temporary
                context = await playwright.chromium.launch_persistent_context(
                    directory, executable_path=str(executable), headless=False,
                    accept_downloads=False, service_workers="block",
                    args=[f"--profile-directory={coccoc_profile(profile)}"]
                    if use_real_profile else [])
                version = context.browser.version if context.browser else "UNKNOWN"
                await context.close()
                return {"launch": "PASS", "browser_version": version}
        except Exception as exc:
            message = str(exc).casefold()
            return {"launch": "FAIL", "reason": browser_start_reason(exc),
                    "exception_class": exc.__class__.__name__,
                    "diagnostic": {
                        "profile_lock": any(word in message for word in (
                            "singleton", "already in use", "profile in use")),
                        "default_profile_rejected": any(word in message for word in (
                            "default user data", "non-default data directory")),
                        "devtools_endpoint_missing": "devtoolsactiveport" in message,
                        "early_exit": any(word in message for word in (
                            "browser has been closed", "process did exit")),
                    }}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-profile", action="store_true")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.real_profile))))
