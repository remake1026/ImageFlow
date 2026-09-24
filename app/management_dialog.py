"""应用管理后台：维护本地预览缓存和产品数据。"""
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
        self.catalog = {product: list(colors) for product, colors in catalog.items()}
        self._refreshing_tree = False

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(16)

        title = QLabel("管理后台")
        title.setObjectName("managementTitle")
        subtitle = QLabel("管理本机预览缓存与命名设置中的产品数据。")
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

        product_card = QFrame()
        product_card.setObjectName("managementCard")
        product_layout = QVBoxLayout(product_card)
        product_layout.setContentsMargins(18, 16, 18, 16)
        product_layout.setSpacing(12)
        product_header = QHBoxLayout()
        product_title = QLabel("产品管理")
        product_title.setObjectName("managementSectionTitle")
        self.product_count = QLabel()
        self.product_count.setObjectName("managementMeta")
        product_header.addWidget(product_title)
        product_header.addStretch()
        product_header.addWidget(self.product_count)
        product_layout.addLayout(product_header)

        self.product_tree = QTreeWidget()
        self.product_tree.setObjectName("productManagementTree")
        self.product_tree.setColumnCount(2)
        self.product_tree.setHeaderLabels(["产品", "可选颜色"])
        self.product_tree.setRootIsDecorated(False)
        self.product_tree.setAlternatingRowColors(True)
        self.product_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.product_tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.product_tree.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.product_tree.setToolTip("双击产品或颜色可直接编辑；点击空白处自动保存")
        self.product_tree.itemChanged.connect(self._on_product_item_changed)
        self.product_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.product_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        product_layout.addWidget(self.product_tree, 1)

        input_row = QHBoxLayout()
        self.product_name_edit = QLineEdit()
        self.product_name_edit.setPlaceholderText("输入产品名称")
        self.product_colors_edit = QLineEdit()
        self.product_colors_edit.setPlaceholderText("可选颜色，用逗号分隔")
        self.add_product_button = QPushButton("添加产品")
        self.add_product_button.setObjectName("primaryCompactButton")
        self.add_product_button.clicked.connect(self._add_product)
        self.product_name_edit.returnPressed.connect(self._add_product)
        input_row.addWidget(self.product_name_edit, 2)
        input_row.addWidget(self.product_colors_edit, 3)
        input_row.addWidget(self.add_product_button)
        product_layout.addLayout(input_row)

        action_row = QHBoxLayout()
        delete_button = QPushButton("删除选中产品")
        delete_button.setObjectName("dangerButton")
        delete_button.clicked.connect(self._delete_selected_product)
        action_row.addWidget(delete_button)
        action_row.addStretch()
        product_layout.addLayout(action_row)
        root.addWidget(product_card, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        close_button = QPushButton("完成")
        close_button.setObjectName("primaryButton")
        close_button.setMinimumWidth(130)
        close_button.clicked.connect(self.accept)
        footer.addWidget(close_button)
        root.addLayout(footer)

        self._refresh_cache_status()
        self._refresh_product_tree()

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

    def _refresh_product_tree(self, selected_product: str = "") -> None:
        self._refreshing_tree = True
        self.product_tree.blockSignals(True)
        try:
            self.product_tree.clear()
            selected_item: Optional[QTreeWidgetItem] = None
            for product, colors in self.catalog.items():
                item = QTreeWidgetItem([product, ", ".join(colors)])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                item.setData(0, Qt.ItemDataRole.UserRole, product)
                self.product_tree.addTopLevelItem(item)
                if product == selected_product:
                    selected_item = item
            if selected_item:
                self.product_tree.setCurrentItem(selected_item)
                self.product_tree.scrollToItem(selected_item)
            self.product_count.setText(f"共 {len(self.catalog)} 个产品")
        finally:
            self.product_tree.blockSignals(False)
            self._refreshing_tree = False

    def _on_product_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """单元格编辑结束（包括点击空白处）后立即校验并保存。"""
        if self._refreshing_tree:
            return
        original_product = str(item.data(0, Qt.ItemDataRole.UserRole) or "")
        if original_product not in self.catalog:
            self._refresh_product_tree()
            return
        snapshot = {product: list(colors) for product, colors in self.catalog.items()}
        selected_product = original_product
        if column == 0:
            new_product = item.text(0).strip()
            if not new_product:
                QMessageBox.information(self, "产品不能为空", "请输入有效的产品名称。")
                self._refresh_product_tree(original_product)
                return
            duplicate = next(
                (name for name in self.catalog if name != original_product and name.casefold() == new_product.casefold()),
                "",
            )
            if duplicate:
                QMessageBox.information(self, "产品已存在", f"“{duplicate}”已经在列表中。")
                self._refresh_product_tree(original_product)
                return
            if new_product != original_product:
                self.catalog = {
                    (new_product if product == original_product else product): colors
                    for product, colors in self.catalog.items()
                }
                selected_product = new_product
        elif column == 1:
            self.catalog[original_product] = parse_colors(item.text(1))
        else:
            return
        if not self._save_catalog():
            self.catalog = snapshot
            self._refresh_product_tree(original_product)
            return
        self._refresh_product_tree(selected_product)

    def _save_catalog(self) -> bool:
        try:
            save_product_catalog(self.catalog)
        except OSError as error:
            QMessageBox.critical(self, "产品保存失败", str(error))
            return False
        self.catalog_changed.emit({product: list(colors) for product, colors in self.catalog.items()})
        return True

    def _add_product(self) -> None:
        product = self.product_name_edit.text().strip()
        if not product:
            self.product_name_edit.setFocus()
            return
        duplicate = next((name for name in self.catalog if name.casefold() == product.casefold()), "")
        if duplicate:
            QMessageBox.information(self, "产品已存在", f"“{duplicate}”已经在列表中。")
            self._refresh_product_tree(duplicate)
            return
        colors = parse_colors(self.product_colors_edit.text())
        self.catalog[product] = colors
        if not self._save_catalog():
            self.catalog.pop(product, None)
            return
        self._refresh_product_tree(product)
        self.product_name_edit.clear()
        self.product_colors_edit.clear()
        self.product_name_edit.setFocus()

    def _delete_selected_product(self) -> None:
        item = self.product_tree.currentItem()
        if not item:
            QMessageBox.information(self, "尚未选择产品", "请先在列表中选择需要删除的产品。")
            return
        product = item.text(0)
        answer = QMessageBox.question(self, "删除产品", f"确定从后台删除“{product}”吗？")
        if answer != QMessageBox.StandardButton.Yes:
            return
        colors = self.catalog.pop(product, [])
        if not self._save_catalog():
            self.catalog[product] = colors
            return
        self._refresh_product_tree()
