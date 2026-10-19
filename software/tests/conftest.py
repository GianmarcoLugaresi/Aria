"""Nessun test deve toccare i dati veri di Aria (~/.aria: memoria, timer, frasi salvate): la "Home" dei test e' una cartella temporanea."""
import os
import sys

import pytest


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path_factory, monkeypatch):
    home = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("HOME", str(home))
    if sys.platform == "win32":                             # su Windows la Home e' USERPROFILE, non HOME: i test restano comunque chiusi nella loro cartella
        monkeypatch.setenv("USERPROFILE", str(home))


@pytest.fixture(autouse=True)
def _no_variety(monkeypatch):
    import aria.textutil as T
    monkeypatch.setattr(T, "VARIETY", False)                # le conferme sono sempre la prima variante: i test confrontano frasi esatte


# Prove che usano i programmi di supporto del Mac (finti, scritti come script eseguibili con «#!») o che dipendono dal Mac: altrove si saltano.
MAC_ONLY = {
    "test_apple_stt_talks_to_the_helper_and_cleans_the_text", "test_apple_stt_drops_whisper_style_hallucinations", "test_the_router_treats_apple_as_a_local_engine_not_as_a_server_to_ping",
    "test_the_answer_to_a_cancelled_request_is_not_given_to_the_next_one", "test_the_echo_filter_is_on_only_during_a_conversation_and_the_plain_mic_covers_the_switch",
    "test_the_clean_mic_falls_back_to_the_normal_one_when_the_helper_is_missing_or_keeps_failing", "test_a_helper_that_says_ready_but_sends_no_audio_makes_the_mic_fall_back_and_stay_there_for_a_while",
    "test_the_ocr_helper_talks_in_lines_and_forgets_answers_to_cancelled_requests", "test_the_pointer_helper_is_started_with_the_boxes_and_not_waited_for",
    "test_a_very_long_answer_line_from_the_helpers_is_read_in_full", "test_when_the_permission_keeps_failing_aria_explains_the_stale_entry_and_checks_with_a_fresh_helper",
    "test_pocket_voice_becomes_the_automatic_voice_so_the_natural_one_can_be_switched_on_live",        # la voce «naturale» (MLX) esiste solo sul Mac
    "test_remove_deletes_only_inside_the_hf_cache",                                                     # (usa i modelli Hugging Face del Mac)
    "test_check_root_refuses_dangerous_folders", "test_settings_choose_and_clear_the_folder_without_losing_model_choices",   # (cartelle di sistema POSIX: «/System», «/Applications»; per Windows c'e' test_windows_system_folders_…)
}


# Prove che contano su pause di 10-20 ms: su Windows i timer di asyncio hanno una risoluzione di 15,6 ms e una pausa piu' corta non aspetta niente.
TIMING = {"test_the_key_while_aria_speaks_stops_her_even_if_the_app_thinks_she_is_idle_and_sends_wake", "test_on_battery_with_the_screen_off_she_stops_listening_so_the_mac_can_sleep_and_comes_back"}


def pytest_collection_modifyitems(config, items):
    if sys.platform == "darwin":
        return
    skip_mac = pytest.mark.skip(reason="solo sul Mac (programmi di supporto di macOS o percorsi POSIX)")
    skip_timing = pytest.mark.skip(reason="conta su pause di 10-20 ms: su Windows i timer di asyncio hanno una risoluzione di 15,6 ms")
    for item in items:
        if item.name in MAC_ONLY:
            item.add_marker(skip_mac)
        elif item.name in TIMING:
            item.add_marker(skip_timing)
