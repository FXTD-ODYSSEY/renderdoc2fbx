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
from threading import Thread

import renderdoc as rd
import qrenderdoc

from .query_dialog import QueryDialog

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


class MeshData(rd.MeshFormat):
    indexOffset = 0
    name = ""


formatChars = {}
formatChars[rd.CompType.UInt] = "xBHxIxxxL"
formatChars[rd.CompType.SInt] = "xbhxixxxl"
formatChars[rd.CompType.Float] = "xxexfxxxd"  # only 2, 4 and 8 are valid

# These types have identical decodes, but we might post-process them
formatChars[rd.CompType.UNorm] = formatChars[rd.CompType.UInt]
formatChars[rd.CompType.UScaled] = formatChars[rd.CompType.UInt]
formatChars[rd.CompType.SNorm] = formatChars[rd.CompType.SInt]
formatChars[rd.CompType.SScaled] = formatChars[rd.CompType.SInt]

nested_dict = lambda: defaultdict(nested_dict)
vertexFormat = nested_dict()
# https://stackoverflow.com/a/36797651
# fmt.compCount 234
# fmt.compByteWidth 124
for compCount in [2, 3, 4]:
    for compType in formatChars:
        for compByteWidth in [1, 2, 4]:
            vertexFormat[compCount][compType][compByteWidth] = struct.Struct(
                "%s%s" % (compCount,formatChars[compType][compByteWidth])
            ).unpack_from


# Unpack a tuple of the given format, from the data
def unpackData(fmt, data):
    # We don't handle 'special' formats - typically bit-packed such as 10:10:10:2
    if fmt.Special():
        raise RuntimeError("Packed formats are not supported!")

    # # We need to fetch compCount components
    # vertexFormat = "%s%s" % (fmt.compCount,formatChars[fmt.compType][fmt.compByteWidth])
    # value = struct.unpack_from(vertexFormat, data, 0)

    # TODO enhance performance
    unpack_from = vertexFormat[fmt.compCount][fmt.compType][fmt.compByteWidth]
    value = unpack_from(data)

    # If the format needs post-processing such as normalisation, do that now
    if fmt.compType == rd.CompType.UNorm:
        divisor = float((2 ** (fmt.compByteWidth * 8)) - 1)
        value = tuple(float(i) / divisor for i in value)
    elif fmt.compType == rd.CompType.SNorm:
        maxNeg = -float(2 ** (fmt.compByteWidth * 8)) / 2
        divisor = float(-(maxNeg - 1))
        value = tuple(
            (float(i) if (i == maxNeg) else (float(i) / divisor)) for i in value
        )

    # If the format is BGRA, swap the two components
    if fmt.BGRAOrder():
        value = tuple(value[i] for i in (2, 1, 0, 3))

    return value


def getIndices(controller, mesh):
    # Get the character for the width of index
    indexFormat = "B"
    if mesh.indexByteStride == 2:
        indexFormat = "H"
    elif mesh.indexByteStride == 4:
        indexFormat = "I"

    # Duplicate the format by the number of indices
    indexFormat = str(mesh.numIndices) + indexFormat

    # If we have an index buffer
    if mesh.indexResourceId != rd.ResourceId.Null():
        # Fetch the data
        ibdata = controller.GetBufferData(mesh.indexResourceId, mesh.indexByteOffset, 0)

        # Unpack all the indices, starting from the first index to fetch
        offset = mesh.indexOffset * mesh.indexByteStride
        indices = struct.unpack_from(indexFormat, ibdata, offset)

        # Apply the baseVertex offset
        return [i + mesh.baseVertex for i in indices]
    else:
        # With no index buffer, just generate a range
        return tuple(range(mesh.numIndices))


def findChannel(vertexData, keywords):
    for channel in vertexData:
        for keyword in keywords:
            if keyword in channel:
                return channel
    return None


def unpack(controller, attr, idx):
    # This is the data we're reading from. This would be good to cache instead of
    # re-fetching for every attribute for every index
    offset = attr.vertexByteOffset + attr.vertexByteStride * idx
    data = controller.GetBufferData(attr.vertexResourceId, offset, 0)

    # Get the value from the data
    return unpackData(attr.format, data)


def export_fbx(save_path, mapper, meshInputs, controller):

    indices = getIndices(controller, meshInputs[0])
    if not indices:
        # manager.ErrorDialog("Current Draw Call lack of Vertex. ", "Error")
        return

    save_name = os.path.basename(os.path.splitext(save_path)[0])
    curr = time.time()

    # We'll decode the first three indices making up a triangle
    idx_dict = defaultdict(list)
    value_dict = defaultdict(list)
    vertex_data = defaultdict(OrderedDict)

    for idx in indices:
        for attr in meshInputs:
            value = unpack(controller, attr, idx)
            idx_dict[attr.name].append(idx)
            value_dict[attr.name].append(value)
            if idx not in vertex_data[attr.name]:
                vertex_data[attr.name][idx] = value

    print("elapsed time unpack: %s" % (time.time() - curr))

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

    polygons = idx_dict[POSITION]
    if not polygons:
        return
    min_poly = min(polygons)
    idx_list = [str(idx - min_poly) for idx in idx_dict[POSITION]]
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
                str(v)
                for values in self.vertex_data[self.POSITION].values()
                for v in values
            ]
            self.ARGS["vertices"] = ",".join(vertices)
            self.ARGS["vertices_num"] = len(vertices)

        def run_polygons(self):
            polygons = []
            # temp_list = []
            # for i, idx in enumerate(self.idx_dict[self.POSITION]):
            #     if i % 3 == 0:
            #         temp_list.append(idx - self.min_poly)
            #     elif i % 3 == 1:
            #         temp_list.append(idx - self.min_poly)
            #     elif i % 3 == 2:
            #         temp_list.append(idx - self.min_poly + 1)
            #         polygons.append(str(temp_list[1]))
            #         polygons.append(str(temp_list[0]))
            #         polygons.append(str(-temp_list[2]))
            #         temp_list = []
                
            polygons = [
                str(idx - self.min_poly) if i % 3 else str(-(idx - self.min_poly + 1))
                for i, idx in enumerate(self.idx_dict[self.POSITION], 1)
            ]
            self.ARGS["polygons"] = ",".join(polygons)
            self.ARGS["polygons_num"] = len(polygons)

        def run_normals(self):
            if not self.vertex_data.get(self.NORMAL):
                return
            # NOTE FBX_ASCII only support 3 dimension
            normals = [
                str(v) for values in self.value_dict[self.NORMAL] for v in values[:3]
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
            # print("binormals")
            # print(self.vertex_data.get(self.BINORMAL))
            if not self.vertex_data.get(self.BINORMAL):
                return
            # NOTE FBX_ASCII only support 3 dimension
            binormals = [
                str(-v) for values in self.value_dict[self.BINORMAL] for v in values[:3]
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
            if not self.vertex_data.get(self.TANGENT):
                return
            tangents = [
                str(v) for values in self.value_dict[self.TANGENT] for v in values[:3]
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
            if not self.vertex_data.get(self.COLOR):
                return
            colors = [
                # str(v) if i % 4 else "1"
                str(v) 
                for values in self.value_dict[self.COLOR]
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
            if not self.vertex_data.get(self.UV):
                return

            uvs = [
                # NOTE flip y axis
                str(1 - v if i else v)
                for values in self.vertex_data[self.UV].values()
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
            if not self.vertex_data.get(self.UV2):
                return

            uvs = [
                # NOTE flip y axis
                str(1 - v if i else v)
                for values in self.vertex_data[self.UV2].values()
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
            "POSITION": POSITION,
            "NORMAL": NORMAL,
            "BINORMAL": BINORMAL,
            "TANGENT": TANGENT,
            "COLOR": COLOR,
            "UV": UV,
            "UV2": UV2,
            "ENGINE": ENGINE,
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

    state = pyrenderdoc.CurPipelineState()

    # Get the index & vertex buffers, and fixed vertex inputs
    ib = state.GetIBuffer()
    vbs = state.GetVBuffers()
    attrs = state.GetVertexInputs()

    # NOTE current draw draw
    draw = pyrenderdoc.CurSelectedDrawcall()
    if not draw:
        msg = "Please pick a valid draw call in the Event Browser."
        manager.ErrorDialog(msg, "Error")
        return

    meshInputs = []
    for attr in attrs:
        if not attr.used:
            continue
        elif attr.perInstance:
            # We don't handle instance attributes
            manager.ErrorDialog("Instanced properties are not supported!", "Error")
            return

        meshInput = MeshData()
        meshInput.indexResourceId = ib.resourceId
        meshInput.indexByteOffset = ib.byteOffset
        meshInput.indexByteStride = draw.indexByteWidth
        meshInput.baseVertex = draw.baseVertex
        meshInput.indexOffset = draw.indexOffset
        meshInput.numIndices = draw.numIndices

        # If the draw doesn't use an index buffer, don't use it even if bound
        if not (draw.flags & rd.DrawFlags.Indexed):
            meshInput.indexResourceId = rd.ResourceId.Null()

        # The total offset is the attribute offset from the base of the vertex
        meshInput.vertexByteOffset = (
            attr.byteOffset
            + vbs[attr.vertexBuffer].byteOffset
            + draw.vertexOffset * vbs[attr.vertexBuffer].byteStride
        )
        meshInput.format = attr.format
        meshInput.vertexResourceId = vbs[attr.vertexBuffer].resourceId
        meshInput.vertexByteStride = vbs[attr.vertexBuffer].byteStride
        meshInput.name = attr.name

        meshInputs.append(meshInput)

    save_path = manager.SaveFileName("Save FBX File", "", "*.fbx")
    if not save_path:
        return

    pyrenderdoc.Replay().BlockInvoke(
        partial(export_fbx, save_path, dialog.mapper, meshInputs)
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
