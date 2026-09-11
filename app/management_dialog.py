"""应用管理后台：维护本地预览缓存和 SKU 数据。"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .image_processor import clear_thumbnail_cache, thumbnail_cache_info
from .product_catalog import parse_colors, save_product_catalog
from .window_style import enable_dark_title_bar


def _format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


class ManagementDialog(QDialog):
    """独立管理窗口；所有数据都只保存在当前电脑。"""

    catalog_changed = Signal(object)

    def __init__(self, catalog: dict[str, list[str]], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ImageFlow 管理后台")
        self.resize(760, 650)
        self.setMinimumSize(660, 560)
        self.catalog = {sku: list(colors) for sku, colors in catalog.items()}
        self._refreshing_tree = False

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(16)

        title = QLabel("管理后台")
        title.setObjectName("managementTitle")
        subtitle = QLabel("管理本机预览缓存与命名设置中的 SKU 数据。")
        subtitle.setObjectName("managementSubtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        cache_card = QFrame()
        cache_card.setObjectName("managementCard")
        cache_layout = QVBoxLayout(cache_card)
        cache_layout.setContentsMargins(18, 16, 18, 16)
        cache_layout.setSpacing(10)
        cache_header = QHBoxLayout()
        cache_title = QLabel("预览缓存")
        cache_title.setObjectName("managementSectionTitle")
        self.cache_status = QLabel()
        self.cache_status.setObjectName("managementMeta")
        self.clear_cache_button = QPushButton("清除缓存")
        self.clear_cache_button.setObjectName("secondaryButton")
        self.clear_cache_button.clicked.connect(self._clear_cache)
        cache_header.addWidget(cache_title)
        cache_header.addStretch()
        cache_header.addWidget(self.cache_status)
        cache_header.addWidget(self.clear_cache_button)
        cache_note = QLabel("只清除为加快启动生成的缩略图，下次使用时会自动重新生成，不会删除原图或项目。")
        cache_note.setObjectName("managementHint")
        cache_note.setWordWrap(True)
        cache_layout.addLayout(cache_header)
        cache_layout.addWidget(cache_note)
        root.addWidget(cache_card)

        sku_card = QFrame()
        sku_card.setObjectName("managementCard")
        sku_layout = QVBoxLayout(sku_card)
        sku_layout.setContentsMargins(18, 16, 18, 16)
        sku_layout.setSpacing(12)
        sku_header = QHBoxLayout()
        sku_title = QLabel("SKU 管理")
        sku_title.setObjectName("managementSectionTitle")
        self.sku_count = QLabel()
        self.sku_count.setObjectName("managementMeta")
        sku_header.addWidget(sku_title)
        sku_header.addStretch()
        sku_header.addWidget(self.sku_count)
        sku_layout.addLayout(sku_header)

        self.sku_tree = QTreeWidget()
        self.sku_tree.setObjectName("skuManagementTree")
        self.sku_tree.setColumnCount(2)
        self.sku_tree.setHeaderLabels(["SKU", "可选颜色"])
        self.sku_tree.setRootIsDecorated(False)
        self.sku_tree.setAlternatingRowColors(True)
        self.sku_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.sku_tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sku_tree.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.sku_tree.setToolTip("双击 SKU 或颜色可直接编辑；点击空白处自动保存")
        self.sku_tree.itemChanged.connect(self._on_sku_item_changed)
        self.sku_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.sku_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        sku_layout.addWidget(self.sku_tree, 1)

        input_row = QHBoxLayout()
        self.sku_name_edit = QLineEdit()
        self.sku_name_edit.setPlaceholderText("输入新 SKU，例如 Air75 V3")
        self.sku_colors_edit = QLineEdit()
        self.sku_colors_edit.setPlaceholderText("可选颜色，用逗号分隔")
        self.add_sku_button = QPushButton("添加 SKU")
        self.add_sku_button.setObjectName("primaryCompactButton")
        self.add_sku_button.clicked.connect(self._add_sku)
        self.sku_name_edit.returnPressed.connect(self._add_sku)
        input_row.addWidget(self.sku_name_edit, 2)
        input_row.addWidget(self.sku_colors_edit, 3)
        input_row.addWidget(self.add_sku_button)
        sku_layout.addLayout(input_row)

        action_row = QHBoxLayout()
        delete_button = QPushButton("删除选中 SKU")
        delete_button.setObjectName("dangerButton")
        delete_button.clicked.connect(self._delete_selected_sku)
        action_row.addWidget(delete_button)
        action_row.addStretch()
        sku_layout.addLayout(action_row)
        root.addWidget(sku_card, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        close_button = QPushButton("完成")
        close_button.setObjectName("primaryButton")
        close_button.setMinimumWidth(130)
        close_button.clicked.connect(self.accept)
        footer.addWidget(close_button)
        root.addLayout(footer)

        self._refresh_cache_status()
        self._refresh_sku_tree()

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        enable_dark_title_bar(self)

    def _refresh_cache_status(self) -> None:
        count, size = thumbnail_cache_info()
        self.cache_status.setText(f"{count} 个文件 · {_format_bytes(size)}")
        self.clear_cache_button.setEnabled(count > 0)

    def _clear_cache(self) -> None:
        answer = QMessageBox.question(
            self,
            "清除预览缓存",
            "确定清除本机预览缓存吗？\n下次打开照片时会自动重新生成。",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        count, size = clear_thumbnail_cache()
        self._refresh_cache_status()
        QMessageBox.information(self, "缓存已清除", f"已清除 {count} 个缓存文件，共 {_format_bytes(size)}。")

    def _refresh_sku_tree(self, selected_sku: str = "") -> None:
        self._refreshing_tree = True
        self.sku_tree.blockSignals(True)
        try:
            self.sku_tree.clear()
            selected_item: Optional[QTreeWidgetItem] = None
            for sku, colors in self.catalog.items():
                item = QTreeWidgetItem([sku, ", ".join(colors)])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                item.setData(0, Qt.ItemDataRole.UserRole, sku)
                self.sku_tree.addTopLevelItem(item)
                if sku == selected_sku:
                    selected_item = item
            if selected_item:
                self.sku_tree.setCurrentItem(selected_item)
                self.sku_tree.scrollToItem(selected_item)
            self.sku_count.setText(f"共 {len(self.catalog)} 个 SKU")
        finally:
            self.sku_tree.blockSignals(False)
            self._refreshing_tree = False

    def _on_sku_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """单元格编辑结束（包括点击空白处）后立即校验并保存。"""
        if self._refreshing_tree:
            return
        original_sku = str(item.data(0, Qt.ItemDataRole.UserRole) or "")
        if original_sku not in self.catalog:
            self._refresh_sku_tree()
            return
        snapshot = {sku: list(colors) for sku, colors in self.catalog.items()}
        selected_sku = original_sku
        if column == 0:
            new_sku = item.text(0).strip()
            if not new_sku:
                QMessageBox.information(self, "SKU 不能为空", "请输入有效的 SKU 名称。")
                self._refresh_sku_tree(original_sku)
                return
            duplicate = next(
                (name for name in self.catalog if name != original_sku and name.casefold() == new_sku.casefold()),
                "",
            )
            if duplicate:
                QMessageBox.information(self, "SKU 已存在", f"“{duplicate}”已经在列表中。")
                self._refresh_sku_tree(original_sku)
                return
            if new_sku != original_sku:
                self.catalog = {
                    (new_sku if sku == original_sku else sku): colors
                    for sku, colors in self.catalog.items()
                }
                selected_sku = new_sku
        elif column == 1:
            self.catalog[original_sku] = parse_colors(item.text(1))
        else:
            return
        if not self._save_catalog():
            self.catalog = snapshot
            self._refresh_sku_tree(original_sku)
            return
        self._refresh_sku_tree(selected_sku)

    def _save_catalog(self) -> bool:
        try:
            save_product_catalog(self.catalog)
        except OSError as error:
            QMessageBox.critical(self, "SKU 保存失败", str(error))
            return False
        self.catalog_changed.emit({sku: list(colors) for sku, colors in self.catalog.items()})
        return True

    def _add_sku(self) -> None:
        sku = self.sku_name_edit.text().strip()
        if not sku:
            self.sku_name_edit.setFocus()
            return
        duplicate = next((name for name in self.catalog if name.casefold() == sku.casefold()), "")
        if duplicate:
            QMessageBox.information(self, "SKU 已存在", f"“{duplicate}”已经在列表中。")
            self._refresh_sku_tree(duplicate)
            return
        colors = parse_colors(self.sku_colors_edit.text())
        self.catalog[sku] = colors
        if not self._save_catalog():
            self.catalog.pop(sku, None)
            return
        self._refresh_sku_tree(sku)
        self.sku_name_edit.clear()
        self.sku_colors_edit.clear()
        self.sku_name_edit.setFocus()

    def _delete_selected_sku(self) -> None:
        item = self.sku_tree.currentItem()
        if not item:
            QMessageBox.information(self, "尚未选择 SKU", "请先在列表中选择需要删除的 SKU。")
            return
        sku = item.text(0)
        answer = QMessageBox.question(self, "删除 SKU", f"确定从后台删除“{sku}”吗？")
        if answer != QMessageBox.StandardButton.Yes:
            return
        colors = self.catalog.pop(sku, [])
        if not self._save_catalog():
            self.catalog[sku] = colors
            return
        self._refresh_sku_tree()
