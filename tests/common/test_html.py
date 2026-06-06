from atlas.commons.html import bold, link, strip_html


def test_bold_escapes_text_content():
    rendered = bold('<img src=x onerror="alert(1)">')

    assert rendered == (
        '<span style="font-weight: bold">'
        '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;'
        '</span>'
    )
    assert '<img' not in rendered
    assert 'onerror="alert(1)"' not in rendered


def test_link_escapes_href_attribute_and_visible_text():
    url = 'https://example.invalid/?q=" onclick="alert(1)&x=<tag>'
    rendered = link(url)

    assert rendered == (
        '<a href="https://example.invalid/?q=&quot; onclick=&quot;alert(1)&amp;x=&lt;tag&gt;">'
        'https://example.invalid/?q=&quot; onclick=&quot;alert(1)&amp;x=&lt;tag&gt;'
        '</a>'
    )
    assert 'onclick="alert(1)' not in rendered
    assert '<tag>' not in rendered


def test_strip_html_keeps_existing_plain_text_behavior():
    assert strip_html('<b>ok</b>') == 'ok'
