# renderdoc2fbx
renderdoc python extension for exporting fbx data

## Usage

copy `fbx_exporter` folder to `%appdata%\qrenderdoc\extensions`

If you are in the windows platform, you can use `install.bat` to install the extension.

## Feature

Export ASCII FBX File Support

+ **Vertex** 
+ **Normal** 
+ **UV**
+ **Tangent**
+ **VertexColor**

![FBX](image/01.png)

## Notice 

Export Large Mesh especially more than 30000 vertices need several seconds,
Python extension not efficient enough for that large Mesh. 
