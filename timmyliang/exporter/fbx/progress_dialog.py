# -*- coding: utf-8 -*-
"""
progressbar dispaly 
"""

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

from PySide2.QtCore import QTimer

__author__ = "timmyliang"
__email__ = "820472580@qq.com"
__date__ = "2021-04-17 19:50:02"

from PySide2 import QtWidgets, QtCore, QtGui


class MProgressDialog(QtWidgets.QProgressDialog):
    def __init__(
        self,
        status=u"progress...",
        button_text=u"Cancel",
        minimum=0,
        maximum=100,
        parent=None,
        title="",
    ):
        super(MProgressDialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags())
        self.setWindowModality(QtCore.Qt.WindowModal)
        self.setWindowTitle(status if title else title)
        bar = QtWidgets.QProgressBar(self)
        bar.setStyleSheet(
            """
            QProgressBar {
                color:white;
                border: 1px solid black;
                background: gray;
            }

            QProgressBar::chunk {
                background: QLinearGradient( x1: 0, y1: 0, x2: 1, y2: 0,
                stop: 0 #78d,
                stop: 0.4999 #46a,
                stop: 0.5 #45a,
                stop: 1 #238 );
                border: 1px solid black;
            }
            """
        )
        bar.setAlignment(QtCore.Qt.AlignCenter)
        self.setBar(bar)
        self.setLabelText(status)
        self.setCancelButtonText(button_text)
        self.setRange(minimum, maximum)
        self.setValue(minimum)
        
        # NOTE show the progressbar without blocking
        self.show()
        QtWidgets.QApplication.processEvents()

    @classmethod
    def loop(cls, seq, **kwargs):
        self = cls(**kwargs)
        if not kwargs.get("maximum"):
            self.setMaximum(len(seq))
        for i, item in enumerate(seq, 1):

            if self.wasCanceled():
                break
            try:
                yield i, item  # with body executes here
            except:
                import traceback

                traceback.print_exc()
                self.deleteLater()
            self.setValue(i)
        self.deleteLater()
