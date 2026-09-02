from __future__ import annotations

from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlparse, parse_qs

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
    expect,
)

import config


BROWSER_PROFILE = config.BROWSER_PROFILE
STUDIO_URL = config.STUDIO_URL
LOGS = config.LOGS
UPLOAD_VISIBILITY = config.UPLOAD_VISIBILITY
KEEP_BROWSER_OPEN_AFTER_UPLOAD = (
    config.KEEP_BROWSER_OPEN_AFTER_UPLOAD
)

YOUTUBE_MIN_PROCESSING_WAIT = getattr(
    config,
    "YOUTUBE_MIN_PROCESSING_WAIT",
    90,
)
YOUTUBE_MAX_PROCESSING_WAIT = getattr(
    config,
    "YOUTUBE_MAX_PROCESSING_WAIT",
    600,
)
YOUTUBE_PROCESSING_POLL = getattr(
    config,
    "YOUTUBE_PROCESSING_POLL",
    2,
)
YOUTUBE_CLEAN_POLLS_REQUIRED = getattr(
    config,
    "YOUTUBE_CLEAN_POLLS_REQUIRED",
    3,
)
YOUTUBE_FINAL_GRACE_WAIT = getattr(
    config,
    "YOUTUBE_FINAL_GRACE_WAIT",
    15,
)

YOUTUBE_PUBLISH_VERIFY_TIMEOUT = getattr(
    config,
    "YOUTUBE_PUBLISH_VERIFY_TIMEOUT",
    120,
)

YOUTUBE_STUDIO_VERIFY_WAIT = getattr(
    config,
    "YOUTUBE_STUDIO_VERIFY_WAIT",
    8,
)


class YouTubeUploadError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        stage: str = "",
        studio_error_text: str = "",
        processing_wait_seconds: int | None = None,
        screenshot_path: str | None = None,
        html_path: str | None = None,
    ):
        super().__init__(message)

        self.stage = stage
        self.studio_error_text = studio_error_text
        self.processing_wait_seconds = (
            processing_wait_seconds
        )
        self.screenshot_path = screenshot_path
        self.html_path = html_path


def save_debug(
    page,
    name: str,
) -> tuple[str | None, str | None]:
    debug_dir = LOGS / "youtube"
    debug_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    stamp = time.strftime(
        "%Y%m%d_%H%M%S"
    )

    screenshot = (
        debug_dir
        / f"{stamp}_{name}.png"
    )

    html_file = (
        debug_dir
        / f"{stamp}_{name}.html"
    )

    screenshot_path = None
    html_path = None

    try:
        page.screenshot(
            path=str(screenshot),
            full_page=True,
        )
        screenshot_path = str(
            screenshot.resolve()
        )
    except Exception:
        pass

    try:
        html_file.write_text(
            page.content(),
            encoding="utf-8",
        )
        html_path = str(
            html_file.resolve()
        )
    except Exception:
        pass

    print("")
    print("DEBUG saved:")

    if screenshot_path:
        print(screenshot_path)

    if html_path:
        print(html_path)

    return screenshot_path, html_path


def _visible_text(
    locator,
) -> str:
    try:
        if (
            locator.count() > 0
            and locator.first.is_visible()
        ):
            return (
                locator.first.inner_text(
                    timeout=3000
                )
                or ""
            )
    except Exception:
        pass

    return ""


def _page_text(
    page,
) -> str:
    try:
        return (
            page.locator("body")
            .inner_text(timeout=5000)
            or ""
        )
    except Exception:
        return ""


def find_fatal_studio_error(
    page,
) -> str | None:
    """
    Шукаємо лише помилки, які схожі на реальну
    невдачу upload/publish.

    Copyright warning сам по собі тут не вважається
    publish failure.
    """

    candidates = []

    selectors = [
        '[role="alert"]',
        "ytcp-toast",
        "tp-yt-paper-toast",
        "ytcp-snackbar",
        "ytcp-uploads-dialog",
    ]

    for selector in selectors:
        try:
            locators = page.locator(selector)

            for index in range(
                min(locators.count(), 10)
            ):
                item = locators.nth(index)

                try:
                    if item.is_visible():
                        text = (
                            item.inner_text(
                                timeout=2000
                            )
                            or ""
                        ).strip()

                        if text:
                            candidates.append(text)

                except Exception:
                    pass

        except Exception:
            pass

    body = _page_text(page)

    if body:
        candidates.append(body)

    fatal_patterns = [
        r"\bsomething went wrong\b",
        r"\bupload failed\b",
        r"\bfailed to upload\b",
        r"\bcould(?:n't| not) publish\b",
        r"\bcould(?:n't| not) upload\b",
        r"\bunable to publish\b",
        r"\bunable to upload\b",
        r"\bprocessing abandoned\b",
        r"\bdaily upload limit\b",
        r"\btoo many uploads\b",
        r"\bpublishing failed\b",
        r"\berror publishing\b",
        r"\berror uploading\b",
    ]

    for text in candidates:
        lines = [
            re.sub(
                r"\s+",
                " ",
                line,
            ).strip()
            for line in text.splitlines()
        ]

        for line in lines:
            if not line:
                continue

            lower = line.lower()

            for pattern in fatal_patterns:
                if re.search(
                    pattern,
                    lower,
                    re.IGNORECASE,
                ):
                    return line[:1000]

    return None


def open_create_menu(page) -> None:
    selectors = [
        "#create-icon",
        "ytcp-button#create-icon",
        'button[aria-label*="Create" i]',
    ]

    for selector in selectors:
        try:
            locator = page.locator(
                selector
            ).first

            if locator.count() > 0:
                locator.wait_for(
                    state="visible",
                    timeout=5000,
                )
                locator.click()
                return

        except Exception:
            pass

    locator = page.get_by_role(
        "button",
        name=re.compile(
            r"^Create$",
            re.IGNORECASE,
        ),
    ).first

    locator.wait_for(
        state="visible",
        timeout=10000,
    )
    locator.click()


def click_upload_videos(page) -> None:
    page.wait_for_timeout(700)

    try:
        item = page.get_by_text(
            "Upload videos",
            exact=True,
        ).first

        item.wait_for(
            state="visible",
            timeout=10000,
        )
        item.click()
        return

    except Exception:
        pass

    item = page.locator(
        'tp-yt-paper-item:has-text("Upload videos")'
    ).first

    item.wait_for(
        state="visible",
        timeout=10000,
    )
    item.click()


def click_next(page) -> None:
    try:
        button = page.locator(
            "#next-button"
        ).first

        button.wait_for(
            state="visible",
            timeout=120000,
        )

        expect(
            button
        ).to_be_enabled(
            timeout=120000,
        )

        button.click()
        page.wait_for_timeout(900)
        return

    except Exception:
        pass

    button = page.get_by_role(
        "button",
        name="Next",
        exact=True,
    ).first

    button.wait_for(
        state="visible",
        timeout=120000,
    )

    expect(
        button
    ).to_be_enabled(
        timeout=120000,
    )

    button.click()
    page.wait_for_timeout(900)


def select_not_for_kids(page) -> None:
    radio = page.locator(
        '[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]'
    ).first

    try:
        radio.wait_for(
            state="attached",
            timeout=10000,
        )
        radio.click()
        return

    except Exception:
        pass

    option = page.get_by_text(
        re.compile(
            r"No,\s*it's not made for kids",
            re.IGNORECASE,
        ),
    ).first

    option.wait_for(
        state="visible",
        timeout=10000,
    )
    option.click()


def select_visibility(
    page,
    visibility: str,
) -> None:
    visibility = (
        visibility.strip().lower()
    )

    mapping = {
        "public": "PUBLIC",
        "private": "PRIVATE",
        "unlisted": "UNLISTED",
    }

    if visibility not in mapping:
        raise ValueError(
            "UPLOAD_VISIBILITY must be "
            "public/private/unlisted."
        )

    internal_name = mapping[
        visibility
    ]

    selectors = [
        (
            'tp-yt-paper-radio-button'
            f'[name="{internal_name}"]'
        ),
        f'[name="{internal_name}"]',
    ]

    for selector in selectors:
        try:
            radio = page.locator(
                selector
            ).first

            if radio.count() > 0:
                radio.wait_for(
                    state="visible",
                    timeout=10000,
                )
                radio.click()
                page.wait_for_timeout(700)
                return

        except Exception:
            pass

    label = visibility.capitalize()

    candidates = page.get_by_text(
        label,
        exact=True,
    )

    for index in range(
        candidates.count()
    ):
        candidate = candidates.nth(index)

        try:
            if candidate.is_visible():
                candidate.click()
                page.wait_for_timeout(700)
                return

        except Exception:
            pass

    raise RuntimeError(
        f"Не вдалося вибрати visibility={visibility}."
    )


def _upload_dialog_text(
    page,
) -> str:
    try:
        dialog = page.locator(
            "ytcp-uploads-dialog"
        ).first

        if (
            dialog.count() > 0
            and dialog.is_visible()
        ):
            return (
                dialog.inner_text(
                    timeout=5000
                )
                or ""
            )

    except Exception:
        pass

    return _page_text(page)


def _active_processing_lines(
    text: str,
) -> list[str]:
    lines = [
        re.sub(
            r"\s+",
            " ",
            line,
        ).strip()
        for line in (
            text or ""
        ).splitlines()
    ]

    active = []

    finished_words = (
        "complete",
        "completed",
        "finished",
        "done",
        "no issues found",
        "checks passed",
    )

    active_patterns = (
        "uploading",
        "processing",
        "checking",
        "checks running",
        "checks are running",
        "running checks",
    )

    for line in lines:
        if not line:
            continue

        lower = line.lower()

        if any(
            word in lower
            for word in finished_words
        ):
            continue

        if any(
            pattern in lower
            for pattern in active_patterns
        ):
            active.append(line)
            continue

        if re.search(
            r"\b\d{1,3}\s*%",
            lower,
        ):
            if (
                "upload" in lower
                or "process" in lower
                or "check" in lower
            ):
                active.append(line)

    return active


def _wait_fixed_cooldown(
    page,
    seconds: int,
) -> None:
    if seconds <= 0:
        return

    print("")
    print(
        "YouTube safety cooldown:"
        f" {seconds} сек."
    )

    remaining = seconds

    while remaining > 0:
        chunk = min(
            10,
            remaining,
        )

        page.wait_for_timeout(
            chunk * 1000
        )

        remaining -= chunk

        fatal = find_fatal_studio_error(
            page
        )

        if fatal:
            raise YouTubeUploadError(
                (
                    "YouTube Studio показав "
                    f"помилку: {fatal}"
                ),
                stage="processing_wait",
                studio_error_text=fatal,
            )

        if remaining > 0:
            print(
                f"  ще {remaining} сек..."
            )


def wait_for_youtube_processing(
    page,
) -> int:
    started = time.monotonic()

    print("")
    print("=" * 58)
    print(
        "WAITING FOR YOUTUBE PROCESSING".center(58)
    )
    print("=" * 58)

    _wait_fixed_cooldown(
        page,
        YOUTUBE_MIN_PROCESSING_WAIT,
    )

    clean_polls = 0
    last_status_print = 0.0

    while True:
        elapsed = int(
            time.monotonic()
            - started
        )

        fatal = find_fatal_studio_error(
            page
        )

        if fatal:
            raise YouTubeUploadError(
                (
                    "YouTube Studio показав "
                    f"помилку: {fatal}"
                ),
                stage="processing_wait",
                studio_error_text=fatal,
                processing_wait_seconds=elapsed,
            )

        if (
            elapsed
            >= YOUTUBE_MAX_PROCESSING_WAIT
        ):
            raise YouTubeUploadError(
                (
                    "YouTube все ще показує "
                    "upload/processing/checks після "
                    f"{YOUTUBE_MAX_PROCESSING_WAIT} сек. "
                    "Publish НЕ натискаю."
                ),
                stage="processing_timeout",
                processing_wait_seconds=elapsed,
            )

        text = _upload_dialog_text(
            page
        )

        active_lines = (
            _active_processing_lines(
                text
            )
        )

        if active_lines:
            clean_polls = 0

            now = time.monotonic()

            if (
                now
                - last_status_print
                >= 10
            ):
                print("")
                print(
                    "YouTube ще обробляє "
                    f"відео ({elapsed} сек):"
                )

                for line in (
                    active_lines[:4]
                ):
                    print(
                        "  ",
                        line,
                    )

                last_status_print = now

        else:
            clean_polls += 1

            print(
                f"Clean processing check: "
                f"{clean_polls}/"
                f"{YOUTUBE_CLEAN_POLLS_REQUIRED}"
            )

            if (
                clean_polls
                >= YOUTUBE_CLEAN_POLLS_REQUIRED
            ):
                break

        page.wait_for_timeout(
            YOUTUBE_PROCESSING_POLL
            * 1000
        )

    if YOUTUBE_FINAL_GRACE_WAIT > 0:
        print(
            "Додатковий safety wait:"
            f" {YOUTUBE_FINAL_GRACE_WAIT} сек."
        )

        page.wait_for_timeout(
            YOUTUBE_FINAL_GRACE_WAIT
            * 1000
        )

    total = int(
        time.monotonic()
        - started
    )

    fatal = find_fatal_studio_error(
        page
    )

    if fatal:
        raise YouTubeUploadError(
            (
                "YouTube Studio показав "
                f"помилку перед Publish: {fatal}"
            ),
            stage="before_publish",
            studio_error_text=fatal,
            processing_wait_seconds=total,
        )

    print("")
    print(
        "YouTube processing gate: READY"
    )
    print(
        f"Фактичне очікування: {total} сек."
    )

    return total


def try_get_video_url(
    page,
) -> str | None:
    selectors = [
        'a[href*="youtube.com/shorts/"]',
        'a[href*="youtube.com/watch?v="]',
        'a[href*="youtu.be/"]',
    ]

    for selector in selectors:
        try:
            links = page.locator(
                selector
            )

            for index in range(
                links.count()
            ):
                href = (
                    links.nth(index)
                    .get_attribute("href")
                )

                if not href:
                    continue

                href = urljoin(
                    "https://www.youtube.com",
                    href,
                )

                if (
                    "/shorts/" in href
                    or "watch?v=" in href
                    or "youtu.be/" in href
                ):
                    return href

        except Exception:
            pass

    return None


def extract_video_id(
    url: str | None,
) -> str | None:
    if not url:
        return None

    if "/shorts/" in url:
        return (
            url.split(
                "/shorts/",
                1,
            )[1]
            .split("?", 1)[0]
            .split("/", 1)[0]
        )

    if "watch?v=" in url:
        parsed = urlparse(url)

        values = parse_qs(
            parsed.query
        ).get("v")

        if values:
            return values[0]

    if "youtu.be/" in url:
        return (
            url.split(
                "youtu.be/",
                1,
            )[1]
            .split("?", 1)[0]
            .split("/", 1)[0]
        )

    return None


def publish_or_save(
    page,
) -> None:
    button = page.locator(
        "#done-button"
    ).first

    try:
        button.wait_for(
            state="visible",
            timeout=120000,
        )

        expect(
            button
        ).to_be_enabled(
            timeout=120000,
        )

    except Exception:
        button = page.get_by_role(
            "button",
            name=re.compile(
                r"^(Publish|Save)$",
                re.IGNORECASE,
            ),
        ).first

        button.wait_for(
            state="visible",
            timeout=120000,
        )

        expect(
            button
        ).to_be_enabled(
            timeout=120000,
        )

    fatal = find_fatal_studio_error(
        page
    )

    if fatal:
        raise YouTubeUploadError(
            (
                "Перед натисканням Publish "
                f"Studio показав помилку: {fatal}"
            ),
            stage="before_publish",
            studio_error_text=fatal,
        )

    print("")
    print("Натискаю Publish/Save...")

    button.click()
    page.wait_for_timeout(1000)


def wait_for_publish_confirmation(
    page,
    video_url: str | None,
) -> tuple[str, str]:
    """
    ВАЖЛИВО:
    закриття upload dialog БІЛЬШЕ НЕ вважається
    автоматичним доказом Publish.

    Потрібні:
    1) відсутність fatal Studio error;
    2) YouTube URL + video ID;
    3) explicit success signal АБО перехід до незалежної
       перевірки video edit page.
    """

    started = time.monotonic()
    explicit_success = False

    success_patterns = re.compile(
        r"(video published|"
        r"video has been published|"
        r"published successfully|"
        r"video saved|"
        r"changes saved)",
        re.IGNORECASE,
    )

    while (
        time.monotonic() - started
        < YOUTUBE_PUBLISH_VERIFY_TIMEOUT
    ):
        fatal = find_fatal_studio_error(
            page
        )

        if fatal:
            raise YouTubeUploadError(
                (
                    "Publish failed in YouTube Studio: "
                    f"{fatal}"
                ),
                stage="publish_confirmation",
                studio_error_text=fatal,
            )

        text = _page_text(page)

        if success_patterns.search(
            text or ""
        ):
            explicit_success = True

        if not video_url:
            video_url = try_get_video_url(
                page
            )

        video_id = extract_video_id(
            video_url
        )

        dialog_visible = False

        try:
            dialog = page.locator(
                "ytcp-uploads-dialog"
            ).first

            dialog_visible = (
                dialog.count() > 0
                and dialog.is_visible()
            )
        except Exception:
            dialog_visible = False

        if (
            explicit_success
            and video_id
        ):
            return video_url, video_id

        if (
            not dialog_visible
            and video_id
        ):
            # Dialog closed, but unlike old bot we still do
            # not call it published yet. We will verify the
            # video independently in Studio edit page.
            return video_url, video_id

        page.wait_for_timeout(1000)

    raise YouTubeUploadError(
        (
            "Publish/Save був натиснутий, "
            "але за відведений час бот не отримав "
            "надійного підтвердження та video ID."
        ),
        stage="publish_confirmation_timeout",
    )


def verify_video_in_studio(
    page,
    video_id: str,
    visibility: str,
) -> None:
    """
    Друга незалежна перевірка:
    відкриваємо editor конкретного YouTube video ID
    і перевіряємо, що Studio бачить цей ролик та потрібний
    visibility.

    Це робить перевірку сильнішою, ніж просто:
    "dialog закрився -> success".
    """

    edit_url = (
        "https://studio.youtube.com/"
        f"video/{video_id}/edit?hl=en"
    )

    print("")
    print(
        "Перевіряю опубліковане відео "
        "окремо в YouTube Studio..."
    )

    page.goto(
        edit_url,
        wait_until="domcontentloaded",
        timeout=120000,
    )

    page.wait_for_timeout(
        YOUTUBE_STUDIO_VERIFY_WAIT
        * 1000
    )

    if "accounts.google.com" in page.url:
        raise YouTubeUploadError(
            "Studio verification redirected to Google login.",
            stage="studio_verify",
        )

    fatal = find_fatal_studio_error(
        page
    )

    if fatal:
        raise YouTubeUploadError(
            (
                "Studio verification page showed error: "
                f"{fatal}"
            ),
            stage="studio_verify",
            studio_error_text=fatal,
        )

    body_text = _page_text(
        page
    )

    body_lines = {
        re.sub(
            r"\s+",
            " ",
            line,
        ).strip().lower()
        for line in body_text.splitlines()
        if line.strip()
    }

    expected = visibility.lower()

    if expected == "public":
        expected_text = "public"
    elif expected == "private":
        expected_text = "private"
    else:
        expected_text = "unlisted"

    # A visible exact-match text is preferred.
    visibility_confirmed = False

    try:
        matches = page.get_by_text(
            expected_text.capitalize(),
            exact=True,
        )

        for index in range(
            matches.count()
        ):
            try:
                if matches.nth(index).is_visible():
                    visibility_confirmed = True
                    break
            except Exception:
                pass
    except Exception:
        pass

    if not visibility_confirmed:
        visibility_confirmed = (
            expected_text in body_lines
        )

    draft_visible = (
        "draft" in body_lines
    )

    if (
        expected == "public"
        and draft_visible
    ):
        raise YouTubeUploadError(
            (
                "Studio edit page shows Draft after "
                "Publish. Вважаю публікацію невдалою."
            ),
            stage="studio_verify",
            studio_error_text="Draft",
        )

    if not visibility_confirmed:
        raise YouTubeUploadError(
            (
                "Video ID існує, але Studio не підтвердив "
                f"visibility={visibility}. "
                "Вважаю Publish непідтвердженим."
            ),
            stage="studio_verify_visibility",
        )

    print(
        "STUDIO VERIFY: OK"
    )
    print(
        f"Video ID: {video_id}"
    )
    print(
        f"Visibility: {visibility}"
    )


def upload_video(
    video: Path,
    title: str,
    description: str,
    visibility: str | None = None,
) -> dict:
    visibility = (
        visibility
        or UPLOAD_VISIBILITY
    )

    print("")
    print("=" * 58)
    print(
        "YOUTUBE UPLOAD".center(58)
    )
    print("=" * 58)
    print("")
    print("VIDEO:")
    print(video)
    print("")
    print("VISIBILITY:")
    print(visibility)

    processing_wait_seconds = None

    with sync_playwright() as p:
        context = (
            p.chromium
            .launch_persistent_context(
                user_data_dir=str(
                    BROWSER_PROFILE
                ),
                channel="chrome",
                headless=False,
                no_viewport=True,
                chromium_sandbox=True,
                args=[
                    "--start-maximized",
                ],
            )
        )

        context.set_default_timeout(
            30000
        )

        page = (
            context.pages[0]
            if context.pages
            else context.new_page()
        )

        try:
            page.goto(
                STUDIO_URL,
                wait_until="domcontentloaded",
                timeout=120000,
            )

            page.wait_for_timeout(4000)

            if (
                "accounts.google.com"
                in page.url
            ):
                raise YouTubeUploadError(
                    (
                        "Google-сесія в BrowserProfile "
                        "не активна."
                    ),
                    stage="open_studio",
                )

            open_create_menu(page)
            click_upload_videos(page)

            file_input = page.locator(
                'input[type="file"]'
            ).first

            file_input.wait_for(
                state="attached",
                timeout=30000,
            )

            file_input.set_input_files(
                str(video)
            )

            title_box = page.locator(
                "#title-textarea #textbox"
            ).first

            title_box.wait_for(
                state="visible",
                timeout=120000,
            )

            description_box = (
                page.locator(
                    "#description-textarea #textbox"
                )
                .first
            )

            title_box.fill(title)
            description_box.fill(
                description
            )

            select_not_for_kids(page)

            video_url = try_get_video_url(
                page
            )

            click_next(page)
            click_next(page)
            click_next(page)

            select_visibility(
                page,
                visibility,
            )

            processing_wait_seconds = (
                wait_for_youtube_processing(
                    page
                )
            )

            publish_or_save(page)

            video_url, video_id = (
                wait_for_publish_confirmation(
                    page,
                    video_url,
                )
            )

            # Strong secondary confirmation.
            verify_video_in_studio(
                page,
                video_id,
                visibility,
            )

            print("")
            print(
                "YOUTUBE UPLOAD: VERIFIED"
            )
            print(video_url)

            if (
                KEEP_BROWSER_OPEN_AFTER_UPLOAD
            ):
                input(
                    "Перевір Studio і "
                    "натисни ENTER..."
                )

            return {
                "success": True,
                "video_url": video_url,
                "video_id": video_id,
                "visibility": visibility,
                "processing_wait_seconds":
                    processing_wait_seconds,
                "verification":
                    "studio_edit_page",
            }

        except PlaywrightTimeoutError as exc:
            screenshot, html = save_debug(
                page,
                "upload_timeout",
            )

            raise YouTubeUploadError(
                f"Playwright timeout: {exc}",
                stage="playwright_timeout",
                processing_wait_seconds=(
                    processing_wait_seconds
                ),
                screenshot_path=screenshot,
                html_path=html,
            ) from exc

        except YouTubeUploadError as exc:
            if (
                not exc.screenshot_path
                or not exc.html_path
            ):
                screenshot, html = save_debug(
                    page,
                    (
                        "publish_failed_"
                        + (
                            exc.stage
                            or "unknown"
                        )
                    ),
                )

                if not exc.screenshot_path:
                    exc.screenshot_path = screenshot

                if not exc.html_path:
                    exc.html_path = html

            if (
                exc.processing_wait_seconds
                is None
            ):
                exc.processing_wait_seconds = (
                    processing_wait_seconds
                )

            raise

        except Exception as exc:
            screenshot, html = save_debug(
                page,
                "upload_unexpected_error",
            )

            raise YouTubeUploadError(
                str(exc),
                stage="unexpected",
                processing_wait_seconds=(
                    processing_wait_seconds
                ),
                screenshot_path=screenshot,
                html_path=html,
            ) from exc

        finally:
            try:
                context.close()
            except Exception:
                pass
