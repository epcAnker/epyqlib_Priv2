#!/usr/bin/env python3

#TODO: """DocString if there is one"""

import epyqlib.nv
import epyqlib.utils.qt
import functools
import io
import os
import twisted.internet.defer
from PyQt5 import QtWidgets, uic, QtCore
from PyQt5.QtCore import (pyqtSignal, pyqtSlot, QFile, QFileInfo, QTextStream,
                          QCoreApplication, Qt, QItemSelectionModel,
                          QModelIndex, QSortFilterProxyModel)

# See file COPYING in this source tree
__copyright__ = 'Copyright 2016, EPC Power Corp.'
__license__ = 'GPLv2+'


class NvView(QtWidgets.QWidget):
    module_to_nv = pyqtSignal()
    read_from_file = pyqtSignal()
    read_from_value_set_file = pyqtSignal()
    write_to_file = pyqtSignal()
    write_to_value_set_file = pyqtSignal()

    def __init__(self, parent=None, in_designer=False):
        QtWidgets.QWidget.__init__(self, parent=parent)

        self.in_designer = in_designer

        ui = 'nvview.ui'
        # TODO: CAMPid 9549757292917394095482739548437597676742
        if not QFileInfo(ui).isAbsolute():
            ui_file = os.path.join(
                QFileInfo.absolutePath(QFileInfo(__file__)), ui)
        else:
            ui_file = ui
        ui_file = QFile(ui_file)
        ui_file.open(QFile.ReadOnly | QFile.Text)
        ts = QTextStream(ui_file)
        sio = io.StringIO(ts.readAll())
        self.ui = uic.loadUi(sio, self)

        self.ui.module_to_nv_button.clicked.connect(self.module_to_nv)
        self.ui.write_to_module_button.clicked.connect(self.write_to_module)
        self.ui.read_from_module_button.clicked.connect(self.read_from_module)
        self.ui.write_to_file_button.clicked.connect(self.write_to_file)
        self.ui.write_to_value_set_file_button.clicked.connect(
            self.write_to_value_set_file,
        )
        self.ui.read_from_file_button.clicked.connect(self.read_from_file)
        self.ui.read_from_value_set_file_button.clicked.connect(
            self.read_from_value_set_file,
        )

        view = self.ui.tree_view
        view.setContextMenuPolicy(Qt.CustomContextMenu)
        view.customContextMenuRequested.connect(self.context_menu)
        view.setSelectionBehavior(view.SelectRows)
        view.setSelectionMode(view.ExtendedSelection)

        self.resize_columns = epyqlib.nv.Columns(
            name=True,
            value=True,
            user_default=True,
            factory_default=True,
            minimum=True,
            maximum=True,
            comment=True,
        )

        self.progress = None

        self.ui.tree_view.clicked.connect(self.clicked)
        self.ui.tree_view.header().setMinimumSectionSize(0)

        self.ui.searchbox.connect_to_view(
            view=self.ui.tree_view,
            column=epyqlib.nv.Columns.indexes.name,
        )

        self.ui.current_access_level.signal_path = ';'.join((
            'ParameterQuery',
            'AccessLevel',
            'Level',
        ))

        self.password_mapper = QtWidgets.QDataWidgetMapper()
        self.password_mapper.setSubmitPolicy(
            QtWidgets.QDataWidgetMapper.AutoSubmit,
        )
        self.access_level_mapper = QtWidgets.QDataWidgetMapper()
        self.access_level_mapper.setSubmitPolicy(
            QtWidgets.QDataWidgetMapper.AutoSubmit,
        )

        self.ui.access_level_password.setPlaceholderText('Access Code...')

    def filter_text_changed(self, text):
        self.ui.tree_view.model().setFilterWildcard(text)

    # TODO: CAMPid 07943342700734207878034207087
    def nonproxy_model(self):
        model = self.ui.tree_view.model()
        while isinstance(model, QSortFilterProxyModel):
            model = model.sourceModel()

        return model

    def set_sorting_enabled(self, enabled):
        self.ui.tree_view.setSortingEnabled(enabled)

    def sort_by_column(self, column, order):
        self.ui.tree_view.sortByColumn(column, order)

    def write_to_module(self):
        model = self.nonproxy_model()

        def not_none(nv):
            if nv.value is not None:
                return True

            return any(
                getattr(nv.meta, meta.name).value is not None
                for meta in epyqlib.nv.MetaEnum.non_value
            )

        only_these = [nv for nv in model.all_nv()
                      if not_none(nv) is not None]
        callback = functools.partial(
            self.update_signals,
            only_these=only_these
        )
        d = model.root.write_all_to_device(
            callback=callback,
            only_these=only_these,
        )
        d.addErrback(epyqlib.utils.twisted.catch_expected)
        d.addErrback(epyqlib.utils.twisted.errbackhook)

    def read_from_module(self):
        resize_mode = self.ui.tree_view.header().sectionResizeMode(epyqlib.nv.Columns.indexes.value)
        self.ui.tree_view.header().setSectionResizeMode(
            epyqlib.nv.Columns.indexes.value, QtWidgets.QHeaderView.Fixed)
        model = self.nonproxy_model()
        only_these = [nv for nv in model.all_nv()]
        callback = functools.partial(
            self.update_signals,
            only_these=only_these
        )
        d = model.root.read_all_from_device(callback=callback,
                                            only_these=only_these)

        def f():
            self.ui.tree_view.header().setSectionResizeMode(
                epyqlib.nv.Columns.indexes.value, resize_mode
            )
        d.addBoth(epyqlib.utils.twisted.detour_result, f)
        d.addErrback(epyqlib.utils.twisted.catch_expected)
        d.addErrback(epyqlib.utils.twisted.errbackhook)

    def setModel(self, model):
        proxy = model
        proxy.setSortRole(epyqlib.pyqabstractitemmodel.UserRoles.sort)
        self.ui.tree_view.setModel(proxy)

        model = self.nonproxy_model()

        self.password_mapper.setModel(model)
        self.password_mapper.setRootIndex(model.index_from_node(
            model.root.password_node.tree_parent,
        ))
        self.password_mapper.setCurrentIndex(
            model.index_from_node(model.root.password_node).row(),
        )
        self.password_mapper.addMapping(
            self.ui.access_level_password,
            epyqlib.nv.Columns.indexes.value,
        )

        access_level_node = model.root.access_level_node
        self.access_level_mapper.setModel(model)
        self.access_level_mapper.setRootIndex(model.index_from_node(
            access_level_node.tree_parent,
        ))
        access_level_index = model.index_from_node(access_level_node)
        self.access_level_mapper.setCurrentIndex(
            access_level_index.row(),
        )

        # TODO: CAMPid 9754542524161542698615426
        # TODO: use the userdata to make it easier to get in and out
        self.ui.access_level.addItems(
            model.root.access_level_node.enumeration_strings(
                include_values=True,
            ),
        )

        self.access_level_mapper.addMapping(
            self.ui.access_level,
            epyqlib.nv.Columns.indexes.value,
            'currentIndex'.encode('utf-8'),
        )

        delegate = self.access_level_mapper.itemDelegate()
        self.ui.access_level.currentIndexChanged.connect(
            lambda: delegate.commitData.emit(self.ui.access_level),
        )

        self.ui.access_level.setCurrentIndex(1)
        self.ui.access_level.setCurrentIndex(0)

        selected_nodes = (
            model.root.password_node,
            model.root.access_level_node,
        )

        callback = functools.partial(
            self.update_signals,
            only_these=selected_nodes
        )

        def write_access_level():
            d = model.root.write_all_to_device(
                only_these=selected_nodes,
                callback=callback,
            )
            d.addErrback(epyqlib.utils.twisted.catch_expected)
            d.addErrback(epyqlib.utils.twisted.errbackhook)

        self.set_access_level.clicked.connect(write_access_level)

        model.activity_started.connect(self.activity_started)
        model.activity_ended.connect(self.activity_ended)

        self.ui.enforce_range_limits_check_box.stateChanged.connect(
            model.check_range_changed,
        )
        model.check_range_changed(
            self.ui.enforce_range_limits_check_box.checkState(),
        )

        self.ui.module_to_nv.connect(model.module_to_nv)

        read_from_file = functools.partial(
            model.read_from_file,
            parent=self
        )
        self.ui.read_from_file.connect(read_from_file)

        read_from_value_set_file = functools.partial(
            model.read_from_value_set_file,
            parent=self
        )
        self.ui.read_from_value_set_file.connect(read_from_value_set_file)

        write_to_file = functools.partial(
            model.write_to_file,
            parent=self
        )
        self.ui.write_to_file.connect(write_to_file)

        write_to_value_set_file = functools.partial(
            model.write_to_value_set_file,
            parent=self
        )
        self.ui.write_to_value_set_file.connect(write_to_value_set_file)

        for i in epyqlib.nv.Columns.indexes:
            if self.resize_columns[i]:
                self.ui.tree_view.header().setSectionResizeMode(
                    i, QtWidgets.QHeaderView.ResizeToContents)

        for column in model.meta_columns:
            self.ui.tree_view.setItemDelegateForColumn(
                column,
                epyqlib.delegates.ByFunction(
                    model=model,
                    proxy=proxy,
                    parent=self,
                )
            )

        self.ui.tree_view.setColumnHidden(
            epyqlib.nv.Columns.indexes.factory,
            not any(nv.is_factory() for nv in model.root.all_nv())
        )

        model.force_action_decorations = True
        for column in model.icon_columns:
            self.ui.tree_view.resizeColumnToContents(column)
            self.ui.tree_view.header().setSectionResizeMode(
                column, QtWidgets.QHeaderView.Fixed)

        max_icon_column_width = max(
            self.ui.tree_view.columnWidth(c) for c in model.icon_columns
        )

        for column in model.icon_columns:
            self.ui.tree_view.header().setMinimumSectionSize(0)
            self.ui.tree_view.setColumnWidth(column, max_icon_column_width)

        model.force_action_decorations = False

    def clicked(self, index):
        model = self.nonproxy_model()
        index = self.ui.tree_view.model().mapToSource(index)
        node = model.node_from_index(index)

        if isinstance(node, epyqlib.nv.Nv):
            column = index.column()
            if column == model.headers.indexes.saturate:
                model.saturate_node(node)
            elif column == model.headers.indexes.reset:
                model.reset_node(node)
            elif column == model.headers.indexes.clear:
                model.clear_node(node)

    @pyqtSlot(str)
    def activity_started(self, string):
        self.ui.status_label.setText(string)
        self.progress = epyqlib.utils.qt.Progress()
        self.progress.connect(
            progress=epyqlib.utils.qt.progress_dialog(parent=self),
            label_text=string,
        )

    @pyqtSlot(str)
    def activity_ended(self, string):
        self.ui.status_label.setText(string)
        if self.progress is not None:
            self.progress.complete()
            self.progress = None

    def context_menu(self, position):
        proxy = self.ui.tree_view.model()

        index = self.ui.tree_view.indexAt(position)
        index = proxy.mapToSource(index)

        model = self.nonproxy_model()

        node = model.node_from_index(index)
        node_type = type(node)

        dispatch = {
            epyqlib.nv.Nv: self.nv_context_menu
        }

        f = dispatch.get(node_type)
        if f is not None:
            f(position)
        else:
            self.other_context_menu(position)

    def other_context_menu(self, position):
        menu = QtWidgets.QMenu(parent=self.ui.tree_view)
        menu.setSeparatorsCollapsible(True)

        expand_all = menu.addAction('Expand All')
        collapse_all = menu.addAction('Collapse All')

        action = menu.exec(self.ui.tree_view.viewport().mapToGlobal(position))

        if action is expand_all:
            self.ui.tree_view.expandAll()
        elif action is collapse_all:
            self.ui.tree_view.collapseAll()

    def nv_context_menu(self, position):
        proxy = self.ui.tree_view.model()
        model = self.nonproxy_model()

        selection_model = self.ui.tree_view.selectionModel()
        selected_indexes = selection_model.selectedRows()
        selected_indexes = tuple(
            proxy.mapToSource(i) for i in selected_indexes
        )
        selected_nodes = tuple(
            model.node_from_index(i) for i in selected_indexes
        )
        selected_nodes = tuple(
            node for node in selected_nodes if isinstance(node, epyqlib.nv.Nv)
        )

        menu = QtWidgets.QMenu(parent=self.ui.tree_view)
        menu.setSeparatorsCollapsible(True)

        read = menu.addAction('Read {}'.format(
            self.ui.read_from_module_button.text()))
        write = menu.addAction('Write {}'.format(
            self.ui.write_to_module_button.text()))
        saturate = menu.addAction('Saturate')
        if not any(n.can_be_saturated() for n in selected_nodes):
            saturate.setDisabled(True)
        reset = menu.addAction('Reset')
        if not any(n.can_be_reset() for n in selected_nodes):
            reset.setDisabled(True)
        clear = menu.addAction('Clear')
        if not any(n.can_be_cleared() for n in selected_nodes):
            clear.setDisabled(True)

        menu.addSeparator()
        expand_all = menu.addAction('Expand All')
        collapse_all = menu.addAction('Collapse All')

        action = menu.exec(self.ui.tree_view.viewport().mapToGlobal(position))

        callback = functools.partial(
            self.update_signals,
            only_these=selected_nodes
        )
        if action is None:
            pass
        elif action is read:
            d = model.root.read_all_from_device(
                only_these=selected_nodes,
                callback=callback,
            )
            d.addErrback(epyqlib.utils.twisted.catch_expected)
            d.addErrback(epyqlib.utils.twisted.errbackhook)
        elif action is write:
            d = model.root.write_all_to_device(
                only_these=selected_nodes,
                callback=callback,
            )
            d.addErrback(epyqlib.utils.twisted.catch_expected)
            d.addErrback(epyqlib.utils.twisted.errbackhook)
        elif action is saturate:
            for node in selected_nodes:
                model.saturate_node(node)
        elif action is reset:
            for node in selected_nodes:
                model.reset_node(node)
        elif action is clear:
            for node in selected_nodes:
                model.clear_node(node)
        elif action is expand_all:
            self.ui.tree_view.expandAll()
        elif action is collapse_all:
            self.ui.tree_view.collapseAll()

    def update_signals(self, arg, only_these):
        d, meta = arg
        model = self.nonproxy_model()

        frame = next(iter(d)).frame

        signals = set(only_these) & set(frame.set_frame.parameter_signals)

        for signal in signals:
            if signal.status_signal in d:
                value = d[signal.status_signal]
                signal.set_meta(value, meta=meta, check_range=False)

        for signal in frame.set_frame.parameter_signals:
            model.dynamic_columns_changed(
                signal,
                columns=(getattr(epyqlib.nv.Columns.indexes, meta.name),)
            )


if __name__ == '__main__':
    import sys

    print('No script functionality here')
    sys.exit(1)     # non-zero is a failure
