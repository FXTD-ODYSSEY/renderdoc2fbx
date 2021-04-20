# -*- coding: utf-8 -*-
"""
FBX Exporter
"""

from __future__ import division
from __future__ import print_function
from __future__ import absolute_import

__author__ = "timmyliang"
__email__ = "820472580@qq.com"
__date__ = "2021-01-26 20:44:17"


import os
import time
import json
import struct
import inspect
from textwrap import dedent
from functools import partial
from collections import defaultdict, OrderedDict

from PySide2 import QtWidgets, QtCore, QtGui

import renderdoc as rd
import qrenderdoc

from .query_dialog import QueryDialog
from .progress_dialog import MProgressDialog

FBX_ASCII_TEMPLETE = """
    ; FBX 7.3.0 project file
    ; ----------------------------------------------------

    ; Object definitions
    ;------------------------------------------------------------------

    Definitions:  {

        ObjectType: "Geometry" {
            Count: 1
            PropertyTemplate: "FbxMesh" {
                Properties70:  {
                    P: "Primary Visibility", "bool", "", "",1
                }
            }
        }

        ObjectType: "Model" {
            Count: 1
            PropertyTemplate: "FbxNode" {
                Properties70:  {
                    P: "Visibility", "Visibility", "", "A",1
                }
            }
        }
    }

    ; Object properties
    ;------------------------------------------------------------------

    Objects:  {
        Geometry: 2035541511296, "Geometry::", "Mesh" {
            Vertices: *%(vertices_num)s {
                a: %(vertices)s
            } 
            PolygonVertexIndex: *%(polygons_num)s {
                a: %(polygons)s
            } 
            GeometryVersion: 124
            %(LayerElementNormal)s
            %(LayerElementBiNormal)s
            %(LayerElementTangent)s
            %(LayerElementColor)s
            %(LayerElementUV)s
            %(LayerElementUV2)s
            Layer: 0 {
                Version: 100
                %(LayerElementNormalInsert)s
                %(LayerElementBiNormalInsert)s
                %(LayerElementTangentInsert)s
                %(LayerElementColorInsert)s
                %(LayerElementUVInsert)s
                
            }
            Layer: 1 {
                Version: 100
                %(LayerElementUV2Insert)s
            }
        }
        Model: 2035615390896, "Model::%(model_name)s", "Mesh" {
            Properties70:  {
                P: "DefaultAttributeIndex", "int", "Integer", "",0
            }
        }
    }

    ; Object connections
    ;------------------------------------------------------------------

    Connections:  {
        
        ;Model::pCube1, Model::RootNode
        C: "OO",2035615390896,0
        
        ;Geometry::, Model::pCube1
        C: "OO",2035541511296,2035615390896

    }

    """


def export_fbx(save_path, mapper, data, attr_list, controller):

    if not data:
        # manager.ErrorDialog("Current Draw Call lack of Vertex. ", "Error")
        return

    save_name = os.path.basename(os.path.splitext(save_path)[0])

    # We'll decode the first three indices making up a triangle
    idx_dict = data["IDX"]
    value_dict = defaultdict(list)
    vertex_data = defaultdict(OrderedDict)

    for i, idx in enumerate(idx_dict):
        for attr in attr_list:
            value = data[attr][i]
            value_dict[attr].append(value)
            if idx not in vertex_data[attr]:
                vertex_data[attr][idx] = value

    # print(json.dumps(vertex_data))

    ARGS = {
        "model_name": save_name,
        "LayerElementNormal": "",
        "LayerElementNormalInsert": "",
        "LayerElementBiNormal": "",
        "LayerElementBiNormalInsert": "",
        "LayerElementTangent": "",
        "LayerElementTangentInsert": "",
        "LayerElementColor": "",
        "LayerElementColorInsert": "",
        "LayerElementUV": "",
        "LayerElementUVInsert": "",
        "LayerElementUV2": "",
        "LayerElementUV2Insert": "",
    }

    POSITION = mapper.get("POSITION")
    NORMAL = mapper.get("NORMAL")
    BINORMAL = mapper.get("BINORMAL")
    TANGENT = mapper.get("TANGENT")
    COLOR = mapper.get("COLOR")
    UV = mapper.get("UV")
    UV2 = mapper.get("UV2")
    ENGINE = mapper.get("ENGINE")

    polygons = idx_dict
    if not polygons:
        return
    min_poly = min(polygons)
    idx_list = [str(idx - min_poly) for idx in idx_dict]
    idx_data = ",".join(idx_list)
    idx_len = len(idx_list)

    class ProcessHandler(object):
        def __init__(self, config):
            self.__dict__.update(config)

        def run(self):
            curr = time.time()
            for name, func in inspect.getmembers(self, inspect.isroutine):
                if name.startswith("run_"):
                    func()
            print("elapsed time template: %s" % (time.time() - curr))

        def run_vertices(self):
            vertices = [
                str(v) for values in self.vertex_data[POSITION].values() for v in values
            ]
            self.ARGS["vertices"] = ",".join(vertices)
            self.ARGS["vertices_num"] = len(vertices)

        def run_polygons(self):
            if ENGINE == "unreal":
                polygons = []
                indices = []
                for i, idx in enumerate(self.idx_dict):
                    if i % 3 == 0:
                        indices.append(idx - self.min_poly)
                    elif i % 3 == 1:
                        indices.append(idx - self.min_poly + 1)
                    elif i % 3 == 2:
                        indices.append(idx - self.min_poly)
                        polygons.append(str(indices[0]))
                        polygons.append(str(indices[2]))
                        polygons.append(str(-indices[1]))
                        indices = []
            else:
                polygons = [
                    str(idx - self.min_poly)
                    if i % 3
                    else str(-(idx - self.min_poly + 1))
                    for i, idx in enumerate(self.idx_dict, 1)
                ]

            self.ARGS["polygons"] = ",".join(polygons)
            self.ARGS["polygons_num"] = len(polygons)

        def run_normals(self):
            if not self.vertex_data.get(NORMAL):
                return

            if ENGINE == "unreal":
                normals = []
                indices = []
                for i, idx in enumerate(self.idx_dict):
                    if i % 3 == 0:
                        indices.append(idx)
                    elif i % 3 == 1:
                        indices.append(idx)
                    elif i % 3 == 2:
                        indices.append(idx)
                        _normals = self.vertex_data[NORMAL]
                        normals.extend([str(v) for v in _normals[indices[0]][:3]])
                        normals.extend([str(v) for v in _normals[indices[2]][:3]])
                        normals.extend([str(v) for v in _normals[indices[1]][:3]])
                        indices = []
            else:
                # NOTE FBX_ASCII only support 3 dimension
                normals = [
                    str(v) for values in self.value_dict[NORMAL] for v in values[:3]
                ]

            self.ARGS[
                "LayerElementNormal"
            ] = """
                LayerElementNormal: 0 {
                    Version: 101
                    Name: ""
                    MappingInformationType: "ByPolygonVertex"
                    ReferenceInformationType: "Direct"
                    Normals: *%(normals_num)s {
                        a: %(normals)s
                    } 
                }
            """ % {
                "normals": ",".join(normals),
                "normals_num": len(normals),
            }
            self.ARGS[
                "LayerElementNormalInsert"
            ] = """
                LayerElement:  {
                        Type: "LayerElementNormal"
                    TypedIndex: 0
                }
            """

        def run_binormals(self):
            if not self.vertex_data.get(BINORMAL):
                return
            # NOTE FBX_ASCII only support 3 dimension

            if ENGINE == "unreal":
                binormals = []
                indices = []
                for i, idx in enumerate(self.idx_dict):
                    if i % 3 == 0:
                        indices.append(idx)
                    elif i % 3 == 1:
                        indices.append(idx)
                    elif i % 3 == 2:
                        indices.append(idx)
                        _binormals = self.vertex_data[BINORMAL]
                        binormals.extend([str(v) for v in _binormals[indices[0]][:3]])
                        binormals.extend([str(v) for v in _binormals[indices[2]][:3]])
                        binormals.extend([str(v) for v in _binormals[indices[1]][:3]])
                        indices = []
            else:
                binormals = [
                    str(-v) for values in self.value_dict[BINORMAL] for v in values[:3]
                ]

            self.ARGS[
                "LayerElementBiNormal"
            ] = """
                LayerElementBinormal: 0 {
                    Version: 101
                    Name: "map1"
                    MappingInformationType: "ByVertice"
                    ReferenceInformationType: "Direct"
                    Binormals: *%(binormals_num)s {
                        a: %(binormals)s
                    } 
                    BinormalsW: *%(binormalsW_num)s {
                        a: %(binormalsW)s
                    } 
                }
            """ % {
                "binormals": ",".join(binormals),
                "binormals_num": len(binormals),
                "binormalsW": ",".join(["1" for i in range(self.idx_len)]),
                "binormalsW_num": self.idx_len,
            }
            self.ARGS[
                "LayerElementBiNormalInsert"
            ] = """
                LayerElement:  {
                        Type: "LayerElementBinormal"
                    TypedIndex: 0
                }
            """

        def run_tangents(self):
            if not self.vertex_data.get(TANGENT):
                return

            if ENGINE == "unreal":
                tangents = []
                indices = []
                for i, idx in enumerate(self.idx_dict):
                    if i % 3 == 0:
                        indices.append(idx)
                    elif i % 3 == 1:
                        indices.append(idx)
                    elif i % 3 == 2:
                        indices.append(idx)
                        _tangents = self.vertex_data[TANGENT]
                        tangents.extend([str(v) for v in _tangents[indices[0]][:3]])
                        tangents.extend([str(v) for v in _tangents[indices[2]][:3]])
                        tangents.extend([str(v) for v in _tangents[indices[1]][:3]])
                        indices = []
            else:
                tangents = [
                    str(v) for values in self.value_dict[TANGENT] for v in values[:3]
                ]

            self.ARGS[
                "LayerElementTangent"
            ] = """
                LayerElementTangent: 0 {
                    Version: 101
                    Name: "map1"
                    MappingInformationType: "ByPolygonVertex"
                    ReferenceInformationType: "Direct"
                    Tangents: *%(tangents_num)s {
                        a: %(tangents)s
                    } 
                }
            """ % {
                "tangents": ",".join(tangents),
                "tangents_num": len(tangents),
            }

            self.ARGS[
                "LayerElementTangentInsert"
            ] = """
                    LayerElement:  {
                        Type: "LayerElementTangent"
                        TypedIndex: 0
                    }
            """

        def run_color(self):
            if not self.vertex_data.get(COLOR):
                return

            if ENGINE == "unreal":
                colors = []
                indices = []
                for i, idx in enumerate(self.idx_dict):
                    if i % 3 == 0:
                        indices.append(idx)
                    elif i % 3 == 1:
                        indices.append(idx)
                    elif i % 3 == 2:
                        indices.append(idx)
                        _colors = self.vertex_data[COLOR]
                        colors.extend([str(v) for v in _colors[indices[0]]])
                        colors.extend([str(v) for v in _colors[indices[2]]])
                        colors.extend([str(v) for v in _colors[indices[1]]])
                        indices = []
            else:
                colors = [
                    # str(v) if i % 4 else "1"
                    str(v)
                    for values in self.value_dict[COLOR]
                    for i, v in enumerate(values, 1)
                ]

            self.ARGS[
                "LayerElementColor"
            ] = """
                LayerElementColor: 0 {
                    Version: 101
                    Name: "colorSet1"
                    MappingInformationType: "ByPolygonVertex"
                    ReferenceInformationType: "IndexToDirect"
                    Colors: *%(colors_num)s {
                        a: %(colors)s
                    } 
                    ColorIndex: *%(colors_indices_num)s {
                        a: %(colors_indices)s
                    } 
                }
            """ % {
                "colors": ",".join(colors),
                "colors_num": len(colors),
                "colors_indices": ",".join([str(i) for i in range(self.idx_len)]),
                "colors_indices_num": self.idx_len,
            }
            self.ARGS[
                "LayerElementColorInsert"
            ] = """
                LayerElement:  {
                    Type: "LayerElementColor"
                    TypedIndex: 0
                }
            """

        def run_uv(self):
            if not self.vertex_data.get(UV):
                return

            # if ENGINE == "unreal":
            #     uvs = []
            #     indices = []
            #     for i, idx in enumerate(self.idx_dict):
            #         if i % 3 == 0:
            #             indices.append(idx)
            #         elif i % 3 == 1:
            #             indices.append(idx)
            #         elif i % 3 == 2:
            #             indices.append(idx)
            #             uvs.extend([str(v) for v in self.vertex_data[UV][indices[0]]])
            #             uvs.extend([str(v) for v in self.vertex_data[UV][indices[2]]])
            #             uvs.extend([str(v) for v in self.vertex_data[UV][indices[1]]])
            #             indices = []
            # else:
            uvs = [
                # NOTE flip y axis
                str(1 - v if i else v)
                for values in self.vertex_data[UV].values()
                for i, v in enumerate(values)
            ]

            self.ARGS[
                "LayerElementUV"
            ] = """
                LayerElementUV: 0 {
                    Version: 101
                    Name: "map1"
                    MappingInformationType: "ByPolygonVertex"
                    ReferenceInformationType: "IndexToDirect"
                    UV: *%(uvs_num)s {
                        a: %(uvs)s
                    } 
                    UVIndex: *%(uvs_indices_num)s {
                        a: %(uvs_indices)s
                    } 
                }
            """ % {
                "uvs": ",".join(uvs),
                "uvs_num": len(uvs),
                "uvs_indices": self.idx_data,
                "uvs_indices_num": self.idx_len,
            }

            self.ARGS[
                "LayerElementUVInsert"
            ] = """
                LayerElement:  {
                    Type: "LayerElementUV"
                    TypedIndex: 0
                }
            """

        def run_uv2(self):
            if not self.vertex_data.get(UV2):
                return

            # if ENGINE == "unreal":
            #     uvs = []
            #     indices = []
            #     for i, idx in enumerate(self.idx_dict):
            #         if i % 3 == 0:
            #             indices.append(idx)
            #         elif i % 3 == 1:
            #             indices.append(idx)
            #         elif i % 3 == 2:
            #             indices.append(idx)
            #             uvs.extend([str(v) for v in self.vertex_data[UV2][indices[0]]])
            #             uvs.extend([str(v) for v in self.vertex_data[UV2][indices[2]]])
            #             uvs.extend([str(v) for v in self.vertex_data[UV2][indices[1]]])
            #             indices = []
            # else:
            uvs = [
                # NOTE flip y axis
                str(1 - v if i else v)
                for values in self.vertex_data[UV2].values()
                for i, v in enumerate(values)
            ]

            self.ARGS[
                "LayerElementUV2"
            ] = """
                LayerElementUV: 1 {
                    Version: 101
                    Name: "map2"
                    MappingInformationType: "ByPolygonVertex"
                    ReferenceInformationType: "IndexToDirect"
                    UV: *%(uvs_num)s {
                        a: %(uvs)s
                    } 
                    UVIndex: *%(uvs_indices_num)s {
                        a: %(uvs_indices)s
                    } 
                }
            """ % {
                "uvs": ",".join(uvs),
                "uvs_num": len(uvs),
                "uvs_indices": self.idx_data,
                "uvs_indices_num": self.idx_len,
            }

            self.ARGS[
                "LayerElementUV2Insert"
            ] = """
                LayerElement:  {
                    Type: "LayerElementUV"
                    TypedIndex: 1
                }
            """

    handler = ProcessHandler(
        {
            "polygons": polygons,
            "min_poly": min_poly,
            "idx_list": idx_list,
            "idx_data": idx_data,
            "idx_len": idx_len,
            "ARGS": ARGS,
            "idx_dict": idx_dict,
            "value_dict": value_dict,
            "vertex_data": vertex_data,
        }
    )
    handler.run()

    fbx = FBX_ASCII_TEMPLETE % ARGS

    with open(save_path, "w") as f:
        f.write(dedent(fbx).strip())


def prepare_export(pyrenderdoc, data):
    manager = pyrenderdoc.Extensions()
    if not pyrenderdoc.HasMeshPreview():
        manager.ErrorDialog("No preview mesh!", "Error")
        return

    mqt = manager.GetMiniQtHelper()
    dialog = QueryDialog(mqt)
    # NOTE get input attribute
    if not mqt.ShowWidgetAsDialog(dialog.init_ui()):
        return

    save_path = manager.SaveFileName("Save FBX File", "", "*.fbx")
    if not save_path:
        return

    current = time.time()

    # NOTE Get Data from QTableView directly
    main_window = pyrenderdoc.GetMainWindow().Widget()
    table = main_window.findChild(QtWidgets.QTableView, "vsinData")

    model = table.model()
    row_count = model.rowCount()
    column_count = model.columnCount()
    rows = range(row_count)
    columns = range(column_count)

    data = defaultdict(list)
    attr_list = set()

    # # NOTE progressbar display
    # pool = QtCore.QThreadPool.globalInstance()
    # pool.setMaxThreadCount(8)

    for _, c in MProgressDialog.loop(columns, status="Collect Mesh Data"):
        head = model.headerData(c, QtCore.Qt.Horizontal)
        values = [model.data(model.index(r, c)) for r in rows]
        if "." not in head:
            data[head] = values
        else:
            attr = head.split(".")[0]
            attr_list.add(attr)
            data[attr].append(values)

    for _, attr in MProgressDialog.loop(attr_list, status="Rearrange Mesh Data"):
        values_list = data[attr]
        data[attr] = [[float(values[r]) for values in values_list] for r in rows]

    print("elapsed time unpack: %s" % (time.time() - current))
    pyrenderdoc.Replay().BlockInvoke(
        partial(export_fbx, save_path, dialog.mapper, data, attr_list)
    )

    if os.path.exists(save_path):
        manager.MessageDialog("FBX Ouput Sucessfully", "Congradualtion!~")
        os.startfile(os.path.dirname(save_path))
    else:
        manager.MessageDialog(
            "FBX Ouput Fail\nPlease Check the attribute input", "Error!~"
        )


def register(version, pyrenderdoc):
    # version is the RenderDoc Major.Minor version as a string, such as "1.2"
    # pyrenderdoc is the CaptureContext handle, the same as the global available in the python shell
    print("Registering FBX Mesh Exporter extension for RenderDoc {}".format(version))
    pyrenderdoc.Extensions().RegisterPanelMenu(
        qrenderdoc.PanelMenu.MeshPreview, ["Export FBX Mesh"], prepare_export
    )


def unregister():
    print("Unregistrating FBX Mesh Exporter extension")
