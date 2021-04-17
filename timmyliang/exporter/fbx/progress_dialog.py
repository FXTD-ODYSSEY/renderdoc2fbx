# -*- coding: utf-8 -*-
"""
progressbar dispaly 
"""

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

from PySide2.QtCore import QTimer

__author__ = 'timmyliang'
__email__ = '820472580@qq.com'
__date__ = '2021-04-17 19:50:02'

from PySide2 import QtWidgets, QtCore, QtGui

class QProgressDialog(QtWidgets.QProgressDialog):
    def __init__(self, status=u"progress...",button_text=u"Cancel",minimum=0,maximum=100,parent=None,title=""):
        super(QProgressDialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        self.setWindowModality(QtCore.Qt.WindowModal)
        self.setWindowTitle(status if title else title)
        self.setLabelText(status)
        self.setCancelButtonText(button_text)
        self.setRange(minimum,maximum)
        self.setValue(minimum)
        self.delay()

    def delay(self):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(1, loop.quit)
        loop.exec_()
    
    def setLabelText(self,text):
        super(QProgressDialog, self).setLabelText(text)
        self.delay()
    
    @classmethod
    def loop(cls,seq,**kwargs):
        self = cls(**kwargs)
        if not kwargs.get("maximum"):
            self.setMaximum(len(seq))
        for i,item in enumerate(seq,1):

            if self.wasCanceled():break
            try:
                yield i,item  # with body executes here
            except:
                import traceback
                traceback.print_exc()
                self.deleteLater()
            self.setValue(i)
        self.deleteLater()
        
# class ProgressDialog(object):
#     title = "Progress..."

#     def __init__(self, mqt):
#         self.mqt = mqt

    
#     def init_ui(self,tasks,label =u"进度",total=None):
#         self.widget = self.mqt.CreateToplevelWidget(self.title)
#         self.mqt.AddWidget(self.widget, button_container)
#         total = total if total else len(tasks)
#         self.progress = IProgressDialog()
#         for i,task in enumerate(tasks):
#             yield i,task

            
#         with unreal.ScopedSlowTask(total, label) as task:
#             task.make_dialog(True)
#             for i, item in enumerate(tasks):
#                 if task.should_cancel():
#                     break
#                 task.enter_progress_frame(1, "%s %s/%s" % (label,i, total))
#                 yield i, item
                
#     def loop(self):
#         self.widget = self.mqt.CreateToplevelWidget(self.title)

#         # NOTE template option
#         container = self.mqt.CreateHorizontalContainer()
#         label = self.mqt.CreateLabel()
        
#         self.combo = QtWidgets.QComboBox(self.combo)
#         self.combo.addItems(["unity", "unreal"])
#         self.combo.setCurrentText(self.settings.value("Engine", "unity"))
#         self.combo.currentIndexChanged.connect(self.template_select)

#         self.mqt.SetWidgetText(label, "template")
#         self.mqt.AddWidget(container, label)
#         self.mqt.AddWidget(container, self.combo)
#         self.mqt.AddWidget(self.widget, container)

#         self.button_dict = {}
#         for name, label in self.edit_config.items():
#             w = self.input_widget(label, name)
#             self.button_dict[name] = w
#             self.mqt.AddWidget(self.widget, w)
#             # NOTE load settings
#             text = self.settings.value(name, "")
#             if text and text != name:
#                 self.mqt.SetWidgetText(w.edit, text)

#         button_container = self.mqt.CreateHorizontalContainer()
#         ok_button = self.mqt.CreateButton(self.accept)
#         self.mqt.SetWidgetText(ok_button, "OK")
#         callback = lambda *args: self.mqt.CloseCurrentDialog(False)
#         cancel_button = self.mqt.CreateButton(callback)
#         self.mqt.SetWidgetText(cancel_button, "Cancel")
#         self.mqt.AddWidget(button_container, cancel_button)
#         self.mqt.AddWidget(button_container, ok_button)
#         self.mqt.AddWidget(self.widget, button_container)

