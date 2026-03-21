"""Tests for the message bus."""

import json
from pathlib import Path

import pytest

from genesis.bus.message_bus import Message, MessageBus


@pytest.fixture
def bus(tmp_path: Path) -> MessageBus:
    return MessageBus(tmp_path / "messages")


class TestMessage:
    def test_create_sets_timestamp(self):
        msg = Message.create(agent="planner", event="task-assigned", task_bookmark="#foo")
        assert msg.timestamp  # non-empty ISO 8601
        assert msg.agent == "planner"
        assert msg.event == "task-assigned"
        assert msg.task_bookmark == "#foo"
        assert msg.payload == {}

    def test_roundtrip_json(self):
        msg = Message.create(
            agent="builder",
            event="design-complete",
            task_bookmark="#bar",
            payload={"artifacts": ["design.md"]},
        )
        restored = Message.from_json(msg.to_json())
        assert restored.agent == msg.agent
        assert restored.event == msg.event
        assert restored.task_bookmark == msg.task_bookmark
        assert restored.payload == msg.payload

    def test_filename_format(self):
        msg = Message(
            timestamp="2026-03-20T12:00:00+00:00",
            agent="planner",
            event="task-assigned",
            task_bookmark="#foo",
        )
        assert msg.filename == "2026-03-20T12-00-00p00-00_planner_task-assigned.json"


class TestMessageBus:
    def test_publish_creates_file(self, bus: MessageBus):
        msg = Message.create(agent="planner", event="task-assigned", task_bookmark="#t1")
        path = bus.publish(msg)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["agent"] == "planner"

    def test_query_by_agent(self, bus: MessageBus):
        bus.publish(Message.create(agent="planner", event="e1", task_bookmark="#t1"))
        bus.publish(Message.create(agent="builder", event="e2", task_bookmark="#t1"))
        results = bus.query(agent="planner")
        assert len(results) == 1
        assert results[0].agent == "planner"

    def test_query_by_event(self, bus: MessageBus):
        bus.publish(Message.create(agent="planner", event="task-assigned", task_bookmark="#t1"))
        bus.publish(Message.create(agent="planner", event="design-complete", task_bookmark="#t1"))
        results = bus.query(event="design-complete")
        assert len(results) == 1

    def test_query_by_task(self, bus: MessageBus):
        bus.publish(Message.create(agent="planner", event="e1", task_bookmark="#t1"))
        bus.publish(Message.create(agent="planner", event="e2", task_bookmark="#t2"))
        results = bus.query(task_bookmark="#t1")
        assert len(results) == 1

    def test_query_combined_filters(self, bus: MessageBus):
        bus.publish(Message.create(agent="planner", event="e1", task_bookmark="#t1"))
        bus.publish(Message.create(agent="builder", event="e1", task_bookmark="#t1"))
        bus.publish(Message.create(agent="planner", event="e1", task_bookmark="#t2"))
        results = bus.query(agent="planner", task_bookmark="#t1")
        assert len(results) == 1

    def test_recent(self, bus: MessageBus):
        for i in range(5):
            bus.publish(Message.create(agent="a", event=f"e{i}", task_bookmark="#t"))
        results = bus.recent(2)
        assert len(results) == 2

    def test_for_task(self, bus: MessageBus):
        bus.publish(Message.create(agent="planner", event="e1", task_bookmark="#t1"))
        bus.publish(Message.create(agent="builder", event="e2", task_bookmark="#t1"))
        bus.publish(Message.create(agent="planner", event="e3", task_bookmark="#t2"))
        results = bus.for_task("#t1")
        assert len(results) == 2

    def test_creates_directory(self, tmp_path: Path):
        bus = MessageBus(tmp_path / "deep" / "nested" / "messages")
        msg = Message.create(agent="a", event="e", task_bookmark="#t")
        path = bus.publish(msg)
        assert path.exists()

    def test_empty_bus_returns_empty(self, bus: MessageBus):
        assert bus.query() == []
        assert bus.recent(10) == []
        assert bus.for_task("#none") == []
