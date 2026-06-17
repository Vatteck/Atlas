import unittest

from atlas.gems.arch import aur_comments as ac


# A realistic two-comment AUR package page fragment (pinned + regular), matching the AUR web markup.
SAMPLE = """
<html><body>
<div class="comments package-comments">
  <h3>Pinned Comments</h3>
  <h4 class="comment-header" id="comment-100">
    <a href="/account/maintainer" title="View account">maintainer</a> commented on
    <a href="#comment-100" class="date"><time datetime="2024-02-01T10:00:00Z">2024-02-01 10:00</time></a>
  </h4>
  <div id="comment-100-content" class="article-content">
    <div class="comment-rendered">
      <p>Run <code>updpkgsums</code> if the build fails.</p>
      <p>See https://wiki.archlinux.org/title/PKGBUILD for help.</p>
    </div>
  </div>
  <h4 class="comment-header" id="comment-101">
    <a href="/account/bob">bob</a> commented on
    <a href="#comment-101" class="date"><time datetime="2024-01-15T09:00:00Z">2024-01-15 09:00</time></a>
  </h4>
  <div id="comment-101-content" class="article-content">
    <div class="comment-rendered"><p>Doesn't build on current glibc.</p></div>
  </div>
</div>
</body></html>
"""


class ParseCommentsTest(unittest.TestCase):
    def test_extracts_author_date_body_in_order(self):
        out = ac.parse_comments(SAMPLE)
        self.assertEqual(2, len(out))
        self.assertEqual('maintainer', out[0]['author'])
        self.assertEqual('2024-02-01T10:00:00Z', out[0]['date'])
        self.assertIn('updpkgsums', out[0]['body'])
        self.assertIn('https://wiki.archlinux.org/title/PKGBUILD', out[0]['body'])
        self.assertEqual('bob', out[1]['author'])
        self.assertIn('glibc', out[1]['body'])

    def test_body_is_plain_text_no_tags(self):
        body = ac.parse_comments(SAMPLE)[0]['body']
        self.assertNotIn('<', body)   # no leftover HTML tags
        self.assertNotIn('>', body)

    def test_empty_and_garbage_return_empty_list(self):
        self.assertEqual([], ac.parse_comments(''))
        self.assertEqual([], ac.parse_comments(None))
        self.assertEqual([], ac.parse_comments('<html><body>no comments</body></html>'))

    def test_limit_caps_results(self):
        many = '\n'.join(
            f'<h4 class="comment-header"><a href="/account/u{i}">u{i}</a></h4>'
            f'<div class="article-content"><p>body {i}</p></div>'
            for i in range(40))
        out = ac.parse_comments(f'<div class="comments">{many}</div>', limit=20)
        self.assertEqual(20, len(out))

    def test_comment_without_body_is_skipped(self):
        # a header with no following article-content yields nothing (we only emit when a body exists)
        html = '<h4 class="comment-header"><a href="/account/x">x</a></h4>'
        self.assertEqual([], ac.parse_comments(html))


if __name__ == '__main__':
    unittest.main()
