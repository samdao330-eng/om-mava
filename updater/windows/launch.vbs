' OM MAVA Updater on Windows: opens the window with no console (bundled Python, nothing installed).
Set sh = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
root = fs.GetParentFolderName(WScript.ScriptFullName)
If Not fs.FileExists(root & "\python\pythonw.exe") Then
  MsgBox "Bản cài OM MAVA Updater bị thiếu Python — cài lại từ file Setup.", vbExclamation, "OM MAVA Updater"
  WScript.Quit
End If
sh.Run """" & root & "\python\pythonw.exe"" -I -B """ & root & "\app\updater_gui.py""", 1, False
