import pytest

from forge.prompt import MAX_DOM_CHARS, TRUNCATION_MARKER, build_prompt, shorten_dom


def test_heavy_tags_are_emptied_but_kept():
    html = (
        "<head><style>p{color:red}</style></head>"
        "<svg><path d='x'/></svg><script>a()</script>"
    )
    assert shorten_dom(html) == "<head><style></style></head><svg></svg><script></script>"


def test_sibling_tag_counts_are_preserved():
    html = "<body><script>a</script><script>b</script><svg>1</svg><svg>2</svg></body>"
    out = shorten_dom(html)
    assert out.count("<script>") == 2
    assert out.count("<svg>") == 2


def test_inline_style_is_kept_and_noise_attributes_are_dropped():
    html = (
        '<section class="py-5" role="main" aria-label="x" data-bs-theme="dark" '
        'style="width: 678px;" id="a">Hi</section>'
    )
    assert shorten_dom(html) == '<section style="width: 678px;" id="a">Hi</section>'


def test_comments_removed_and_whitespace_collapsed():
    assert shorten_dom("<p>\n  a   <!-- note -->  b\n</p>") == "<p> a b </p>"


def test_build_prompt_has_size_format_and_html():
    prompt = build_prompt("mobile", "<body><p>Hi</p></body>")
    assert "mobile (375x812 pixels)" in prompt
    assert '"selector"' in prompt
    assert '"property"' in prompt
    assert '"value"' in prompt
    assert prompt.endswith("<body><p>Hi</p></body>")


def test_build_prompt_truncates_very_long_html():
    prompt = build_prompt("desktop", "<p>" + "x" * (MAX_DOM_CHARS * 2) + "</p>")
    assert prompt.endswith(TRUNCATION_MARKER)
    assert len(prompt) < MAX_DOM_CHARS + 1000


def test_build_prompt_rejects_unknown_viewport():
    with pytest.raises(KeyError):
        build_prompt("watch", "<p></p>")

def test_link_and_media_attributes_are_dropped():
    html = (
        '<a href="/wiki/Main_Page" title="Visit the main page" accesskey="z" rel="x" '
        'id="n1" style="color: red;">Main</a>'
        '<img src="/a.svg" srcset="/a2.svg 2x" alt="Logo" lang="en" dir="ltr" tabindex="0">'
    )
    assert shorten_dom(html) == '<a id="n1" style="color: red;">Main</a><img>'