' Arranca el bot sin ventana. La carpeta se puede mover donde quieras.
Set fso = CreateObject("Scripting.FileSystemObject")
carpeta = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = carpeta
sh.Run """" & carpeta & "\runtime\pythonw.exe"" """ & carpeta & "\supervisor.py""", 0, False
