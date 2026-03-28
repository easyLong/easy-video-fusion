Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)

Set env = shell.Environment("Process")
env("PYTHONPATH") = root & "\src;" & env("PYTHONPATH")

shell.Run "pythonw -m easy_video_fusion.gui", 0, False
