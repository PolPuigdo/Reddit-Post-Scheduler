from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import random

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


@dataclass
class FlairOption:
    id: str
    text: str


@dataclass
class ComposerCapabilities:
    target_type: str
    subreddit: str | None
    image_required: bool
    max_images: int | None
    has_flairs: bool
    has_tags: bool
    flair_required: bool
    flairs: list[FlairOption]
    nsfw_available: bool
    nsfw_forced_on: bool
    spoiler_available: bool

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["flairs"] = [asdict(flair) for flair in self.flairs]
        return payload


class RedditComposerCapabilitiesService:
    def __init__(
        self,
        auth_file: str,
        headless: bool = False,
        debug_artifacts_dir: str = "logs/debug",
    ):
        self.auth_file = Path(auth_file)
        self.headless = headless
        self.debug_artifacts_dir = Path(debug_artifacts_dir)

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        return " ".join((value or "").split()).strip().lower()

    @classmethod
    def detect_max_images(cls, input_info_text: str | None) -> int | None:
        normalized = cls._normalize_text(input_info_text)
        if "drag and drop or upload media" in normalized:
            return 1
        if "drag and drop images or" in normalized:
            return None
        return None

    @classmethod
    def detect_flair_tag_state(
        cls,
        button_text: str | None,
        button_disabled: bool,
    ) -> tuple[bool, bool, bool]:
        if button_disabled:
            return False, False, False

        normalized = cls._normalize_text(button_text)
        if "add flair and tags" in normalized:
            flair_required = "*" in (button_text or "")
            return True, True, flair_required

        if "add tags" in normalized:
            return False, True, False

        return False, False, False

    @staticmethod
    def _is_switch_checked(switch_locator) -> bool:
        checked_attr = switch_locator.get_attribute("checked")
        aria_checked = (switch_locator.get_attribute("aria-checked") or "").lower()
        data_checked = (switch_locator.get_attribute("data-checked") or "").lower()
        return (
            checked_attr is not None
            or aria_checked == "true"
            or data_checked == "true"
        )

    @staticmethod
    def _is_switch_disabled(switch_locator) -> bool:
        disabled_attr = switch_locator.get_attribute("disabled")
        aria_disabled = (switch_locator.get_attribute("aria-disabled") or "").lower()
        return disabled_attr is not None or aria_disabled == "true"

    @staticmethod
    def _extract_visible_text(locator) -> str:
        text = locator.inner_text(timeout=2500)
        return " ".join(text.split())

    def _save_debug_artifacts(self, page, prefix: str) -> None:
        self.debug_artifacts_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        screenshot_path = self.debug_artifacts_dir / f"{prefix}_{timestamp}.png"
        html_path = self.debug_artifacts_dir / f"{prefix}_{timestamp}.html"

        try:
            page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception:
            pass

        try:
            html_path.write_text(page.content(), encoding="utf-8")
        except Exception:
            pass

    def _handle_protection_page(self, page, max_retries: int = 3) -> None:
        """
        Detect simple Reddit / Cloudflare protection pages and try to bypass them
        by refreshing the page a few times.
        """
        for attempt in range(1, max_retries + 1):
            content = page.content()

            if (
                "Prove your humanity" in content
                or "You've been blocked by network security" in content
                or "blocked by network security" in content
            ):
                print(f"Protection page detected (attempt {attempt}/{max_retries}). Refreshing page...")
                page.reload(wait_until="domcontentloaded")
                page.wait_for_timeout(3000 + random.randint(500, 1500))
            else:
                return

        self._save_debug_artifacts(page, "protection_page")
        raise RuntimeError("Protection page still present after refresh retries.")

    def _resolve_submit_url(self, target_type: str, subreddit: str | None) -> str:
        if target_type == "profile":
            return "https://www.reddit.com/submit"
        if target_type == "subreddit" and subreddit:
            return f"https://www.reddit.com/r/{subreddit}/submit"
        raise RuntimeError("Invalid target configuration for capabilities extraction.")

    def inspect(self, target_type: str, subreddit: str | None = None) -> ComposerCapabilities:
        clean_target = (target_type or "").strip().lower()
        clean_subreddit = (subreddit or "").strip()

        if clean_target not in {"subreddit", "profile"}:
            raise RuntimeError("Unsupported target type.")

        if clean_target == "subreddit":
            if not clean_subreddit:
                raise RuntimeError("Subreddit is required for subreddit target.")
            if " " in clean_subreddit:
                raise RuntimeError("Subreddit cannot contain spaces.")
        else:
            clean_subreddit = ""

        if not self.auth_file.exists():
            raise RuntimeError("Playwright authentication file not found.")

        submit_url = self._resolve_submit_url(clean_target, clean_subreddit or None)

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                channel="chrome",
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--window-size=1366,900",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            
            context = browser.new_context(
                storage_state=str(self.auth_file),
                locale="en-US",
                timezone_id="Europe/Madrid",
                device_scale_factor=1.0,
                viewport={"width": 1366, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
            )

            # “oculta” el webdriver:
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            page = context.new_page()

            try:
                page.goto(submit_url, wait_until="domcontentloaded")
                page.wait_for_timeout(2500 + random.randint(400, 1000))
                self._handle_protection_page(page)

                images_tab = page.get_by_role("tab", name="Images").first
                if images_tab.is_visible():
                    images_tab.click()
                    page.wait_for_timeout(1200)

                image_required = page.locator(
                    "button[data-select-value='TEXT'][disabled]"
                ).first.is_visible()

                input_info_locator = page.locator("#inputInfo").first
                input_info_text = None
                if input_info_locator.is_visible():
                    input_info_text = self._extract_visible_text(input_info_locator)
                max_images = self.detect_max_images(input_info_text)

                has_flairs = False
                has_tags = False
                flair_required = False
                flairs: list[FlairOption] = []
                nsfw_available = False
                nsfw_forced_on = False
                spoiler_available = False

                if clean_target == "subreddit":
                    flair_tags_button = page.locator("#reddit-post-flair-button").first

                    if flair_tags_button.is_visible():
                        flair_button_text = self._extract_visible_text(flair_tags_button)
                        flair_button_disabled = flair_tags_button.is_disabled()
                        has_flairs, has_tags, flair_required = self.detect_flair_tag_state(
                            flair_button_text,
                            flair_button_disabled,
                        )

                        if has_flairs or has_tags:
                            flair_tags_button.click()
                            page.wait_for_timeout(700)

                            nsfw_switch = page.locator("faceplate-switch-input[name='isNsfw']").first
                            if nsfw_switch.count() > 0 and nsfw_switch.is_visible():
                                nsfw_available = True
                                nsfw_checked = self._is_switch_checked(nsfw_switch)
                                nsfw_disabled = self._is_switch_disabled(nsfw_switch)
                                nsfw_forced_on = nsfw_checked and nsfw_disabled

                            spoiler_switch = page.locator("faceplate-switch-input[name='isSpoiler']").first
                            if spoiler_switch.count() > 0 and spoiler_switch.is_visible():
                                spoiler_available = not self._is_switch_disabled(spoiler_switch)

                            if has_flairs:
                                view_all_button = page.locator("#view-all-flairs-button").first
                                if view_all_button.count() > 0 and view_all_button.is_visible():
                                    view_all_button.click()
                                    page.wait_for_timeout(700)

                                flair_radios = page.locator("faceplate-radio-input[name='flairId']")
                                flair_count = flair_radios.count()
                                seen: set[str] = set()
                                for index in range(flair_count):
                                    radio = flair_radios.nth(index)
                                    value = (radio.get_attribute("value") or "").strip()
                                    label_text = self._extract_visible_text(radio)
                                    if not label_text:
                                        if value:
                                            label_text = value
                                        else:
                                            label_text = "No flair"

                                    key = f"{value}|{label_text}"
                                    if key in seen:
                                        continue
                                    seen.add(key)
                                    flairs.append(FlairOption(id=value, text=label_text))

                            page.keyboard.press("Escape")
                            page.wait_for_timeout(300)

                return ComposerCapabilities(
                    target_type=clean_target,
                    subreddit=clean_subreddit or None,
                    image_required=image_required,
                    max_images=max_images,
                    has_flairs=has_flairs,
                    has_tags=has_tags,
                    flair_required=flair_required,
                    flairs=flairs,
                    nsfw_available=nsfw_available,
                    nsfw_forced_on=nsfw_forced_on,
                    spoiler_available=spoiler_available,
                )

            except PlaywrightTimeoutError as ex:
                self._save_debug_artifacts(page, "capabilities_timeout")
                raise RuntimeError("Timeout while extracting Reddit composer capabilities.") from ex
            except Exception:
                self._save_debug_artifacts(page, "capabilities_error")
                raise
            finally:
                browser.close()
