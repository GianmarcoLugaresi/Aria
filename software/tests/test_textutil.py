from aria.textutil import SentenceChunker, TagFilter, ToolCall, is_stop_command, matches_phrase, normalize, strip_think


def chunks(text, step=7):
    c = SentenceChunker()
    out = []
    for i in range(0, len(text), step):
        out += list(c.push(text[i:i + step]))
    out += list(c.flush())
    return out


def test_first_sentence_leaves_early():
    out = chunks("Canberra. La gente dice Sydney, ma no.")
    assert "".join(out).replace(" ", "") == "Canberra.LagentediceSydney,mano."
    assert len(out) >= 1


def test_does_not_split_abbreviations_or_decimals():
    s = chunks("Ne parla il dott. Rossi nel libro. Costa 3.50 euro, davvero poco. Ok?")
    assert any("dott. Rossi" in x for x in s)
    assert any("3.50" in x for x in s)


def test_long_text_without_punctuation_is_cut():
    s = chunks("parola " * 80)
    assert len(s) >= 2 and all(len(x) <= 240 for x in s)


def test_flush_returns_rest():
    c = SentenceChunker()
    assert list(c.push("Ciao come stai")) == []
    assert list(c.flush()) == ["Ciao come stai"]


def test_tagfilter_whole_and_split():
    f = TagFilter()
    text, calls = f.push("Vediamo. [[CERCA: orari treni Roma Milano]] ")
    assert text.strip() == "Vediamo." and calls == [ToolCall("CERCA", "orari treni Roma Milano")]
    f = TagFilter()
    out, allc = "", []
    for ch in "ok [[METEO: Roma]] fine":
        t, c = f.push(ch)
        out += t
        allc += c
    out += f.flush()
    assert allc == [ToolCall("METEO", "Roma")]
    assert "ok" in out and "fine" in out and "[[" not in out


def test_tagfilter_incomplete_is_held_back():
    f = TagFilter()
    t, c = f.push("ciao [[CERC")
    assert t == "ciao " and c == []
    assert f.flush() == ""            # un comando troncato non va mai pronunciato


def test_tagfilter_lone_bracket_passes_through():
    f = TagFilter()
    t1, _ = f.push("a [")
    t2, _ = f.push("b")
    assert (t1 + t2) == "a [b"


def test_strip_think():
    assert strip_think("<think>ragiono</think>Ciao") == "Ciao"


def test_matches_phrase_tolerates_misrecognition():
    assert matches_phrase("Ciao Aria!", "ciao aria")
    assert matches_phrase("ciao arya che ore sono", "ciao aria")
    assert matches_phrase("eh ciao area", "ciao aria")
    assert not matches_phrase("che aria fredda oggi", "ciao aria")
    assert not matches_phrase("ciao Maria come stai", "ciao aria")            # un nome vero non la sveglia
    assert not matches_phrase("ciao Mario", "ciao aria")
    assert not matches_phrase("ciao a tutti", "ciao aria")
    assert matches_phrase("Ciao, Aria! Che ore sono?", "ciao aria")
    assert matches_phrase("ciaoaria", "ciao aria")
    assert not matches_phrase("", "ciao aria")


def test_hey_aria_is_recognised_however_the_transcription_spells_hey():
    for said in ("Hey Aria", "hey aria!", "Ehi Aria, che ore sono?", "ehi, Aria", "Ei Aria", "Hei aria", "ehy arya", "heyaria", "ehi aria dimmi del tempo", "ok, hey Aria"):
        assert matches_phrase(said, "hey aria"), said
    for said in ("ciao Aria", "che aria fredda oggi", "hey Maria come stai", "ehi Mario", "hey a tutti", "ehi daria", "hey", "", "l'aria condizionata e' accesa", "Ehi Ilaria come stai", "ehi Valeria", "hey Zaira"):
        assert not matches_phrase(said, "hey aria"), said
    assert matches_phrase("Ciao Aria!", "ciao aria")                       # (le altre frasi di attivazione funzionano come prima)


def test_stop_commands():
    assert is_stop_command("Basta!") and is_stop_command("stop") and is_stop_command("zitta")
    assert not is_stop_command("non ti fermare mai")
    assert normalize("Perché?") == "perche"


def test_strip_emoji_and_markdown_symbols():
    from aria.textutil import strip_emoji
    assert strip_emoji("🎉 Scommetto che ti senti sollevato, giusto? 😊") == "Scommetto che ti senti sollevato, giusto?"
    assert strip_emoji("**Ciao** _bello_ #tag") == "Ciao bello tag"
    assert strip_emoji("Fa 15.") == "Fa 15."
    assert strip_emoji("😊") == ""
