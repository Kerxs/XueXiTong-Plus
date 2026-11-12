# -*- coding: utf-8 -*-
"""List models backing the QML log panel and running task list."""

from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, Qt, Property, Signal, Slot

LEVEL_GROUPS = {
    "ALL": None,
    "INFO": {"INFO", "SUCCESS"},
    "WARNING": {"WARNING"},
    "ERROR": {"ERROR", "CRITICAL"},
}


class LogModel(QAbstractListModel):
    """Keeps the last ``limit`` log lines and exposes a level-filtered view.

    Entries are addressed by an absolute sequence number (``_base`` + position), so dropping
    the oldest line only removes that one row instead of resetting the whole view - a reset
    per line made the log panel rebuild every row several times a second on long runs.
    """

    LevelRole = Qt.ItemDataRole.UserRole + 1
    MessageRole = Qt.ItemDataRole.UserRole + 2
    TimeRole = Qt.ItemDataRole.UserRole + 3

    filterChanged = Signal()
    countChanged = Signal()

    def __init__(self, limit: int = 1200, parent=None) -> None:
        super().__init__(parent)
        self._limit = limit
        self._entries: list[tuple[str, str, str]] = []
        self._base = 0                  # absolute number of self._entries[0]
        self._visible: list[int] = []   # absolute numbers of the rows shown
        self._filter = "ALL"

    def roleNames(self):
        return {
            self.LevelRole: QByteArray(b"level"),
            self.MessageRole: QByteArray(b"message"),
            self.TimeRole: QByteArray(b"time"),
        }

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._visible)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._visible):
            return None
        level, message, time = self._entries[self._visible[index.row()] - self._base]
        if role == self.LevelRole:
            return level
        if role in (self.MessageRole, Qt.ItemDataRole.DisplayRole):
            return message
        if role == self.TimeRole:
            return time
        return None

    def _accepts(self, level: str) -> bool:
        group = LEVEL_GROUPS.get(self._filter)
        return group is None or level in group

    def _rebuild(self) -> None:
        self.beginResetModel()
        self._visible = [self._base + i for i, entry in enumerate(self._entries) if self._accepts(entry[0])]
        self.endResetModel()
        self.countChanged.emit()

    def append(self, level: str, message: str, time: str = "") -> None:
        if level in ("TRACE", "DEBUG"):
            return
        self._entries.append((level, message, time))
        if self._accepts(level):
            row = len(self._visible)
            self.beginInsertRows(QModelIndex(), row, row)
            self._visible.append(self._base + len(self._entries) - 1)
            self.endInsertRows()
        overflow = len(self._entries) - self._limit
        if overflow > 0:
            del self._entries[:overflow]
            self._base += overflow
            gone = 0
            while gone < len(self._visible) and self._visible[gone] < self._base:
                gone += 1
            if gone:
                self.beginRemoveRows(QModelIndex(), 0, gone - 1)
                del self._visible[:gone]
                self.endRemoveRows()
        self.countChanged.emit()

    def _get_filter(self) -> str:
        return self._filter

    def _set_filter(self, value: str) -> None:
        value = value if value in LEVEL_GROUPS else "ALL"
        if value != self._filter:
            self._filter = value
            self._rebuild()
            self.filterChanged.emit()

    levelFilter = Property(str, _get_filter, _set_filter, notify=filterChanged)
    count = Property(int, lambda self: len(self._visible), notify=countChanged)

    @Slot()
    def clear(self) -> None:
        self.beginResetModel()
        self._entries.clear()
        self._visible.clear()
        self._base = 0
        self.endResetModel()
        self.countChanged.emit()

    @Slot(result=str)
    def visibleText(self) -> str:
        lines = []
        for i in self._visible:
            level, message, time = self._entries[i - self._base]
            lines.append(f"{time} {level:<8} {message}".strip())
        return "\n".join(lines)


class TaskModel(QAbstractListModel):
    """Recently active video/audio tasks with their progress."""

    NameRole = Qt.ItemDataRole.UserRole + 1
    PercentRole = Qt.ItemDataRole.UserRole + 2
    DetailRole = Qt.ItemDataRole.UserRole + 3
    DoneRole = Qt.ItemDataRole.UserRole + 4
    StateRole = Qt.ItemDataRole.UserRole + 5      # running | done | pending | failed | stopped

    countChanged = Signal()

    def __init__(self, limit: int = 30, parent=None) -> None:
        super().__init__(parent)
        self._limit = limit
        self._items: list[dict] = []

    def roleNames(self):
        return {
            self.NameRole: QByteArray(b"name"),
            self.PercentRole: QByteArray(b"percent"),
            self.DetailRole: QByteArray(b"detail"),
            self.DoneRole: QByteArray(b"done"),
            self.StateRole: QByteArray(b"state"),
        }

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        item = self._items[index.row()]
        return {
            self.NameRole: item["name"],
            Qt.ItemDataRole.DisplayRole: item["name"],
            self.PercentRole: item["percent"],
            self.DetailRole: item["detail"],
            self.DoneRole: item["done"],
            self.StateRole: item["state"],
        }.get(role)

    count = Property(int, lambda self: len(self._items), notify=countChanged)

    def _find(self, name: str) -> int:
        for row, item in enumerate(self._items):
            if item["name"] == name:
                return row
        return -1

    def _changed(self, row: int) -> None:
        index = self.index(row)
        self.dataChanged.emit(index, index)

    STATE_TEXT = {"done": "已完成", "pending": "待确认", "failed": "未完成，稍后重试", "stopped": "已停止"}

    def start(self, name: str) -> None:
        """The task starts (again): a row left from an earlier try goes back to running."""
        row = self._find(name)
        if row >= 0:
            self._items[row].update(done=False, state="running", percent=0)
        self.upsert(name, detail="进行中")

    def finish(self, name: str, state: str) -> None:
        """The task ended: done | pending | failed. A row never stays "进行中" after its task ended."""
        self.upsert(name, detail=self.STATE_TEXT[state], done=state == "done", state=state)

    def upsert(self, name: str, percent: int | None = None, detail: str | None = None, done: bool = False,
               state: str | None = None) -> None:
        row = self._find(name)
        if row < 0:
            # Newest first so the active task stays at the top of the list.
            self.beginInsertRows(QModelIndex(), 0, 0)
            self._items.insert(0, {"name": name, "percent": 0, "detail": "", "done": False, "state": "running"})
            self.endInsertRows()
            row = 0
            if len(self._items) > self._limit:
                last = len(self._items) - 1
                self.beginRemoveRows(QModelIndex(), last, last)
                self._items.pop()
                self.endRemoveRows()
            self.countChanged.emit()
        item = self._items[row]
        if state is None and item["state"] != "running":
            # A progress line that arrives after the result line (tqdm's last redraw) changes nothing.
            return
        if percent is not None:
            item["percent"] = percent
        if detail is not None:
            item["detail"] = detail
        if state is not None:
            item["state"] = state
        if done:
            item["done"] = True
            item["state"] = "done"
            item["percent"] = 100
        self._changed(row)

    def finish_running(self) -> None:
        """Stop showing tasks as running once the worker exits."""
        for row, item in enumerate(self._items):
            if item["state"] == "running":
                item["state"] = "stopped"
                item["detail"] = self.STATE_TEXT["stopped"]
                self._changed(row)

    def clear(self) -> None:
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()
        self.countChanged.emit()
