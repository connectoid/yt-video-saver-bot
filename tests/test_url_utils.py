from bot.utils.url_utils import extract_video_url

CANONICAL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_watch_url():
    assert extract_video_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == CANONICAL


def test_watch_url_with_extra_params():
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s&list=PL123"
    assert extract_video_url(url) == CANONICAL


def test_shorts_url_inside_text():
    text = "смотри https://youtube.com/shorts/dQw4w9WgXcQ вот это да!"
    assert extract_video_url(text) == CANONICAL


def test_short_domain_with_query():
    assert extract_video_url("https://youtu.be/dQw4w9WgXcQ?si=abc123") == CANONICAL


def test_mobile_domain():
    assert extract_video_url("https://m.youtube.com/watch?v=dQw4w9WgXcQ") == CANONICAL


def test_no_link_returns_none():
    assert extract_video_url("привет, как дела?") is None


def test_non_youtube_link_returns_none():
    assert extract_video_url("https://vimeo.com/12345678") is None


from bot.utils.url_utils import VIDEO_ID_RE, extract_video_id


def test_extract_video_id_matches_extract_video_url():
    text = "смотри https://youtu.be/dQw4w9WgXcQ?si=abc123 вот это да!"
    assert extract_video_id(text) == "dQw4w9WgXcQ"


def test_extract_video_id_no_link_returns_none():
    assert extract_video_id("просто текст без ссылок") is None


def test_video_id_re_accepts_valid_id():
    assert VIDEO_ID_RE.match("dQw4w9WgXcQ")


def test_video_id_re_rejects_wrong_length():
    assert not VIDEO_ID_RE.match("short")
    assert not VIDEO_ID_RE.match("waytoolongvideoid123")


def test_video_id_re_rejects_spaces_and_symbols():
    assert not VIDEO_ID_RE.match("dQw4w9Wg XcQ")
    assert not VIDEO_ID_RE.match("dQw4w9Wg/cQ")
