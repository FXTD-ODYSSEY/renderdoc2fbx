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
import json
import struct
from textwrap import dedent
from collections import defaultdict, OrderedDict

FBX_ASCII_TEMPLETE = """
    ; FBX 7.3.0 project file
    ; ----------------------------------------------------

    FBXHeaderExtension:  {
        FBXHeaderVersion: 1003
        FBXVersion: 7300
        CreationTimeStamp:  {
            Version: 1000
            Year: 2021
            Month: 1
            Day: 26
            Hour: 21
            Minute: 4
            Second: 59
            Millisecond: 682
        }
    }


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
            %(LayerElementTangent)s
            %(LayerElementColor)s
            %(LayerElementUV)s
            Layer: 0 {
                Version: 100
                %(LayerElementNormalInsert)s
                %(LayerElementTangentInsert)s
                %(LayerElementColorInsert)s
                %(LayerElementUVInsert)s
                
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

rd = renderdoc
manager = pyrenderdoc.Extensions()


class MeshData(rd.MeshFormat):
    indexOffset = 0
    name = ""


# Unpack a tuple of the given format, from the data
def unpackData(fmt, data):
    # We don't handle 'special' formats - typically bit-packed such as 10:10:10:2
    if fmt.Special():
        raise RuntimeError("Packed formats are not supported!")

    formatChars = {}
    #                                 012345678
    formatChars[rd.CompType.UInt] = "xBHxIxxxL"
    formatChars[rd.CompType.SInt] = "xbhxixxxl"
    formatChars[rd.CompType.Float] = "xxexfxxxd"  # only 2, 4 and 8 are valid

    # These types have identical decodes, but we might post-process them
    formatChars[rd.CompType.UNorm] = formatChars[rd.CompType.UInt]
    formatChars[rd.CompType.UScaled] = formatChars[rd.CompType.UInt]
    formatChars[rd.CompType.SNorm] = formatChars[rd.CompType.SInt]
    formatChars[rd.CompType.SScaled] = formatChars[rd.CompType.SInt]

    # We need to fetch compCount components
    vertexFormat = str(fmt.compCount) + formatChars[fmt.compType][fmt.compByteWidth]

    # Unpack the data
    value = struct.unpack_from(vertexFormat, data, 0)

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
        value = tuple(value[i] for i in [2, 1, 0, 3])

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


def test(controller):
    state = controller.GetPipelineState()

    # Get the index & vertex buffers, and fixed vertex inputs
    ib = state.GetIBuffer()
    vbs = state.GetVBuffers()
    attrs = state.GetVertexInputs()

    # NOTE current draw draw
    draw = pyrenderdoc.CurSelectedDrawcall()
    if not draw:
        manager.ErrorDialog(
            "Please pick a valid draw call in the Event Browser.", "Error"
        )
        return

    meshInputs = []
    for attr in attrs:
        # We don't handle instance attributes
        if attr.perInstance:
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

    indices = getIndices(controller, meshInputs[0])
    if not indices:
        manager.ErrorDialog("Current Draw Call lack of Vertex. ", "Error")
        return

    save_path = manager.SaveFileName("Save FBX File", "", "*.fbx")
    if not save_path:
        return

    save_name = os.path.basename(os.path.splitext(save_path)[0])

    # We'll decode the first three indices making up a triangle
    idx_dict = defaultdict(list)
    value_dict = defaultdict(list)
    vertex_data = defaultdict(OrderedDict)
    for i, idx in enumerate(indices):
        for attr in meshInputs:
            value = unpack(controller, attr, idx)
            idx_dict[attr.name].append(idx)
            value_dict[attr.name].append(value)
            if idx not in vertex_data[attr.name]:
                vertex_data[attr.name][idx] = value

    # print(json.dumps(vertex_data))

    polygons = [idx for idx in idx_dict["POSITION"]]
    min_poly = min(polygons)
    idx_list = [str(idx - min_poly) for idx in idx_dict["POSITION"]]
    idx_data = ",".join(idx_list)
    idx_len = len(idx_list)

    ARGS = {"model_name": save_name}
    vertices = [str(v) for values in vertex_data["POSITION"].values() for v in values]
    ARGS["vertices"] = ",".join(vertices)
    ARGS["vertices_num"] = len(vertices)

    # NOTE https://www.codenong.com/cs105411312/
    polygons = [
        str(idx - min_poly) if i % 3 else str(-(idx - min_poly + 1))
        for i, idx in enumerate(idx_dict["POSITION"], 1)
    ]
    ARGS["polygons"] = ",".join(polygons)
    ARGS["polygons_num"] = len(polygons)

    LayerElementNormal = ""
    LayerElementNormalInsert = ""
    has_normal = vertex_data.get("NORMAL")
    if has_normal:
        normals = [str(v) for values in value_dict["NORMAL"] for v in values]

        LayerElementNormal = """
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
        LayerElementNormalInsert = """
            LayerElement:  {
                    Type: "LayerElementNormal"
                TypedIndex: 0
            }
        """

    LayerElementTangent = ""
    LayerElementTangentInsert = ""
    has_tangent = vertex_data.get("TANGENT")
    if has_tangent:
        tangents = [str(v) for values in value_dict["TANGENT"] for v in values]
        LayerElementTangent = """
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

        LayerElementTangentInsert = """
                LayerElement:  {
                    Type: "LayerElementTangent"
                    TypedIndex: 0
                }
        """

    LayerElementColor = ""
    LayerElementColorInsert = ""
    has_color = vertex_data.get("COLOR")
    if has_color:
        colors = [str(v) if i%4 else "1" for values in value_dict["COLOR"] for i,v in enumerate(values,1)]

        LayerElementColor = """
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
            "colors_indices": ",".join([str(i) for i in range(idx_len)]),
            "colors_indices_num": idx_len,
        }
        LayerElementColorInsert = """
            LayerElement:  {
                Type: "LayerElementColor"
                TypedIndex: 0
            }
        """

    LayerElementUV = ""
    LayerElementUVInsert = ""
    has_uv = vertex_data.get("TEXCOORD0")
    if has_uv:
        uvs = [str(v) for values in vertex_data["TEXCOORD0"].values() for v in values]

        LayerElementUV = """
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
            "uvs_indices":idx_data,
            "uvs_indices_num": idx_len,
        }

        LayerElementUVInsert = """
            LayerElement:  {
                Type: "LayerElementUV"
                TypedIndex: 0
            }
        """

    ARGS.update(
        {
            "LayerElementNormal": LayerElementNormal,
            "LayerElementNormalInsert": LayerElementNormalInsert,
            "LayerElementTangent": LayerElementTangent,
            "LayerElementTangentInsert": LayerElementTangentInsert,
            "LayerElementColor": LayerElementColor,
            "LayerElementColorInsert": LayerElementColorInsert,
            "LayerElementUV": LayerElementUV,
            "LayerElementUVInsert": LayerElementUVInsert
        }
    )

    fbx = FBX_ASCII_TEMPLETE % ARGS

    with open(save_path, "w") as f:
        f.write(dedent(fbx).strip())
        # json.dump(value_dict,f,indent=4)

    # print(json.dumps(value_dict))
    # manager.MessageDialog("FBX Ouput Sucessfully", "Congradualtion!~")


pyrenderdoc.Replay().BlockInvoke(test)
