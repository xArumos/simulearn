from src.data.select_corpora import overlap_fraction, parse_age_range, parse_index, parse_n


def test_age_range_formats():
    assert parse_age_range("1;6-5;1") == (18, 61)
    assert parse_age_range("2;6, 3;6, 4;6, 5;6") == (30, 66)
    assert parse_age_range("3-10") == (36, 131)
    assert parse_age_range("5 and adult") == (60, 71)
    assert parse_age_range("6, 9, 12 months") == (6, 12)
    assert parse_age_range("2;0.12-4;11.20") == (24, 59)
    assert parse_age_range("--") == (None, None)


def test_parse_n_and_overlap():
    assert parse_n("10 and 10") == 20
    assert parse_n("--") is None
    assert overlap_fraction(48, 71, 60, 71) == 0.5
    assert overlap_fraction(18, 30, 48, 71) == 0


def test_parse_index_row():
    html = """<tr id="tr_heading"><td>Corpus<td>Age Range<td>N<td>Media<td>Comments</td>
    <tr><td bgcolor="dddddd"><a href=Fake.html>Fake</a>
    <td bgcolor="dddddd">4;0-5;11<td bgcolor="dddddd">12<td>audio<td>made-up corpus</td>"""
    [c] = parse_index(html, "Eng-NA")
    assert c.name == "Fake"
    assert c.page_url == "https://talkbank.org/childes/access/Eng-NA/Fake.html"
    assert (c.lo_months, c.hi_months, c.n_children) == (48, 71, 12)
