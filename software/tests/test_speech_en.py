"""Cio' che il chatbot scrive, pronto per essere DETTO in inglese: numeri, orari, date, valute, unita', indirizzi."""
import pytest

from aria import speech


@pytest.fixture(autouse=True)
def _en(english):
    pass


@pytest.mark.parametrize("written,said", [
    ("It's 18°C and sunny, with a high of 24 °C.", "It's eighteen degrees Celsius and sunny, with a high of twenty-four degrees Celsius."),
    ("The meeting is at 3:30 PM on 10/22.", "The meeting is at three thirty p m on October twenty-second."),
    ("Call me at 5 pm. Then we go.", "Call me at five p m. Then we go."),
    ("Meet at 10:05 a.m. Bring snacks.", "Meet at ten oh five a m. Bring snacks."),
    ("That costs $4.99, or about €4.50.", "That costs four dollars and ninety-nine cents, or about four euros and fifty cents."),
    ("It's 12 km away, about 7.5 miles.", "It's twelve kilometers away, about seven point five miles."),
    ("In 1999 and 2026 it changed.", "In nineteen ninety-nine and twenty twenty-six it changed."),
    ("He was born on March 3rd, 1985.", "He was born on March third, nineteen eighty-five."),
    ("It rained 20% less than 2019.", "It rained twenty percent less than twenty nineteen."),
    ("The temperature dropped to -5°C.", "The temperature dropped to minus five degrees Celsius."),
    ("I scored 9/10!", "I scored nine out of ten!"),
    ("half is 1/2 and 3/4 too", "half is one half and three quarters too"),
    ("Use Wi-Fi at 2.4GHz.", "Use Wi-Fi at two point four gigahertz."),
    ("Visit https://example.com/page for more.", "Visit example dot com for more."),
    ("The population is 1,250,000.", "The population is one million two hundred fifty thousand."),
    ("He's 25-30 years old", "He's twenty-five to thirty years old"),
    ("The score was 3-2.", "The score was three-two."),
    ("It's 5'11\" tall.", "It's five foot eleven tall."),
    ("1st, 2nd, 3rd, 21st place", "first, second, third, twenty-first place"),
    ("e.g. apples, i.e. fruit, etc.", "for example apples, that is fruit, et cetera"),
    ("It costs $1500.", "It costs one thousand five hundred dollars."),
    ("2026-10-21", "October twenty-first, twenty twenty-six"),
])
def test_what_is_written_becomes_what_is_said(written, said):
    assert speech.speechify(written) == said


@pytest.mark.parametrize("written,spoken", [
    ("Call 555-0134 tomorrow.", "Call five five five, zero one three four tomorrow."),
    ("Call (555) 123-4567 now.", "Call five five five, one two three, four five six seven now."),
    ("Call 1-800-555-0199 now.", "Call one, eight zero zero, five five five, zero one nine nine now."),
    ("Use the Wi-Fi at 192.168.1.1.", "Use the Wi-Fi at one hundred ninety-two dot one hundred sixty-eight dot one dot one."),
    ("Mix 1/2 cup of sugar with 2 1/4 cups of flour.", "Mix one half cup of sugar with two and one quarter cups of flour."),
    ("That was #1 on the charts.", "That was number one on the charts."),
    ("The ratio is 3:1.", "The ratio is three to one."),
    ("It starts at 3:45 pm.", "It starts at three forty-five p m."),
    ("Main St. near the park.", "Main Street near the park."),
    ("St. John's Church on Elm St.", "Saint John's Church on Elm Street."),
    ("Due 13/02/25.", "Due February thirteenth, twenty twenty-five."),
])
def test_phone_numbers_addresses_fractions_and_dates_are_read_like_a_person(written, spoken):
    assert speech.speechify(written) == spoken


def test_a_numeric_date_follows_the_region():
    from unittest import mock
    from aria import i18n
    with mock.patch.object(i18n, "units", lambda cfg=None: "imperial"):
        assert speech.speechify("Born on 04/07/1990.") == "Born on April seventh, nineteen ninety."
    with mock.patch.object(i18n, "units", lambda cfg=None: "metric"):
        assert speech.speechify("Born on 04/07/1990.") == "Born on July fourth, nineteen ninety."
