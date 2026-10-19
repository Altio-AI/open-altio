"""Memory facts the build records and the doctor checks."""

from open_altio import machine


def test_the_peak_memory_of_this_process_is_less_than_the_machine_has():
    assert 0 < machine.peak_rss_bytes() < machine.total_memory_bytes()
