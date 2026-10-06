import pytest

from forge.prompt import MAX_DOM_CHARS, TRUNCATION_MARKER, build_prompt, shorten_dom


def test_style_script_and_head_metadata_are_dropped():
    html = (
        '<head><meta charset="utf-8"><link rel="x"><style>p{color:red}</style></head>'
        '<body><script>a()</script><p n="1">Hi</p></body>'
    )
    assert shorten_dom(html) == '<body><p n="1">Hi</p></body>'


def test_svg_drawings_are_dropped():
    html = '<div n="3"><svg n="4"><path d="x"/></svg>Hi</div>'
    assert shorten_dom(html) == '<div n="3">Hi</div>'


def test_empty_unnumbered_elements_are_dropped_but_numbered_ones_kept():
    html = '<div><span></span><ul> </ul></div><div n="2"></div><nav><a n="3">Go</a></nav>'
    assert shorten_dom(html) == '<div n="2"></div><nav><a n="3">Go</a></nav>'


def test_every_element_number_survives():
    html = (
        '<body><div id="toc-a-very-long-id" n="1"><span></span><span n="2">A</span></div>'
        '<ul n="3"><li n="4"><a href="/x" n="5">x</a></li></ul><img n="6" src="a.png"></body>'
    )
    out = shorten_dom(html)
    for number in range(1, 7):
        assert f'n="{number}"' in out


def test_inline_style_is_kept_and_noise_attributes_are_dropped():
    html = (
        '<section class="py-5" role="main" aria-label="x" data-bs-theme="dark" '
        'style="width: 678px;" id="a" n="1">Hi</section>'
    )
    assert shorten_dom(html) == '<section style="width: 678px;" n="1">Hi</section>'


def test_long_text_is_cut_to_its_first_words():
    words = " ".join(["word"] * 40)
    out = shorten_dom(f'<p n="1">{words}</p>')
    assert out.startswith('<p n="1">word word')
    assert out.endswith("…</p>")
    assert len(out) < 90


def test_comments_removed_and_whitespace_collapsed():
    assert shorten_dom('<p n="1">\n  a   <!-- note -->  b\n</p>  <p n="2">c</p>') == (
        '<p n="1"> a b </p><p n="2">c</p>'
    )


def test_build_prompt_has_size_format_and_html():
    prompt = build_prompt("mobile", "<body><p>Hi</p></body>")
    assert "mobile (375x812 pixels)" in prompt
    assert '"element"' in prompt
    assert '"property"' in prompt
    assert '"value"' in prompt
    assert prompt.endswith("<body><p>Hi</p></body>")


def test_build_prompt_truncates_very_long_html():
    prompt = build_prompt("desktop", '<p n="1">x</p>' * MAX_DOM_CHARS)
    assert prompt.endswith(TRUNCATION_MARKER)
    assert len(prompt) < MAX_DOM_CHARS + 1000


def test_build_prompt_rejects_unknown_viewport():
    with pytest.raises(KeyError):
        build_prompt("watch", "<p></p>")

def test_link_and_media_attributes_are_dropped():
    html = (
        '<a href="/wiki/Main_Page" title="Visit the main page" accesskey="z" rel="x" '
        'id="n1" style="color: red;" n="1">Main</a>'
        '<img src="/a.svg" srcset="/a2.svg 2x" alt="Logo" lang="en" dir="ltr" tabindex="0" n="2">'
    )
    assert shorten_dom(html) == '<a style="color: red;" n="1">Main</a><img n="2">'