import crawler


def test_extract_links_basic():
    html = '''
        <a href="/a">A</a>
        <a href="http://example.com/b">B</a>
    '''

    c = crawler.Crawler()
    links = c.extract_links(html, "http://example.com")

    assert "http://example.com/a" in links
    assert "http://example.com/b" in links

def test_queue_basic():
    c = crawler.Crawler()

    url = c.next_url()
    assert url is not None

def test_queue_deduplication():
    c = crawler.Crawler()

    c.enqueue_links([
        "http://example.com/a",
        "http://example.com/a",
    ])

    assert list(c.queue).count("http://example.com/a") == 1

def test_enqueue_respects_seen():
    c = crawler.Crawler()

    c.enqueue_links(["http://example.com/a"])
    c.enqueue_links(["http://example.com/a"])

    assert len([u for u in c.queue if u.endswith("/a")]) == 1