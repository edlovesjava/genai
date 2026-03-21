"""Smoke tests to verify the genesis package is importable."""


def test_import_genesis():
    import genesis
    assert genesis.__version__ == "0.1.0"


def test_import_subpackages():
    import genesis.agents
    import genesis.bus
    import genesis.state
    import genesis.tools
    import genesis.context


def test_import_quick_task_api():
    from quick_task.api import load_file, get_task, list_tasks, add_task, update_status
    assert callable(load_file)
    assert callable(get_task)
    assert callable(list_tasks)
    assert callable(add_task)
    assert callable(update_status)
