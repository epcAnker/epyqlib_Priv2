import pathlib
from datetime import datetime
from enum import Enum

import PyQt5.uic
import attr
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush, QTextCursor
from PyQt5.QtWidgets import QPushButton, QTreeWidget, QTreeWidgetItem, QLineEdit, QLabel, \
    QPlainTextEdit, QGridLayout
from twisted.internet.defer import ensureDeferred


# noinspection PyUnreachableCode
if False:  # Tell the editor about the type, but don't invoke a cyclic depedency
    from epyqlib.device import DeviceInterface


from epyqlib.tabs.files.graphql import InverterNotFoundException

Ui, UiBase = PyQt5.uic.loadUiType(
    pathlib.Path(__file__).with_suffix('.ui'),
)


# TODO: what about `in_designer=False`

class _Sections:
    params: QTreeWidgetItem
    pvms: QTreeWidgetItem
    firmware: QTreeWidgetItem
    fault_logs: QTreeWidgetItem
    other: QTreeWidgetItem


class Cols:
    filename = 0
    local = 1
    web = 2
    association = 3
    creator = 4
    created_at = 5
    version = 6
    description = 7


class Relationships(Enum):
    inverter = QBrush(QColor(187, 187, 187))  # Gray
    model = QBrush(QColor(112, 173, 71))  # Green
    customer = QBrush(QColor(143, 170, 220))  # Blue
    site = QBrush(QColor(255, 208, 64))  # Yellow



def get_keys(obj):
    return [key for key in obj.__dict__.keys() if not key.startswith("__")]

def get_values(obj):
    return [obj.__dict__[key] for key in get_keys(obj)]

@attr.s
class FilesView(UiBase):
    gray_brush = QBrush(QColor(22, 22, 22, 22))
    check_icon = u'✅'
    question_icon = u'❓'

    device_interface: 'DeviceInterface' = attr.ib(init=False)

    time_format = '%l:%M%p %m/%d'

    ui = attr.ib(factory=Ui)

    @classmethod
    def build(cls):
        instance = cls()
        instance.setup_ui()

        return instance

    @classmethod
    def qt_build(cls, parent):
        instance = cls.build()
        instance.setParent(parent)

        return instance

    def __attrs_post_init__(self):
        super().__init__()

    # noinspection PyAttributeOutsideInit
    def setup_ui(self):
        self.ui.setupUi(self)

        from .files_controller import FilesController
        self.controller = FilesController(self)
        self.controller.setup()

    def set_device_interface(self, device_interface):
        self.device_interface = device_interface

    def tab_selected(self):
        self.controller.tab_selected()

    ### Setup methods
    # noinspection PyAttributeOutsideInit
    def bind(self):
        self.section_headers = _Sections()

        self.root: QGridLayout = self.ui.gridLayout

        self.lbl_not_logged_in: QLabel = self.ui.lbl_not_logged_in
        self.btn_login: QPushButton = self.ui.login

        self.lbl_serial_number: QLabel = self.ui.lbl_serial_number
        self.serial_number: QLineEdit = self.ui.serial_number
        self.inverter_error: QLabel = self.ui.lbl_inverter_error

        self.files_grid: QTreeWidget = self.ui.treeWidget

        self.assigned_by: QLineEdit = self.ui.assigned_by
        self.assigned_time: QLineEdit = self.ui.assigned_time
        self.description: QLineEdit = self.ui.description
        self.filename: QLineEdit = self.ui.filename
        self.upload_time: QLineEdit = self.ui.upload_time
        self.version: QLineEdit = self.ui.version

        self.notes: QPlainTextEdit = self.ui.notes
        self.btn_save_notes: QPushButton = self.ui.save_notes
        self.btn_reset_notes: QPushButton = self.ui.reset_notes

        self.btn_save_file_as: QPushButton = self.ui.save_file_as
        self.btn_send_to_inverter: QPushButton = self.ui.send_to_inverter

        self.lbl_last_sync: QLabel = self.ui.last_sync
        self.btn_sync_now: QPushButton = self.ui.sync_now

        # Bind click events
        self.btn_login.clicked.connect(self._login_clicked)
        self.serial_number.returnPressed.connect(self._sync_now_clicked)

        self.files_grid.itemClicked.connect(self.controller.file_item_clicked)

        self.btn_save_file_as.clicked.connect(self._save_file_as_clicked)
        self.btn_sync_now.clicked.connect(self._sync_now_clicked)

        self.notes.textChanged.connect(self._notes_changed)
        self.btn_reset_notes.clicked.connect(self._reset_notes)

        # Set initial state
        self.lbl_not_logged_in.setText("<font color='red'><b>Warning: You are not currently logged in to EPC Sync. "
                                       "To sync the latest configuration files for this inverter, login here:</b></font>")


    def populate_tree(self):
        self.files_grid.setAlternatingRowColors(True)

        self.files_grid.setHeaderLabels(get_keys(Cols))
        self.files_grid.setColumnWidth(Cols.filename, 250)
        self.files_grid.setColumnWidth(Cols.local, 35)
        self.files_grid.setColumnWidth(Cols.web, 30)
        self.files_grid.setColumnWidth(Cols.association, 150)
        self.files_grid.setColumnWidth(Cols.description, 500)

        def make_entry(caption):
            val = QTreeWidgetItem(self.files_grid, [caption])
            val.setExpanded(True)
            return val

        self.section_headers.params = make_entry("Parameter Sets")
        self.section_headers.pvms = make_entry("Value Sets")
        self.section_headers.firmware = make_entry("Firmware")
        self.section_headers.fault_logs = make_entry("Fault Logs")
        self.section_headers.other = make_entry("Other files")

    def enable_file_buttons(self, enable):
        self.btn_save_file_as.setDisabled(not enable)
        self.btn_send_to_inverter.setDisabled(not enable)

    def initialize_ui(self):
        self.enable_file_buttons(False)
        self.btn_sync_now.setDisabled(True)

        self.serial_number.setReadOnly(False)  #TODO: Link to whether or not they have admin access
        self.show_inverter_error(None)


    def _remove_all_children(self, parent: QTreeWidgetItem):
        while parent.childCount() > 0:
            parent.removeChild(parent.child(0))

    def enable_grid_sorting(self, enable: bool):
        self.files_grid.setSortingEnabled(enable)

        if enable is True:
            self.files_grid.sortByColumn(Cols.filename, Qt.SortOrder.AscendingOrder)


    def attach_row_to_parent(self, type: str, filename):
        parents = {
            'firmware': self.section_headers.firmware,
            'log': self.section_headers.fault_logs,
            'other': self.section_headers.other,
            'parameter': self.section_headers.params,
            'pvms': self.section_headers.pvms
        }

        parent = parents[type]
        row = QTreeWidgetItem(parent, [filename, self.question_icon, self.check_icon])
        row.setTextAlignment(Cols.local, Qt.AlignRight)
        return row

    def remove_row(self, row: QTreeWidgetItem):
        self.files_grid.removeItemWidget(row)

    def show_relationship(self, row: QTreeWidgetItem, relationship: Relationships, rel_text: str):
        row.setBackground(Cols.association, relationship.value)
        row.setText(Cols.association, rel_text)

    ### Action
    def _sync_now_clicked(self):
        ensureDeferred(self.controller.sync_now())

    def _login_clicked(self):
        ensureDeferred(self.controller.login_clicked())

    def _save_file_as_clicked(self):
        ensureDeferred(self.controller.save_file_as_clicked())

    def _notes_changed(self):
        ensureDeferred(self._disable_notes_buttons())

    def _reset_notes(self):
        self.notes.setPlainText(self.controller.old_notes)
        self.notes.moveCursor(QTextCursor.End)

    async def _disable_notes_buttons(self):
        changed = self.controller.notes_modified(self.notes.toPlainText())

        self.btn_save_notes.setDisabled(not changed)
        self.btn_reset_notes.setDisabled(not changed)

    def set_serial_number(self, serial_number: str):
        self.serial_number.setText(serial_number)

    def inverter_error_handler(self, error):
        if error.type is InverterNotFoundException:  #Twisted wraps errors in its own class
            self.show_inverter_error("Error: Inverter ID not found.")
        else:
            raise error


    ### UI Update methods
    def show_logged_out_warning(self, enabled):
        self.lbl_not_logged_in.setHidden(not enabled)
        self.btn_login.setHidden(not enabled)

        self.lbl_serial_number.setHidden(enabled)
        self.serial_number.setHidden(enabled)
        self.inverter_error.setHidden(enabled)

    def show_file_details(self, association):
        if association is not None:
            self.filename.setText(association['file']['filename'])
            self.version.setText(association['file']['version'])
            self.description.setText(association['file']['description'])
            self.controller.set_original_notes(association['file']['notes'])
            self.notes.setPlainText(association['file']['notes'])
            self.notes.setReadOnly(False)
        else:
            self.filename.clear()
            self.version.clear()
            self.notes.setReadOnly(True)
            self.notes.clear()

    def enable_file_action_buttons(self, enabled):
        self.btn_send_to_inverter.setDisabled(not enabled)
        self.btn_save_file_as.setDisabled(not enabled)

    def show_inverter_error(self, error):
        if error is None:
            self.inverter_error.setText("")
        else:
            self.inverter_error.setText(f"<font color='red'>{error}</font>")

    def show_sync_time(self, time: datetime):
        self.lbl_last_sync.setText(f'Last sync at:{time.strftime(self.time_format)}')




# .ui files need a direct module attribute, not a class method, afaict.
FilesViewQtBuilder = FilesView.qt_build
