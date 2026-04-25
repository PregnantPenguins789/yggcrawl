import main

def test_get_node_state_basic():
    class DummyCrawler:
        queue = [1, 2, 3]
        seen = {1, 2}

    class DummyIndexer:
        index = {"a": 1}

    state = main.get_node_state(DummyIndexer(), DummyCrawler())

    assert state["queue_size"] == 3
    assert state["seen_size"] == 2
    assert state["index_size"] == 1