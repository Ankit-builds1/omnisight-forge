from forge.elements import element_number, element_paths

HTML = (
    "<html><head><title>t</title></head><body>"
    '<div n="1"><p n="2">a</p><img n="3"><p n="4">b</p></div>'
    "<div></div>"
    '<div n="5"><span n="6">c</span><br/><span n="7">d</span></div>'
    "</body></html>"
)


def test_paths_follow_nth_of_type_from_body():
    assert element_paths(HTML) == {
        1: "body > div:nth-of-type(1)",
        2: "body > div:nth-of-type(1) > p:nth-of-type(1)",
        3: "body > div:nth-of-type(1) > img:nth-of-type(1)",
        4: "body > div:nth-of-type(1) > p:nth-of-type(2)",
        5: "body > div:nth-of-type(3)",
        6: "body > div:nth-of-type(3) > span:nth-of-type(1)",
        7: "body > div:nth-of-type(3) > span:nth-of-type(2)",
    }


def test_element_number_finds_the_target():
    assert element_number(HTML, "body > div:nth-of-type(3) > span:nth-of-type(2)") == 7
    assert element_number(HTML, "body > div:nth-of-type(2)") is None