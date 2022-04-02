# -*- coding: utf-8 -*-
"""
- [x] save the user input | using QSettings

"""

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

__author__ = "timmyliang"
__email__ = "820472580@qq.com"
__date__ = "2021-04-09 20:39:53"

import os
import tempfile
from functools import partial
from PySide2 import QtWidgets, QtCore, QtGui

# manager = pyrenderdoc.Extensions()
# mqt = manager.GetMiniQtHelper()


class QueryDialog(object):

    title = "Attribute Query"
    space = "%-15s"

    edit_config = {
        "POSITION": space % "Vertex Position",
        "TANGENT": space % "Vertex Tangent",
        "NORMAL": space % "Vertex Normal",
        "BINORMAL": space % "Vertex BiNormal",
        "COLOR": space % "Vertex Color",
        "UV": space % "UV",
        "UV2": space % "UV2",
    }

    button_dict = {}
    mapper = {}

    def __init__(self, mqt):
        self.mqt = mqt
        name = "RenderDoc_%s.ini" % self.__class__.__name__
        path = os.path.join(tempfile.gettempdir(),name)
        self.settings = QtCore.QSettings(path, QtCore.QSettings.IniFormat)
        if not os.path.exists(path):
            self.template_select(0)

    def template_select(self, index):
        text = self.combo.itemText(index) if hasattr(self,"combo") else "unity"
        config = {}
        if text == "unity":
            config = {
                "POSITION": "POSITION",
                "TANGENT": "TANGENT",
                "BINORMAL": "",
                "NORMAL": "NORMAL",
                "COLOR": "COLOR",
                "UV": "TEXCOORD0",
                "UV2": "TEXCOORD1",
            }
        elif text == "unreal":
            config = {
                "POSITION": "ATTRIBUTE0",
                "TANGENT": "ATTRIBUTE1",
                "BINORMAL": "",
                "NORMAL": "ATTRIBUTE2",
                "COLOR": "ATTRIBUTE13",
                "UV": "ATTRIBUTE5",
                "UV2": "ATTRIBUTE6",
            }

        self.settings.setValue("Engine", text)
        for name, input_widget in self.button_dict.items():
            value = config.get(name, "")
            self.settings.setValue(name, value)
            self.mqt.SetWidgetText(input_widget.edit, value)

    def init_ui(self):
        self.widget = self.mqt.CreateToplevelWidget(self.title, None)

        # NOTE template option
        container = self.mqt.CreateHorizontalContainer()
        label = self.mqt.CreateLabel()
        
        self.combo = QtWidgets.QComboBox()
        self.combo.addItems(["unity", "unreal"])
        self.combo.setCurrentText(self.settings.value("Engine", "unity"))
        self.combo.currentIndexChanged.connect(self.template_select)

        self.mqt.SetWidgetText(label, "template")
        self.mqt.AddWidget(container, label)
        self.mqt.AddWidget(container, self.combo)
        self.mqt.AddWidget(self.widget, container)

        self.button_dict = {}
        for name, label in self.edit_config.items():
            w = self.input_widget(label, name)
            self.button_dict[name] = w
            self.mqt.AddWidget(self.widget, w)
            # NOTE load settings
            text = self.settings.value(name, "")
            if text and text != name:
                self.mqt.SetWidgetText(w.edit, text)

        button_container = self.mqt.CreateHorizontalContainer()
        ok_button = self.mqt.CreateButton(self.accept)
        self.mqt.SetWidgetText(ok_button, "OK")
        callback = lambda *args: self.mqt.CloseCurrentDialog(False)
        cancel_button = self.mqt.CreateButton(callback)
        self.mqt.SetWidgetText(cancel_button, "Cancel")
        self.mqt.AddWidget(button_container, cancel_button)
        self.mqt.AddWidget(button_container, ok_button)
        self.mqt.AddWidget(self.widget, button_container)

        return self.widget

    def accept(self, context, widget, text):
        self.mapper = {}
        for name, WIDGET in self.button_dict.items():
            text = self.mqt.GetWidgetText(WIDGET.edit)
            self.mapper[name] = text
        
        self.mapper['ENGINE'] = self.combo.currentText()

        self.mqt.CloseCurrentDialog(True)

    def textChange(self, key, c, w, text):
        self.settings.setValue(key, text)

    def input_widget(self, text, edit_text="", type=""):
        container = self.mqt.CreateHorizontalContainer()
        label = self.mqt.CreateLabel()
        edit = self.mqt.CreateTextBox(True, partial(self.textChange, edit_text))

        self.mqt.SetWidgetText(label, text)
        self.mqt.SetWidgetText(edit, edit_text)
        self.mqt.AddWidget(container, label)
        self.mqt.AddWidget(container, edit)

        container.label = label
        container.edit = edit
        return container


# if self.mqt.ShowWidgetAsDialog(QueryDialog.init_ui()):
#     print(QueryDialog.result_dict)
